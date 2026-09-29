"""
Root entrypoint. Registers all tool connectors, runs the ingest loop:
tool -> raw item -> matcher (which deal/thread/chain position) ->
extraction -> DB -> notification.
"""
from core.db import (
    init_db, upsert_deal, add_input, log_stage_change, get_deal_timeline,
    find_person_by_email, add_person, link_person_to_deal, already_ingested,
    add_signal,
)
from core.matcher import resolve, is_unmatched
from core.notifications import notify, list_unread
from connectors.mail_connector import MailConnector
from connectors.voice_connector import VoiceConnector
from connectors.spreadsheet_connector import SpreadsheetConnector
from connectors.meeting_connector import MeetingConnector

CONNECTORS = [
    MailConnector(mailbox_path="./data/mail"),
    VoiceConnector(transcripts_dir="./data/voice_transcripts"),
    SpreadsheetConnector(sheets_dir="./data/spreadsheets"),
    MeetingConnector(notes_dir="./data/meeting_notes"),
]


from core.llm import call_llm

def extract_summary(raw_content: str) -> str:
    if not raw_content:
        return "(no content)"
    return call_llm(
        "Summarize this deal interaction in one or two sentences:\n" + raw_content
    )


def ingest_one(deal_id_hint: str, raw_item):
    """The core loop step: match -> extract -> store -> notify.
    This is what runs for every mail, voice note, spreadsheet row, or
    meeting note, from every connector, uniformly."""
    if already_ingested(message_id=raw_item.message_id, raw_ref=raw_item.raw_ref):
        return None

    deal_id, thread_id, parent_input_id, reason = resolve(
        deal_id_hint,
        message_id=raw_item.message_id,
        in_reply_to=raw_item.in_reply_to,
        sender_email=raw_item.sender_email,
    )

    if is_unmatched(deal_id):
        notify(deal_id=None, kind="unmatched_input",
               message=f"[{raw_item.source}] couldn't be matched to a deal ({reason}) — needs manual review.")
        return None

    sender_person_id = None
    if raw_item.sender_email:
        person = find_person_by_email(raw_item.sender_email)
        if person:
            sender_person_id = person["id"]
        elif reason == "new_person_on_hint":
            # First time we've seen this sender — create the record and
            # link them to the deal, then tell the user so they can
            # confirm/correct the name or role.
            sender_person_id = add_person(name=raw_item.sender_email.split("@")[0], email=raw_item.sender_email)
            link_person_to_deal(deal_id, sender_person_id, role=None)
            notify(deal_id=deal_id, kind="new_person_detected",
                   message=f"New contact {raw_item.sender_email} detected and linked to this deal — confirm their role.")

    summary = extract_summary(raw_item.content)
    input_id = add_input(
        deal_id=deal_id,
        tool_source=raw_item.source,
        input_type="reply" if parent_input_id else "message",
        summary=summary,
        occurred_at=raw_item.occurred_at or None,
        raw_ref=raw_item.raw_ref,
        thread_id=thread_id,
        parent_input_id=parent_input_id,
        sender_person_id=sender_person_id,
        message_id=raw_item.message_id,
        in_reply_to=raw_item.in_reply_to,
    )

    for signal_type in tag_signals(raw_item.content):
        add_signal(deal_id, signal_type, detail=summary[:200], input_id=input_id)

    chain_note = f" (reply, chained to {parent_input_id[:8]})" if parent_input_id else f" (matched via {reason})"
    notify(deal_id=deal_id, input_id=input_id, kind="new_input",
           message=f"[{raw_item.source}] {summary[:80]}{chain_note}")
    return input_id


SIGNAL_RULES = (
    ("budget_mentioned", ("budget", "pricing", "price", "cost", "quote", "fee")),
    ("positive_signal", ("acceptable", "interested", "proceed", "approved", "sounds good", "looks good")),
    ("concern_raised", ("concern", "worried", "push back", "too expensive", "delay", "issue", "risk")),
    ("no_response", ("no response", "haven't heard", "following up", "no reply")),
)


def tag_signals(raw_content: str) -> list:
    text = (raw_content or "").lower()
    return [stype for stype, keys in SIGNAL_RULES if any(k in text for k in keys)]


def run_ingest(deal_id: str):
    for connector in CONNECTORS:
        for raw_item in connector.fetch_new(deal_id):
            ingest_one(deal_id, raw_item)


def demo_thread(deal_id: str):
    """Simulates: a first-ever mail resolved purely by sender email (no
    in_reply_to to match on yet), then a reply chained via message_id,
    then a doc — exactly as a real mail connector would report them."""
    from connectors.base import RawItem
    from core.db import add_person, link_person_to_deal

    # Register the counterpart contact and link them to this deal, so the
    # matcher can resolve their first mail without any reply headers.
    person_id = add_person(name="Client Contact", email="client@example.com")
    link_person_to_deal(deal_id, person_id, role="economic_buyer")

    first_mail = RawItem(source="mail", content="Sent initial proposal outlining scope and pricing.",
                          occurred_at="", message_id="msg-001", sender_email="client@example.com")
    reply = RawItem(source="mail", content="Client asked for a revised timeline, budget looks acceptable.",
                     occurred_at="", message_id="msg-002", in_reply_to="msg-001")
    doc = RawItem(source="doc", content="Shared revised timeline document per client's request.",
                  occurred_at="", message_id="msg-003", in_reply_to="msg-002")

    mail_id = ingest_one(None, first_mail)  # note: no deal_id hint — must resolve via sender email
    reply_id = ingest_one(deal_id, reply)
    ingest_one(deal_id, doc)

    log_stage_change(deal_id, "discovery", trigger_input_id=reply_id)
    notify(deal_id=deal_id, kind="stage_change", message="Deal moved to discovery stage.")


if __name__ == "__main__":
    init_db()
    deal_id = upsert_deal(name="Example Deal")
    run_ingest(deal_id)
    demo_thread(deal_id)

    print(f"\nDeal root: {deal_id}")
    print("Full timeline (auto-chained):")
    for row in get_deal_timeline(deal_id):
        print(f"  [{row['tool_source']}] {row['summary'][:55]} "
              f"(thread={row['thread_id'][:8]}, parent={str(row['parent_input_id'])[:8]})")

    print("\nUnread notifications:")
    for n in list_unread(deal_id):
        print(f"  ({n['kind']}) {n['message']}")
