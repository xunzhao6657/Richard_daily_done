from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from post_market_review.comparison import compare_forecast, load_morning_forecast
from tests.helpers import market


class ComparisonTests(unittest.TestCase):
    def test_institutional_scoring_uses_nested_values_and_correct_units(self) -> None:
        forecast = {
            "schema_version": "forecast.v2",
            "targets": {
                "sse_return": {
                    "status": "VALID", "unit": "decimal_return",
                    "values": {"q10": "-0.01", "q25": "0", "q50": "0.002", "q75": "0.004", "q90": "0.01"},
                    "display_values": {"q10": "-1.00%", "q25": "0.00%", "q50": "0.20%", "q75": "0.40%", "q90": "1.00%"},
                    "conformal": {"status": "VALID", "coverage_target": "0.80", "lower": "-0.02", "upper": "0.02"},
                },
                "sse_direction": {
                    "status": "VALID", "values": {"classes": [
                        {"class_id": "up", "probability_decimal": "0.6", "display_probability": "60%"},
                        {"class_id": "flat", "probability_decimal": "0.1", "display_probability": "10%"},
                        {"class_id": "down", "probability_decimal": "0.3", "display_probability": "30%"}
                    ]}, "display_values": {"up": "60%", "flat": "10%", "down": "30%"}, "conformal": None,
                },
            },
            "governance": {},
        }
        results = compare_forecast(forecast, market(), {"reason": "OK"})
        by_target = {item["target_id"]: item for item in results}
        self.assertAlmostEqual(by_target["sse_return"]["metrics"]["mae"], 0.0003)
        self.assertEqual(by_target["sse_return"]["actual_display"], "0.23%")
        self.assertEqual(by_target["sse_direction"]["verdict"], "HIT")
        self.assertIn("brier", by_target["sse_direction"]["metrics"])

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
