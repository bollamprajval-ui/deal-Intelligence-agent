"""
Every notable event writes a notification row. This module doesn't push
(email/SMS/etc) yet — it's the single place events land, so a future
push channel (desktop notif, mail digest) has one thing to read from.
"""
from core.db import add_notification, list_unread_notifications, mark_notification_read


def notify(deal_id: str, kind: str, message: str, input_id: str = None):
    add_notification(deal_id, kind, message, input_id)


def list_unread(deal_id: str = None):
    return list_unread_notifications(deal_id)


def mark_read(notification_id: str):
    mark_notification_read(notification_id)
