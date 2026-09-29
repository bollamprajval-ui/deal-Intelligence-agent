"""
Voice notes / call recordings connector. Expects audio already transcribed
locally (e.g. via whisper.cpp) into .txt files sitting next to the audio.
"""
from pathlib import Path
from .base import BaseConnector, RawItem


class VoiceConnector(BaseConnector):
    source_name = "voice_note"

    def __init__(self, transcripts_dir: str):
        self.transcripts_dir = Path(transcripts_dir)

    def fetch_new(self, deal_id: str) -> list[RawItem]:
        items = []
        deal_dir = self.transcripts_dir / deal_id
        if not deal_dir.exists():
            return items
        for f in sorted(deal_dir.glob("*.txt")):
            items.append(
                RawItem(
                    source=self.source_name,
                    content=f.read_text(),
                    occurred_at=self._occurred_at_from_filename(f.name),
                    raw_ref=str(f),
                )
            )
        return items

    def _occurred_at_from_filename(self, name: str) -> str:
        # TODO: parse timestamp out of your transcript naming convention
        return ""
