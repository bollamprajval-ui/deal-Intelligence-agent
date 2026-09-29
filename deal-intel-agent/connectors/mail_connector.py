"""
Mail connector. Reads locally-synced email (e.g. from a local IMAP cache or
exported .eml files) — never calls a cloud mail API at extraction time.
Replace `_read_local_mailbox` with your actual local mail source.
"""
from .base import BaseConnector, RawItem


class MailConnector(BaseConnector):
    source_name = "mail"

    def __init__(self, mailbox_path: str):
        self.mailbox_path = mailbox_path

    def fetch_new(self, deal_id: str) -> list[RawItem]:
        raw_emails = self._read_local_mailbox(deal_id)
        return [
            RawItem(
                source=self.source_name,
                content=email["body"],
                occurred_at=email["date"],
                raw_ref=email.get("path"),
            )
            for email in raw_emails
        ]

    def _read_local_mailbox(self, deal_id: str) -> list[dict]:
        # TODO: read .eml files / local IMAP cache filtered to this deal's thread
        return []
