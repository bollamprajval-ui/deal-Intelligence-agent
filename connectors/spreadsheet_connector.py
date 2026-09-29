"""
Spreadsheet connector. Reads local .xlsx/.csv files (budgets, pricing sheets)
and flattens rows into text the extraction step can summarize.
"""
from pathlib import Path
import csv
from .base import BaseConnector, RawItem


class SpreadsheetConnector(BaseConnector):
    source_name = "spreadsheet"

    def __init__(self, sheets_dir: str):
        self.sheets_dir = Path(sheets_dir)

    def fetch_new(self, deal_id: str) -> list[RawItem]:
        items = []
        deal_dir = self.sheets_dir / deal_id
        if not deal_dir.exists():
            return items
        for f in sorted(deal_dir.glob("*.csv")):
            content = self._flatten_csv(f)
            items.append(
                RawItem(source=self.source_name, content=content, occurred_at="", raw_ref=str(f))
            )
        return items

    def _flatten_csv(self, path: Path) -> str:
        with open(path) as fh:
            rows = list(csv.reader(fh))
        return "\n".join(", ".join(row) for row in rows)
