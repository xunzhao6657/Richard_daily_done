from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from post_market_review.comparison import load_morning_forecast


class ComparisonTests(unittest.TestCase):
    def test_a10_only_published_matching_hash_is_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            published = root / "shadow" / "2026-09-09" / "run-one"
            published.mkdir(parents=True)
            forecast_path = published / "forecast.json"
            forecast_path.write_text('{"targets":{}}', encoding="utf-8")
            digest = hashlib.sha256(forecast_path.read_bytes()).hexdigest()
            publication = {"report_date": "2026-09-09", "mode": "shadow", "forecast_path": str(forecast_path), "forecast_sha256": digest, "publication_id": "p1"}
            (published / "publication.json").write_text(json.dumps(publication), encoding="utf-8")
            forecast, state = load_morning_forecast(root, "2026-09-09", "shadow")
            self.assertEqual(forecast, {"targets": {}})
            self.assertEqual(state["status"], "OK")
            forecast_path.write_text('{"targets":{"changed":{}}}', encoding="utf-8")
            forecast, state = load_morning_forecast(root, "2026-09-09", "shadow")
            self.assertIsNone(forecast)
            self.assertEqual(state["reason"], "HASH_MISMATCH")


if __name__ == "__main__":
    unittest.main()
