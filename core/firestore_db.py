"""Firestore implementation of the deal store; SQLite remains local default."""
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

_client = None
_TABLES = (
    "deals", "people", "deal_people", "inputs", "attachments", "signals",
    "deal_stage_history", "reviews", "hindsight_records", "notifications",
    "chat_messages", "reasoning_chain",
)


def _now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def client():
    global _client
    if _client is not None:
        return _client
    import firebase_admin
    from firebase_admin import credentials, firestore
    try:
        app = firebase_admin.get_app("deal-intel")
    except ValueError:
        raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
        credential_file = os.environ.get("FIREBASE_SERVICE_ACCOUNT_FILE") or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if raw:
            app_credential = credentials.Certificate(json.loads(raw))
        elif credential_file:
            app_credential = credentials.Certificate(credential_file)
        else:
            raise RuntimeError("Set FIREBASE_SERVICE_ACCOUNT_JSON or GOOGLE_APPLICATION_CREDENTIALS")
        app = firebase_admin.initialize_app(
            app_credential,
            {"projectId": os.environ.get("FIREBASE_PROJECT_ID", "dealagent-b1e72")},
            name="deal-intel",
        )
    _client = firestore.client(app=app)
    return _client


def _collection(name):
    return client().collection(name)


def _get(name, key):
    snap = _collection(name).document(str(key)).get()
    return snap.to_dict() if snap.exists else None


def _all(name):
    return [snap.to_dict() for snap in _collection(name).stream()]


def _where(name, field, value):
    from google.cloud.firestore_v1.base_query import FieldFilter
    return [snap.to_dict() for snap in _collection(name).where(filter=FieldFilter(field, "==", value)).stream()]


def _save(name, key, values, merge=False):
    _collection(name).document(str(key)).set(values, merge=merge)


def _commit_seed(rows_by_table):
    batch = client().batch()
    writes = 0
    for table, rows in rows_by_table.items():
        for row in rows:
            key = f"{row['deal_id']}__{row['person_id']}" if table == "deal_people" else (row.get("id") or row.get("deal_id"))
            batch.set(_collection(table).document(str(key)), row)
            writes += 1
            if writes == 450:
                batch.commit()
                batch = client().batch()
                writes = 0
    if writes:
        batch.commit()


def init_db():
    db_path = Path(__file__).parent.parent / "data" / "deals.db"
    if not db_path.exists():
        return
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = {}
    for table in _TABLES:
        try:
            rows[table] = [dict(row) for row in conn.execute(f"SELECT * FROM {table}").fetchall()]
        except sqlite3.OperationalError:
            rows[table] = []
    conn.close()
    vector_path = db_path.parent / "hindsight_vectors.jsonl"
    if vector_path.exists():
        with open(vector_path, encoding="utf-8") as vectors_file:
            rows["hindsight_vectors"] = [json.loads(line) for line in vectors_file if line.strip()]
    missing = {}
    for table, items in rows.items():
        missing[table] = []
        for item in items:
            key = f"{item['deal_id']}__{item['person_id']}" if table == "deal_people" else (item.get("id") or item.get("deal_id"))
            if not _collection(table).document(str(key)).get().exists:
                missing[table].append(item)
    if any(missing.values()):
        _commit_seed(missing)


def get_conn():
    raise RuntimeError("Direct SQL is unavailable with Firestore; use the deal store functions")


def new_id():
    import uuid
    return str(uuid.uuid4())


def list_deals():
    return sorted(_all("deals"), key=lambda row: row.get("updated_at", ""), reverse=True)


def upsert_deal(name: str, budget: float = None, deal_id: str = None) -> str:
    deal_id = deal_id or new_id()
    existing = _get("deals", deal_id)
    _save("deals", deal_id, {
        "id": deal_id, "name": name,
        "budget": budget if budget is not None else (existing or {}).get("budget"),
        "stage": (existing or {}).get("stage", "contact"),
        "outcome": (existing or {}).get("outcome"),
        "outcome_reason": (existing or {}).get("outcome_reason"),
        "created_at": (existing or {}).get("created_at", _now()), "updated_at": _now(),
    })
    if not existing:
        log_stage_change(deal_id, "contact")
    return deal_id


def add_input(deal_id, tool_source, input_type, summary, occurred_at=None, thread_id=None,
              parent_input_id=None, sender_person_id=None, link=None, raw_ref=None,
              message_id=None, in_reply_to=None):
    input_id = new_id()
    _save("inputs", input_id, {
        "id": input_id, "deal_id": deal_id, "tool_source": tool_source,
        "input_type": input_type, "thread_id": thread_id or input_id,
        "parent_input_id": parent_input_id, "sender_person_id": sender_person_id,
        "link": link, "raw_ref": raw_ref, "message_id": message_id,
        "in_reply_to": in_reply_to, "summary": summary,
        "occurred_at": occurred_at or datetime.utcnow().isoformat(), "created_at": _now(),
    })
    return input_id


def add_attachment(input_id, file_path, file_type=None, description=None):
    attachment_id = new_id()
    _save("attachments", attachment_id, {"id": attachment_id, "input_id": input_id,
          "file_path": file_path, "file_type": file_type, "description": description})
    return attachment_id


def add_signal(deal_id, signal_type, detail=None, input_id=None):
    signal_id = new_id()
    _save("signals", signal_id, {"id": signal_id, "deal_id": deal_id, "input_id": input_id,
          "signal_type": signal_type, "detail": detail, "created_at": _now()})
    return signal_id


def log_stage_change(deal_id, new_stage, trigger_input_id=None):
    from google.cloud.firestore_v1.base_query import FieldFilter
    batch = client().batch()
    history = _collection("deal_stage_history")
    for snap in history.where(filter=FieldFilter("deal_id", "==", deal_id)).stream():
        if snap.to_dict().get("exited_at") is None:
            batch.update(snap.reference, {"exited_at": _now()})
    stage_id = new_id()
    batch.set(history.document(stage_id), {"id": stage_id, "deal_id": deal_id, "stage": new_stage,
              "entered_at": _now(), "exited_at": None, "trigger_input_id": trigger_input_id})
    batch.update(_collection("deals").document(deal_id), {"stage": new_stage, "updated_at": _now()})
    batch.commit()


def get_thread(thread_id):
    return sorted(_where("inputs", "thread_id", thread_id), key=lambda r: r.get("occurred_at", ""))


def get_deal_timeline(deal_id):
    return sorted(_where("inputs", "deal_id", deal_id), key=lambda r: r.get("occurred_at", ""))


def find_person_by_email(email):
    return next(iter(_where("people", "email", email)), None)


def add_person(name, email=None, org=None):
    person_id = new_id()
    _save("people", person_id, {"id": person_id, "name": name, "email": email, "org": org})
    return person_id


def link_person_to_deal(deal_id, person_id, role=None):
    _save("deal_people", f"{deal_id}__{person_id}", {"deal_id": deal_id, "person_id": person_id, "role": role}, merge=True)


def get_deals_for_person(person_id):
    return [r["deal_id"] for r in _where("deal_people", "person_id", person_id)]


def add_reasoning_node(deal_id, trigger, reasoning, parent_reasoning_id=None):
    reasoning_id = new_id()
    _save("reasoning_chain", reasoning_id, {"id": reasoning_id, "deal_id": deal_id,
          "parent_reasoning_id": parent_reasoning_id, "trigger": trigger,
          "reasoning": reasoning, "created_at": _now()})
    return reasoning_id


def get_latest_reasoning(deal_id):
    rows = _where("reasoning_chain", "deal_id", deal_id)
    return max(rows, key=lambda r: r.get("created_at", ""), default=None)


def get_reasoning_chain(deal_id):
    return sorted(_where("reasoning_chain", "deal_id", deal_id), key=lambda r: r.get("created_at", ""))


def get_stage_history(deal_id):
    return sorted(_where("deal_stage_history", "deal_id", deal_id), key=lambda r: r.get("entered_at", ""))


def get_deal(deal_id):
    return _get("deals", deal_id)


def get_input_by_message_id(message_id):
    return next(iter(_where("inputs", "message_id", message_id)), None)


def already_ingested(message_id=None, raw_ref=None):
    return bool((message_id and _where("inputs", "message_id", message_id)) or
                (raw_ref and _where("inputs", "raw_ref", raw_ref)))


def get_people_for_deal(deal_id):
    links = _where("deal_people", "deal_id", deal_id)
    people = {link["person_id"]: _get("people", link["person_id"]) for link in links}
    result = []
    for link in links:
        person = people.get(link["person_id"])
        if person:
            result.append({key: person.get(key) for key in ("id", "name", "email", "org")} | {"role": link.get("role")})
    return sorted(result, key=lambda row: row.get("name", ""))


def set_person_role(deal_id, person_id, role):
    _save("deal_people", f"{deal_id}__{person_id}", {"deal_id": deal_id, "person_id": person_id, "role": role}, merge=True)


def add_review(deal_id, note):
    review_id = new_id()
    _save("reviews", review_id, {"id": review_id, "deal_id": deal_id, "note": note, "created_at": _now()})
    return review_id


def list_reviews(deal_id):
    return sorted(_where("reviews", "deal_id", deal_id), key=lambda r: r.get("created_at", ""), reverse=True)


def list_signals(deal_id):
    return sorted(_where("signals", "deal_id", deal_id), key=lambda r: r.get("created_at", ""))


def days_since_last_input(deal_id):
    timeline = get_deal_timeline(deal_id)
    last_at = max((row.get("occurred_at", "") for row in timeline), default="")
    if not last_at:
        last_at = (get_deal(deal_id) or {}).get("updated_at", "")
    if not last_at:
        return None
    try:
        last = datetime.fromisoformat(last_at.replace("Z", "").split(".")[0])
    except ValueError:
        last = datetime.strptime(last_at[:19], "%Y-%m-%d %H:%M:%S")
    return max(0, (datetime.utcnow() - last).days)


def add_chat_message(deal_id, role, content):
    message_id = new_id()
    _save("chat_messages", message_id, {"id": message_id, "deal_id": deal_id,
          "role": role, "content": content, "created_at": _now()})
    return message_id


def get_chat_history(deal_id):
    return sorted(_where("chat_messages", "deal_id", deal_id), key=lambda r: r.get("created_at", ""))


def list_open_deals():
    from google.cloud.firestore_v1.base_query import FieldFilter
    return [snap.to_dict() for snap in _collection("deals").where(filter=FieldFilter("outcome", "==", None)).stream()]


def list_deals():
    return sorted(_all("deals"), key=lambda row: row.get("updated_at", ""), reverse=True)


def list_unread_notifications(deal_id=None):
    rows = _where("notifications", "read", 0)
    if deal_id is not None:
        rows = [row for row in rows if row.get("deal_id") == deal_id]
    return sorted(rows, key=lambda r: r.get("created_at", ""), reverse=True)


def add_notification(deal_id, kind, message, input_id=None):
    notification_id = new_id()
    _save("notifications", notification_id, {"id": notification_id, "deal_id": deal_id,
          "input_id": input_id, "kind": kind, "message": message, "read": 0, "created_at": _now()})
    return notification_id


def mark_notification_read(notification_id):
    _collection("notifications").document(notification_id).update({"read": 1})


def update_deal_outcome(deal_id, outcome, outcome_reason=None):
    _collection("deals").document(deal_id).update({"outcome": outcome, "outcome_reason": outcome_reason, "updated_at": _now()})
    return get_deal(deal_id)


def upsert_hindsight_record(deal_id, stage, outcome, outcome_reason, signals):
    _save("hindsight_records", deal_id, {"deal_id": deal_id, "stage_reached": stage,
          "outcome": outcome, "outcome_reason": outcome_reason,
          "signal_summary": json.dumps(signals), "written_at": _now()}, merge=True)


def list_hindsight_records():
    records = _all("hindsight_records")
    deal_ids = {row.get("deal_id") for row in records}
    deals = {deal_id: _get("deals", deal_id) for deal_id in deal_ids}
    rows = []
    for record in records:
        deal = deals.get(record.get("deal_id")) or {}
        rows.append({key: record.get(key) for key in ("deal_id", "stage_reached", "outcome", "outcome_reason", "signal_summary", "written_at")} | {"name": deal.get("name")})
    return sorted(rows, key=lambda row: row.get("written_at", ""), reverse=True)


def save_hindsight_vector(deal_id, text, metadata):
    _save("hindsight_vectors", deal_id, {"deal_id": deal_id, "text": text, "metadata": metadata})


def get_hindsight_vectors():
    return _all("hindsight_vectors")
