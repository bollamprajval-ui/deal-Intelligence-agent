"""
Given a raw item from any tool connector, figure out:
  1. which deal it belongs to
  2. which thread it belongs to
  3. which specific prior input it's a reply to (chain position)

Two-step resolution:
  A. Exact reply match via message_id/in_reply_to (mail threading headers)
  B. Sender-email match: sender -> known person -> deal(s) they're linked to

This is what makes ingestion automatic instead of manually wired per item,
even for the first mail in a deal that isn't a reply to anything yet.
"""
from core.db import get_input_by_message_id, find_person_by_email, get_deals_for_person


def resolve(deal_id_hint: str, message_id: str = None, in_reply_to: str = None, sender_email: str = None):
    """
    deal_id_hint: caller's best guess (e.g. mailbox folder), used only if
    steps A and B both fail to resolve anything.
    Returns (deal_id, thread_id, parent_input_id, match_reason).
    """
    # A. Exact match: this item explicitly replies to a known input.
    if in_reply_to:
        parent = get_input_by_message_id(in_reply_to)
        if parent:
            return parent["deal_id"], parent["thread_id"], parent["id"], "reply_match"

    # B. Sender match: known person, linked to exactly one deal -> confident match.
    #    Linked to multiple deals -> ambiguous, flag for review rather than guess.
    #    Unknown sender -> can't resolve this way.
    if sender_email:
        person = find_person_by_email(sender_email)
        if person:
            deals = get_deals_for_person(person["id"])
            if len(deals) == 1:
                return deals[0], None, None, "sender_match"
            if len(deals) > 1:
                return None, None, None, "ambiguous_sender"
        elif deal_id_hint:
            # Unknown sender, but we know which deal folder this came from —
            # auto-create the person instead of dropping the input. Caller
            # (main.py) fires a notification so the user can confirm/edit.
            return deal_id_hint, None, None, "new_person_on_hint"

    # C. Fall back to caller's hint (e.g. connector already knows the deal folder).
    if deal_id_hint:
        return deal_id_hint, None, None, "hint_fallback"

    return None, None, None, "unmatched"


def is_unmatched(deal_id: str) -> bool:
    return deal_id is None
