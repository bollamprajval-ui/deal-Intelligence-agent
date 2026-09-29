"""
Two directions, both mandatory (per earlier design decision):
  - write_hindsight(): every CLOSED deal writes a structured record + embedding
  - retrieve_similar(): every live deal's reasoning step pulls from that store
"""
import json
from core.db import get_conn, get_deal_timeline, get_stage_history
from core import vector_store


def close_deal(deal_id: str, outcome: str, outcome_reason: str = None):
    """Marks a deal closed and writes it into hindsight. This is the
    mandatory write-back — hindsight decays if any closed deal skips it."""
    conn = get_conn()
    conn.execute(
        "UPDATE deals SET outcome = ?, outcome_reason = ?, updated_at = datetime('now') WHERE id = ?",
        (outcome, outcome_reason, deal_id),
    )
    deal = conn.execute("SELECT * FROM deals WHERE id = ?", (deal_id,)).fetchone()
    conn.commit()
    conn.close()
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
    conn = get_conn()
    rows = conn.execute(
        """SELECT h.deal_id, d.name, h.stage_reached, h.outcome, h.outcome_reason,
                  h.signal_summary, h.written_at
           FROM hindsight_records h
           JOIN deals d ON d.id = h.deal_id
           ORDER BY h.written_at DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _attach_names(hits):
    conn = get_conn()
    out = []
    for hit in hits:
        row = conn.execute("SELECT name FROM deals WHERE id = ?", (hit.get("deal_id"),)).fetchone()
        item = dict(hit)
        item["name"] = row["name"] if row else "Closed deal"
        out.append(item)
    conn.close()
    return out


def _signal_summary(deal_id: str) -> dict:
    conn = get_conn()
    rows = conn.execute("SELECT signal_type, detail FROM signals WHERE deal_id = ?", (deal_id,)).fetchall()
    conn.close()
    return {r["signal_type"]: r["detail"] for r in rows}


def _hindsight_text(name, stage, outcome, reason, signals, timeline) -> str:
    parts = [name, stage, outcome, reason or "", json.dumps(signals)]
    parts += [row["summary"] for row in timeline]
    return " ".join(p for p in parts if p)


def _write_hindsight_row(deal_id, stage, outcome, outcome_reason, signals):
    conn = get_conn()
    conn.execute(
        """INSERT INTO hindsight_records (deal_id, stage_reached, outcome, outcome_reason, signal_summary)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(deal_id) DO UPDATE SET
             stage_reached=excluded.stage_reached, outcome=excluded.outcome,
             outcome_reason=excluded.outcome_reason, signal_summary=excluded.signal_summary""",
        (deal_id, stage, outcome, outcome_reason, json.dumps(signals)),
    )
    conn.commit()
    conn.close()
