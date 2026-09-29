"""
Meeting records connector. Reads local meeting notes/minutes (markdown or
plain text) — same pattern as voice notes, kept separate since meeting notes
are usually human-written summaries, not raw transcripts.
"""
from pathlib import Path
from .base import BaseConnector, RawItem


class MeetingConnector(BaseConnector):
    source_name = "meeting"

    def __init__(self, notes_dir: str):
        self.notes_dir = Path(notes_dir)

    def fetch_new(self, deal_id: str) -> list[RawItem]:
        items = []
        deal_dir = self.notes_dir / deal_id
        if not deal_dir.exists():
            return items
        for f in sorted(deal_dir.glob("*.md")):
            items.append(
                RawItem(source=self.source_name, content=f.read_text(), occurred_at="", raw_ref=str(f))
            )
        return items
