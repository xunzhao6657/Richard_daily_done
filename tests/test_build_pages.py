from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.archive_pages_reports import archive_reports
from scripts.build_pages import build_site


HTML = '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>{}</title></head><body>{}</body></html>'


class PagesBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "published-reports"
        self.output = self.root / "public"
        self.now = datetime(2026, 9, 11, 8, 5, tzinfo=timezone(timedelta(hours=8)))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def add(self, day: str, kind: str, body: str = "中文 ↑ ↓ 1.2% 亿元") -> Path:
        compact = day.replace("-", "")
        path = self.source / compact[:4] / compact[4:6] / compact / f"{kind}.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(HTML.format(kind, body), encoding="utf-8")
        return path

    def build(self):
        return build_site(self.source, self.output, self.now)

    def test_both_morning_and_review_are_built(self) -> None:
        self.add("2026-09-10", "morning")
        self.add("2026-09-10", "review")
        self.build()
        self.assertTrue((self.output / "latest" / "morning.html").is_file())
        self.assertTrue((self.output / "latest" / "review.html").is_file())

    def test_only_morning_gets_review_placeholder(self) -> None:
        self.add("2026-09-10", "morning")
        self.build()
        self.assertIn("今日收盘复盘尚未生成", (self.output / "latest" / "review.html").read_text(encoding="utf-8"))

    def test_only_review_gets_morning_placeholder(self) -> None:
        self.add("2026-09-10", "review")
        self.build()
        self.assertIn("今日晨报尚未生成", (self.output / "latest" / "morning.html").read_text(encoding="utf-8"))

    def test_cross_month_history_is_preserved(self) -> None:
        self.add("2026-08-31", "review")
        self.add("2026-09-01", "review")
        self.build()
        self.assertTrue((self.output / "reports" / "2026" / "08" / "20260831" / "review.html").is_file())
        self.assertTrue((self.output / "reports" / "2026" / "09" / "20260901" / "review.html").is_file())

    def test_cross_year_history_is_preserved(self) -> None:
        self.add("2025-12-31", "morning")
        self.add("2026-01-02", "morning")
        self.build()
        index = (self.output / "index.html").read_text(encoding="utf-8")
        self.assertLess(index.index("2026-01-02"), index.index("2025-12-31"))

    def test_chinese_review_filename_is_archived(self) -> None:
        raw = self.root / "raw" / "review" / "shadow" / "2026-09-10" / "run-1"
        raw.mkdir(parents=True)
        report = raw / "2026年9月10日A股收盘总结.html"
        report.write_text(HTML.format("复盘", "中文报告"), encoding="utf-8")
        digest = hashlib.sha256(report.read_bytes()).hexdigest()
        (raw / "publication.json").write_text(json.dumps({
            "schema_version": "review.publication.v1", "report_date": "2026-09-10", "slot": "20:00",
            "mode": "shadow", "published_at": "2026-09-10T20:00:00+08:00", "artifact_hashes": {"html": digest},
        }), encoding="utf-8")
        archived = archive_reports([self.root / "raw"], self.source)
        self.assertEqual(1, len(archived))
        self.assertTrue((self.source / "2026" / "09" / "20260910" / "review.html").is_file())

    def test_empty_directory_builds_friendly_latest_pages(self) -> None:
        self.build()
        self.assertTrue((self.output / "index.html").is_file())
        self.assertTrue((self.output / ".nojekyll").is_file())
        self.assertIn("暂无已归档报告", (self.output / "index.html").read_text(encoding="utf-8"))

    def test_unrelated_html_is_ignored(self) -> None:
        self.source.mkdir(parents=True)
        (self.source / "random.html").write_text(HTML.format("无关", "ignore"), encoding="utf-8")
        reports = self.build()
        self.assertEqual([], reports)
        self.assertFalse((self.output / "random.html").exists())

    def test_latest_is_selected_independently_for_each_kind(self) -> None:
        self.add("2026-09-09", "morning", "morning-old")
        self.add("2026-09-11", "morning", "morning-new")
        self.add("2026-09-10", "review", "review-new")
        self.build()
        self.assertIn("morning-new", (self.output / "latest" / "morning.html").read_text(encoding="utf-8"))
        self.assertIn("review-new", (self.output / "latest" / "review.html").read_text(encoding="utf-8"))

    def test_project_pages_links_are_relative_and_resolve(self) -> None:
        self.add("2026-09-10", "morning")
        self.build()
        index = (self.output / "index.html").read_text(encoding="utf-8")
        self.assertNotIn('href="/', index)
        self.assertIn('href="./latest/morning.html"', index)
        self.assertTrue((self.output / "latest" / "morning.html").is_file())

    def test_sensitive_html_is_rejected(self) -> None:
        self.add("2026-09-10", "morning", "DEEPSEEK_API_KEY=secret")
        with self.assertRaises(ValueError):
            self.build()


if __name__ == "__main__":
    unittest.main()
