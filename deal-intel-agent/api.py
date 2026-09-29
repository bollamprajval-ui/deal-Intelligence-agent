"""
API layer over the backend. Run with: uvicorn api:app --reload
Serves the Deal Document UI from / and JSON under the routes below.
"""
import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from core.db import (
    init_db,
    upsert_deal,
    get_deal,
    get_deal_timeline,
    get_thread,
    get_stage_history,
    get_conn,
    get_people_for_deal,
    add_person,
    link_person_to_deal,
    set_person_role,
    add_review,
    list_reviews,
    list_signals,
    days_since_last_input,
    log_stage_change,
    find_person_by_email,
)
from core.notifications import list_unread, mark_read, notify
from core.agent import chat, get_chat_history
from core.hindsight import close_deal, retrieve_similar, list_hindsight_library
from core.db import get_reasoning_chain
from core.llm import llm_status
from core.scheduler import start_scheduler
from main import run_ingest, ingest_one
from connectors.base import RawItem

WEB_DIR = os.path.join(os.path.dirname(__file__), "web")
os.makedirs(WEB_DIR, exist_ok=True)

app = FastAPI(title="Deal Intelligence Agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateDealBody(BaseModel):
    name: str
    budget: Optional[float] = None


class ChatBody(BaseModel):
    message: str


class CloseBody(BaseModel):
    outcome: str
    outcome_reason: Optional[str] = None


class PasteBody(BaseModel):
    content: str
    source: str = "paste"
    sender_email: Optional[str] = None
    occurred_at: Optional[str] = None


class ReviewBody(BaseModel):
    note: str


class StageBody(BaseModel):
    stage: str


class PersonBody(BaseModel):
    name: str
    email: Optional[str] = None
    org: Optional[str] = None
    role: Optional[str] = None
    side: Optional[str] = Field(default=None, description="theirs or ours — stored in org prefix if needed")


class RoleBody(BaseModel):
    role: str


VALID_STAGES = {
    "contact", "discovery", "proposal", "negotiation", "closed_won", "closed_lost",
}
VALID_OUTCOMES = {"won", "lost", "stalled", "closed_won", "closed_lost"}


@app.on_event("startup")
def startup():
    init_db()
    if os.environ.get("DEAL_INTEL_DISABLE_SCHEDULER", "0") != "1":
        start_scheduler()


def _require_deal(deal_id: str) -> dict:
    deal = get_deal(deal_id)
    if not deal:
        raise HTTPException(404, "Deal not found")
    return deal


@app.get("/health")
def health():
    return llm_status()


# --- Deals ---

@app.get("/deals")
def list_deals():
    conn = get_conn()
    rows = conn.execute(
        """SELECT id, name, stage, outcome, budget, created_at, updated_at
           FROM deals ORDER BY updated_at DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/deals")
def create_deal(body: CreateDealBody):
    deal_id = upsert_deal(name=body.name, budget=body.budget)
    return {"deal_id": deal_id}


@app.get("/deals/{deal_id}")
def deal_document(deal_id: str):
    """The live Deal Document — snapshot, people, log, signals, reviews, stall hint."""
    deal = _require_deal(deal_id)
    quiet_days = days_since_last_input(deal_id)
    return {
        "deal": deal,
        "people": get_people_for_deal(deal_id),
        "timeline": get_deal_timeline(deal_id),
        "stages": get_stage_history(deal_id),
        "signals": list_signals(deal_id),
        "reviews": list_reviews(deal_id),
        "quiet_days": quiet_days,
        "needs_review": bool(quiet_days is not None and quiet_days >= 5 and not deal.get("outcome")),
    }


@app.get("/deals/{deal_id}/timeline")
def deal_timeline(deal_id: str):
    _require_deal(deal_id)
    return get_deal_timeline(deal_id)


@app.get("/deals/{deal_id}/stages")
def deal_stage_history(deal_id: str):
    _require_deal(deal_id)
    return get_stage_history(deal_id)


@app.post("/deals/{deal_id}/stage")
def set_stage(deal_id: str, body: StageBody):
    _require_deal(deal_id)
    if body.stage not in VALID_STAGES:
        raise HTTPException(400, f"Unknown stage. Use one of: {sorted(VALID_STAGES)}")
    log_stage_change(deal_id, body.stage)
    notify(deal_id=deal_id, kind="stage_change", message=f"Deal moved to {body.stage}.")
    return {"status": "ok", "stage": body.stage}


@app.post("/deals/{deal_id}/ingest")
def trigger_ingest(deal_id: str):
    _require_deal(deal_id)
    run_ingest(deal_id)
    return {"status": "ingested"}


@app.post("/deals/{deal_id}/inputs")
def paste_input(deal_id: str, body: PasteBody):
    """Forward or paste mail, notes, or a transcript into the deal."""
    _require_deal(deal_id)
    if not body.content.strip():
        raise HTTPException(400, "content is empty")
    raw = RawItem(
        source=body.source or "paste",
        content=body.content,
        occurred_at=body.occurred_at or "",
        sender_email=body.sender_email,
        raw_ref=None,
    )
    input_id = ingest_one(deal_id, raw)
    return {"input_id": input_id, "status": "stored" if input_id else "skipped"}


@app.get("/deals/{deal_id}/people")
def deal_people(deal_id: str):
    _require_deal(deal_id)
    return get_people_for_deal(deal_id)


@app.post("/deals/{deal_id}/people")
def add_deal_person(deal_id: str, body: PersonBody):
    _require_deal(deal_id)
    person_id = None
    if body.email:
        existing = find_person_by_email(body.email)
        if existing:
            person_id = existing["id"]
    if not person_id:
        person_id = add_person(name=body.name, email=body.email, org=body.org)
    role = body.role
    if body.side and role:
        role = f"{body.side}:{role}"
    elif body.side:
        role = body.side
    link_person_to_deal(deal_id, person_id, role=role)
    return {"person_id": person_id}


@app.post("/deals/{deal_id}/people/{person_id}/role")
def update_role(deal_id: str, person_id: str, body: RoleBody):
    _require_deal(deal_id)
    set_person_role(deal_id, person_id, body.role)
    return {"status": "ok"}


@app.get("/deals/{deal_id}/reviews")
def deal_reviews(deal_id: str):
    _require_deal(deal_id)
    return list_reviews(deal_id)


@app.post("/deals/{deal_id}/reviews")
def create_review(deal_id: str, body: ReviewBody):
    _require_deal(deal_id)
    if not body.note.strip():
        raise HTTPException(400, "note is empty")
    review_id = add_review(deal_id, body.note.strip())
    return {"review_id": review_id}


@app.get("/deals/{deal_id}/signals")
def deal_signals(deal_id: str):
    _require_deal(deal_id)
    return list_signals(deal_id)


# --- Threads ---

@app.get("/threads/{thread_id}")
def thread_detail(thread_id: str):
    rows = get_thread(thread_id)
    if not rows:
        raise HTTPException(404, "Thread not found")
    return rows


# --- Notifications ---

@app.get("/notifications")
def notifications(deal_id: Optional[str] = None):
    return list_unread(deal_id)


@app.post("/notifications/{notification_id}/read")
def read_notification(notification_id: str):
    mark_read(notification_id)
    return {"status": "read"}


# --- Agent ---

@app.post("/deals/{deal_id}/chat")
def agent_chat(deal_id: str, body: ChatBody):
    _require_deal(deal_id)
    if not body.message.strip():
        raise HTTPException(400, "message is empty")
    reply = chat(deal_id, body.message.strip())
    status = llm_status()
    return {"reply": reply, "model": status.get("model"), "ollama": status.get("ollama")}


@app.get("/deals/{deal_id}/chat")
def chat_history(deal_id: str):
    _require_deal(deal_id)
    return get_chat_history(deal_id)


@app.get("/hindsight")
def hindsight_library():
    """All closed deals stored for comparison."""
    return list_hindsight_library()


@app.get("/deals/{deal_id}/hindsight")
def deal_hindsight(deal_id: str, top_k: int = 3):
    _require_deal(deal_id)
    return retrieve_similar(deal_id, top_k=top_k)


@app.get("/deals/{deal_id}/reasoning")
def reasoning_chain(deal_id: str):
    _require_deal(deal_id)
    return get_reasoning_chain(deal_id)


@app.post("/deals/{deal_id}/close")
def close(deal_id: str, body: CloseBody):
    _require_deal(deal_id)
    outcome = body.outcome.strip().lower()
    if outcome not in VALID_OUTCOMES:
        raise HTTPException(400, f"Unknown outcome. Use one of: {sorted(VALID_OUTCOMES)}")
    mapped = {"won": "closed_won", "lost": "closed_lost"}.get(outcome, outcome)
    if mapped in {"closed_won", "closed_lost"}:
        log_stage_change(deal_id, mapped)
    close_deal(deal_id, outcome, body.outcome_reason)
    return {"status": "closed", "outcome": outcome}


@app.get("/")
def ui_root():
    index = os.path.join(WEB_DIR, "index.html")
    if not os.path.isfile(index):
        raise HTTPException(404, "UI not built")
    return FileResponse(index)


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
