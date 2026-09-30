"""
One AI per deal. Every answer is grounded only in THAT deal's file:
snapshot, people, log, reviews, prior reasoning on this deal, plus
hindsight from closed deals as comparison — never mixed with another live deal's chat.
"""
from core.db import (
    get_chat_history as read_chat_history, add_chat_message, get_deal, get_deal_timeline, get_stage_history,
    get_people_for_deal, list_reviews, list_signals,
    add_reasoning_node, get_latest_reasoning,
)
from core.hindsight import retrieve_similar
from core.llm import call_llm

SYSTEM_PROMPT = (
    "You are the AI for one sales deal. You only know this deal's file. "
    "Answer plainly. Use the log, people, notes, and your prior reasoning. "
    "If something is not in the file, say you do not know and ask for it. "
    "Do not invent meetings or quotes. "
    "If hindsight from closed deals is empty, do not pretend you have a comparison. "
    "Respond with two parts:\n"
    "REASONING: <2-4 sentences of updated understanding for next turn>\n"
    "REPLY: <the answer the user should read>"
)


def chat(deal_id: str, user_message: str) -> str:
    _store_message(deal_id, "user", user_message)

    deal = get_deal(deal_id) or {}
    timeline = get_deal_timeline(deal_id)
    stages = get_stage_history(deal_id)
    people = get_people_for_deal(deal_id)
    reviews = list_reviews(deal_id)
    signals = list_signals(deal_id)
    hindsight_matches = retrieve_similar(deal_id, top_k=3)
    prior_reasoning = get_latest_reasoning(deal_id)

    prompt = _build_prompt(
        user_message, deal, people, reviews, signals,
        timeline, stages, hindsight_matches, prior_reasoning,
    )
    raw = call_llm(prompt, system=SYSTEM_PROMPT)
    reasoning_text, reply_text = _split_response(raw)

    add_reasoning_node(
        deal_id=deal_id,
        trigger=user_message,
        reasoning=reasoning_text,
        parent_reasoning_id=prior_reasoning["id"] if prior_reasoning else None,
    )
    _store_message(deal_id, "agent", reply_text)
    return reply_text


def get_chat_history(deal_id: str):
    return read_chat_history(deal_id)


def _store_message(deal_id: str, role: str, content: str):
    add_chat_message(deal_id, role, content)


def _build_prompt(user_message, deal, people, reviews, signals, timeline, stages, hindsight_matches, prior_reasoning) -> str:
    people_text = "\n".join(
        f"- {p['name']} ({p.get('role') or 'role unknown'}) {p.get('email') or ''} {p.get('org') or ''}".strip()
        for p in people
    ) or "(no people yet)"
    reviews_text = "\n".join(f"- {r['note']}" for r in reviews) or "(no human notes yet)"
    signal_text = ", ".join(sorted({s["signal_type"] for s in signals})) or "(none)"
    timeline_text = "\n".join(
        f"- [{r['tool_source']}] {r['occurred_at']}: {r['summary']}" for r in timeline
    ) or "(no interactions logged yet)"
    stage_text = " -> ".join(s["stage"] for s in stages) or "(no stage history)"

    if hindsight_matches:
        hindsight_text = "\n".join(
            f"- score={m['score']} outcome={m['metadata'].get('outcome')}, "
            f"reason={m['metadata'].get('outcome_reason')}"
            for m in hindsight_matches
        )
    else:
        hindsight_text = "(none)"

    if prior_reasoning:
        prior_text = f"{prior_reasoning['reasoning']}"
    else:
        prior_text = "(first turn on this deal)"

    return (
        f"DEAL NAME: {deal.get('name')}\n"
        f"BUDGET: {deal.get('budget')}\n"
        f"STAGE: {deal.get('stage')}\n"
        f"OUTCOME: {deal.get('outcome') or 'open'}\n"
        f"OUTCOME WHY: {deal.get('outcome_reason') or '—'}\n\n"
        f"PEOPLE:\n{people_text}\n\n"
        f"TAGS: {signal_text}\n\n"
        f"YOUR NOTES:\n{reviews_text}\n\n"
        f"INTERACTION LOG:\n{timeline_text}\n\n"
        f"STAGE PATH: {stage_text}\n\n"
        f"CLOSED DEALS LIKE THIS (hindsight):\n{hindsight_text}\n\n"
        f"YOUR PRIOR UNDERSTANDING OF THIS DEAL:\n{prior_text}\n\n"
        f"USER: {user_message}"
    )


def _split_response(raw: str):
    reasoning, reply = "", raw
    if "REASONING:" in raw and "REPLY:" in raw:
        reasoning = raw.split("REASONING:", 1)[1].split("REPLY:", 1)[0].strip()
        reply = raw.split("REPLY:", 1)[1].strip()
    return reasoning or "(no structured reasoning captured)", reply
