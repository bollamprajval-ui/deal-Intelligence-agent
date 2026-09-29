"""Local SQLite access layer. Everything stays on-device."""
import os
import sqlite3
import uuid
from pathlib import Path
from datetime import datetime

_DEFAULT_DB = Path(__file__).parent.parent / "data" / "deals.db"
DB_PATH = Path(os.environ.get("DEAL_INTEL_DB", str(_DEFAULT_DB)))
SCHEMA_PATH = Path(__file__).parent.parent / "db" / "schema.sql"


def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()


def new_id() -> str:
    return str(uuid.uuid4())


def upsert_deal(name: str, budget: float = None, deal_id: str = None) -> str:
    conn = get_conn()
    is_new = deal_id is None
    deal_id = deal_id or new_id()
    conn.execute(
        """INSERT INTO deals (id, name, budget) VALUES (?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
             name=excluded.name,
             budget=COALESCE(excluded.budget, deals.budget),
             updated_at=datetime('now')""",
        (deal_id, name, budget),
    )
    conn.commit()
    conn.close()
    if is_new:
        log_stage_change(deal_id, "contact")
    return deal_id


def add_input(
    deal_id: str,
    tool_source: str,
    input_type: str,
    summary: str,
    occurred_at: str = None,
    thread_id: str = None,
    parent_input_id: str = None,
    sender_person_id: str = None,
    link: str = None,
    raw_ref: str = None,
    message_id: str = None,
    in_reply_to: str = None,
) -> str:
    """Insert one input (mail / voice note / doc / meeting note / reply).
    thread_id groups a whole conversation; parent_input_id links a reply
    to the specific input it responds to, so 'x mail -> y response -> z doc'
    reconstructs as a chain, not three disconnected rows."""
    conn = get_conn()
    iid = new_id()
    conn.execute(
        """INSERT INTO inputs
           (id, deal_id, tool_source, input_type, thread_id, parent_input_id,
            sender_person_id, link, raw_ref, message_id, in_reply_to, summary, occurred_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            iid, deal_id, tool_source, input_type,
            thread_id or iid,  # start of a new thread defaults to its own id
            parent_input_id, sender_person_id, link, raw_ref,
            message_id, in_reply_to, summary,
            occurred_at or datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    conn.close()
    return iid


def add_attachment(input_id: str, file_path: str, file_type: str = None, description: str = None) -> str:
    conn = get_conn()
    aid = new_id()
    conn.execute(
        "INSERT INTO attachments (id, input_id, file_path, file_type, description) VALUES (?, ?, ?, ?, ?)",
        (aid, input_id, file_path, file_type, description),
    )
    conn.commit()
    conn.close()
    return aid


def add_signal(deal_id: str, signal_type: str, detail: str = None, input_id: str = None) -> str:
    conn = get_conn()
    sid = new_id()
    conn.execute(
        "INSERT INTO signals (id, deal_id, input_id, signal_type, detail) VALUES (?, ?, ?, ?, ?)",
        (sid, deal_id, input_id, signal_type, detail),
    )
    conn.commit()
    conn.close()
    return sid


def log_stage_change(deal_id: str, new_stage: str, trigger_input_id: str = None):
    """Closes out the current open stage row and opens a new one — this is
    what makes the full lifecycle (until close) queryable, not just the
    deal's current stage value."""
    conn = get_conn()
    conn.execute(
        "UPDATE deal_stage_history SET exited_at = datetime('now') WHERE deal_id = ? AND exited_at IS NULL",
        (deal_id,),
    )
    conn.execute(
        "INSERT INTO deal_stage_history (id, deal_id, stage, trigger_input_id) VALUES (?, ?, ?, ?)",
        (new_id(), deal_id, new_stage, trigger_input_id),
    )
    conn.execute("UPDATE deals SET stage = ?, updated_at = datetime('now') WHERE id = ?", (new_stage, deal_id))
    conn.commit()
    conn.close()


def get_thread(thread_id: str):
    """Return every input in a thread, in order — the full reply chain."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM inputs WHERE thread_id = ? ORDER BY occurred_at", (thread_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_deal_timeline(deal_id: str):
    """Every input for a deal, in order — the full deal process history."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM inputs WHERE deal_id = ? ORDER BY occurred_at", (deal_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def find_person_by_email(email: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM people WHERE email = ?", (email,)).fetchone()
    conn.close()
    return dict(row) if row else None


def add_person(name: str, email: str = None, org: str = None) -> str:
    conn = get_conn()
    pid = new_id()
    conn.execute("INSERT INTO people (id, name, email, org) VALUES (?, ?, ?, ?)", (pid, name, email, org))
    conn.commit()
    conn.close()
    return pid


def link_person_to_deal(deal_id: str, person_id: str, role: str = None):
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO deal_people (deal_id, person_id, role) VALUES (?, ?, ?)",
        (deal_id, person_id, role),
    )
    conn.commit()
    conn.close()


def get_deals_for_person(person_id: str):
    """Every deal this person is linked to — used to resolve a mail sender to a deal."""
    conn = get_conn()
    rows = conn.execute("SELECT deal_id FROM deal_people WHERE person_id = ?", (person_id,)).fetchall()
    conn.close()
    return [r["deal_id"] for r in rows]


def add_reasoning_node(deal_id: str, trigger: str, reasoning: str, parent_reasoning_id: str = None) -> str:
    conn = get_conn()
    rid = new_id()
    conn.execute(
        """INSERT INTO reasoning_chain (id, deal_id, parent_reasoning_id, trigger, reasoning)
           VALUES (?, ?, ?, ?, ?)""",
        (rid, deal_id, parent_reasoning_id, trigger, reasoning),
    )
    conn.commit()
    conn.close()
    return rid


def get_latest_reasoning(deal_id: str):
    """The most recent reasoning node — what the agent currently 'believes'
    about this deal, carried forward into the next turn."""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM reasoning_chain WHERE deal_id = ? ORDER BY created_at DESC LIMIT 1", (deal_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_reasoning_chain(deal_id: str):
    """The full chain, oldest to newest — how the agent's understanding evolved."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM reasoning_chain WHERE deal_id = ? ORDER BY created_at", (deal_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stage_history(deal_id: str):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM deal_stage_history WHERE deal_id = ? ORDER BY entered_at", (deal_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_deal(deal_id: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM deals WHERE id = ?", (deal_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def already_ingested(message_id: str = None, raw_ref: str = None) -> bool:
    """Idempotency for the poller: same mail or same local file is not stored twice."""
    if not message_id and not raw_ref:
        return False
    conn = get_conn()
    if message_id:
        row = conn.execute("SELECT id FROM inputs WHERE message_id = ?", (message_id,)).fetchone()
        if row:
            conn.close()
            return True
    if raw_ref:
        row = conn.execute("SELECT id FROM inputs WHERE raw_ref = ?", (raw_ref,)).fetchone()
        if row:
            conn.close()
            return True
    conn.close()
    return False


def get_people_for_deal(deal_id: str):
    conn = get_conn()
    rows = conn.execute(
        """SELECT p.id, p.name, p.email, p.org, dp.role
           FROM deal_people dp JOIN people p ON p.id = dp.person_id
           WHERE dp.deal_id = ?
           ORDER BY p.name""",
        (deal_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_person_role(deal_id: str, person_id: str, role: str):
    conn = get_conn()
    conn.execute(
        "UPDATE deal_people SET role = ? WHERE deal_id = ? AND person_id = ?",
        (role, deal_id, person_id),
    )
    conn.commit()
    conn.close()


def add_review(deal_id: str, note: str) -> str:
    conn = get_conn()
    rid = new_id()
    conn.execute(
        "INSERT INTO reviews (id, deal_id, note) VALUES (?, ?, ?)",
        (rid, deal_id, note),
    )
    conn.commit()
    conn.close()
    return rid


def list_reviews(deal_id: str):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM reviews WHERE deal_id = ? ORDER BY created_at DESC", (deal_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_signals(deal_id: str):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM signals WHERE deal_id = ? ORDER BY created_at", (deal_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def days_since_last_input(deal_id: str):
    conn = get_conn()
    row = conn.execute(
        "SELECT MAX(occurred_at) AS last_at FROM inputs WHERE deal_id = ?", (deal_id,)
    ).fetchone()
    conn.close()
    last_at = row["last_at"] if row else None
    if not last_at:
        deal = get_deal(deal_id)
        last_at = deal["updated_at"] if deal else None
    if not last_at:
        return None
    try:
        last = datetime.fromisoformat(last_at.replace("Z", "").split(".")[0])
    except ValueError:
        last = datetime.strptime(last_at[:19], "%Y-%m-%d %H:%M:%S")
    return max(0, (datetime.utcnow() - last).days)
