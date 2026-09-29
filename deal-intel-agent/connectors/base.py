"""
Every connector (mail, voice notes, spreadsheets, meetings) implements this
interface. The pipeline never depends on a specific tool — only on this shape.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class RawItem:
    """One unit of raw input pulled from a tool, before AI extraction."""
    source: str            # 'mail' / 'voice_note' / 'spreadsheet' / 'meeting'
    content: str            # raw text (transcript, email body, cell dump, etc.)
    occurred_at: str        # ISO timestamp
    raw_ref: Optional[str] = None   # local file path, if kept
    message_id: Optional[str] = None     # mail Message-ID header, if applicable
    in_reply_to: Optional[str] = None    # mail In-Reply-To header, if applicable
    sender_email: Optional[str] = None   # who sent it, for person matching


class BaseConnector(ABC):
    source_name: str = "base"

    @abstractmethod
    def fetch_new(self, deal_id: str) -> list[RawItem]:
        """Pull unseen raw items for this deal from the tool. Must run fully offline
        against locally synced/cached data — the connector's job is reading what's
        already on disk, not making network calls at extraction time."""
        raise NotImplementedError
