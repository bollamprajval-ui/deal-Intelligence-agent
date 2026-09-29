"""
Every notable event writes a notification row. This module doesn't push
(email/SMS/etc) yet — it's the single place events land, so a future
push channel (desktop notif, mail digest) has one thing to read from.
"""
from core.db import get_conn, new_id


def notify(deal_id: str, kind: str, message: str, input_id: str = None):
    conn = get_conn()
    conn.execute(
        "INSERT INTO notifications (id, deal_id, input_id, kind, message) VALUES (?, ?, ?, ?, ?)",
        (new_id(), deal_id, input_id, kind, message),
    )
    conn.commit()
    conn.close()


def list_unread(deal_id: str = None):
    conn = get_conn()
    if deal_id:
        rows = conn.execute(
            "SELECT * FROM notifications WHERE deal_id = ? AND read = 0 ORDER BY created_at DESC", (deal_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM notifications WHERE read = 0 ORDER BY created_at DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_read(notification_id: str):
    conn = get_conn()
    conn.execute("UPDATE notifications SET read = 1 WHERE id = ?", (notification_id,))
    conn.commit()
    conn.close()
