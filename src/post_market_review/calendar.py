from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path


class CalendarError(ValueError):
    pass


@dataclass(frozen=True)
class Session:
    report_date: date
    is_open: bool
    next_session: date | None
    source: str
    source_version: str


class TradingCalendar:
    def __init__(self, path: Path):
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = [row for row in csv.DictReader(handle) if row["market"] == "CN"]
        self.rows = {date.fromisoformat(row["session_date"]): row for row in rows}
        self.open_dates = sorted(day for day, row in self.rows.items() if row["status"] == "OPEN")

    def get(self, day: date) -> Session:
        if day not in self.rows:
            raise CalendarError("UNKNOWN_CALENDAR")
        row = self.rows[day]
        following = next((candidate for candidate in self.open_dates if candidate > day), None)
        return Session(day, row["status"] == "OPEN", following, row["source"], row["source_version"])
