"""
Two directions, both mandatory (per earlier design decision):
  - write_hindsight(): every CLOSED deal writes a structured record + embedding
  - retrieve_similar(): every live deal's reasoning step pulls from that store
"""
import json
from core.db import (
    get_deal_timeline, get_deal, list_signals, update_deal_outcome,
    list_hindsight_records, upsert_hindsight_record,
)
from core import vector_store


def close_deal(deal_id: str, outcome: str, outcome_reason: str = None):
    """Marks a deal closed and writes it into hindsight. This is the
    mandatory write-back — hindsight decays if any closed deal skips it."""
    deal = update_deal_outcome(deal_id, outcome, outcome_reason)
    if not deal:
        raise ValueError(f"Deal not found: {deal_id}")

    signals = _signal_summary(deal_id)
    timeline = get_deal_timeline(deal_id)
    text = _hindsight_text(deal["name"], deal["stage"], outcome, outcome_reason, signals, timeline)

    _write_hindsight_row(deal_id, deal["stage"], outcome, outcome_reason, signals)
    vector_store.add(deal_id, text, metadata={
        "stage_reached": deal["stage"], "outcome": outcome, "outcome_reason": outcome_reason,
    })


def retrieve_similar(deal_id: str, top_k: int = 3):
    """Pulls the most similar CLOSED deals for a live deal, to ground the
    agent's reasoning. Returns [] if hindsight is still cold (no closed
    deals yet) — callers must handle that, not fake a comparison."""
    timeline = get_deal_timeline(deal_id)
    text = " ".join(row["summary"] for row in timeline)
    if not text.strip():
        return []
    hits = vector_store.search(text, top_k=top_k)
    return _attach_names(hits)


def list_hindsight_library():
    """Every closed deal written into hindsight — the training set."""
    return list_hindsight_records()


def _attach_names(hits):
    out = []
    for hit in hits:
        row = get_deal(hit.get("deal_id"))
        item = dict(hit)
        item["name"] = row["name"] if row else "Closed deal"
        out.append(item)
    return out


def _signal_summary(deal_id: str) -> dict:
    return {row["signal_type"]: row["detail"] for row in list_signals(deal_id)}


def _hindsight_text(name, stage, outcome, reason, signals, timeline) -> str:
    parts = [name, stage, outcome, reason or "", json.dumps(signals)]
    parts += [row["summary"] for row in timeline]
    return " ".join(p for p in parts if p)


def _write_hindsight_row(deal_id, stage, outcome, outcome_reason, signals):
    upsert_hindsight_record(deal_id, stage, outcome, outcome_reason, signals)
