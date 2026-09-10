from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

from docx import Document

from post_market_review.pipeline import PipelineError, prepare, publish, replay, watchdog
from post_market_review.util import BJ

from tests.helpers import market, runtime


class PipelineTests(unittest.TestCase):
    def test_a02_a03_a15_a19_three_formats_failure_and_idempotency(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = runtime(Path(temporary))
            clock_prepare = lambda: datetime(2026, 9, 9, 19, 42, tzinfo=BJ)
            states = [{"provider": "wind:market_overview", "status": "OK", "reason": "NORMALIZED"}]
            with patch("post_market_review.pipeline.collect_wind", return_value=(market(), [], states)):
                ready = prepare(config, date(2026, 9, 9), "shadow", clock_prepare)
            self.assertEqual(ready["status"], "READY")
            staging = Path(ready["ready_path"]).parent
            markdown = next(staging.glob("*.md"))
            html = next(staging.glob("*.html"))
            docx = next(staging.glob("*.docx"))
            self.assertEqual(markdown.read_text(encoding="utf-8").count("\n## "), 8)
            self.assertIn("<table>", html.read_text(encoding="utf-8"))
            document = Document(docx)
            self.assertTrue(any("A股每日收盘复盘" in paragraph.text for paragraph in document.paragraphs))
            clock_publish = lambda: datetime(2026, 9, 9, 20, 0, tzinfo=BJ)
            first = publish(config, date(2026, 9, 9), "shadow", clock_publish)
            second = publish(config, date(2026, 9, 9), "shadow", clock_publish)
            self.assertEqual(first["publication_id"], second["publication_id"])
            self.assertEqual(watchdog(config, date(2026, 9, 9), "shadow")["status"], "PASS")
            self.assertEqual(replay(config, ready["run_id"])["status"], "PASS")

            failure_root = Path(temporary) / "failure"
            failure_config = runtime(failure_root)
            with patch("post_market_review.pipeline.collect_wind", return_value=(None, [], [{"provider": "wind", "status": "ERROR", "reason": "NETWORK_ERROR"}])):
                failure = prepare(failure_config, date(2026, 9, 9), "shadow", clock_prepare)
            self.assertEqual(failure["report_status"], "FAILURE_BULLETIN")
            self.assertTrue(next(Path(failure["ready_path"]).parent.glob("*.docx")).exists())

    def test_a07_cutoff_and_publication_windows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = runtime(Path(temporary))
            at_cutoff = market("2026-09-09T19:45:00+08:00")
            with patch("post_market_review.pipeline.collect_wind", return_value=(at_cutoff, [], [])):
                ready = prepare(config, date(2026, 9, 9), "shadow", lambda: datetime(2026, 9, 9, 19, 45, tzinfo=BJ))
            self.assertEqual(ready["status"], "READY")
            with self.assertRaises(PipelineError):
                publish(config, date(2026, 9, 9), "shadow", lambda: datetime(2026, 9, 9, 19, 59, 59, tzinfo=BJ))
            with self.assertRaises(PipelineError):
                publish(config, date(2026, 9, 9), "shadow", lambda: datetime(2026, 9, 9, 21, 0, 1, tzinfo=BJ))


if __name__ == "__main__":
    unittest.main()
