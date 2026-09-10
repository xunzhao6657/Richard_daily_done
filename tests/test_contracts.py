from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from post_market_review.analysis import empirical_percentile, sentiment_temperature
from post_market_review.calendar import CalendarError, TradingCalendar
from post_market_review.research import DeepSeekClient, ResearchError, assert_outbound_safe, validate_research
from post_market_review.util import amount_to_yi
from post_market_review.wind import close_crosscheck

from tests.helpers import runtime


class ContractTests(unittest.TestCase):
    def test_model_probe_accepts_only_configured_backend_alias(self) -> None:
        class Response:
            def __init__(self, model: str):
                self.model = model

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self) -> bytes:
                return json.dumps({
                    "model": self.model,
                    "choices": [{"finish_reason": "stop", "message": {"content": '{"status":"ok"}'}}],
                }).encode("utf-8")

        with tempfile.TemporaryDirectory() as temporary:
            config = runtime(Path(temporary))
            client = DeepSeekClient(config.raw["llm"], Path(temporary) / "unused", "test", Path(temporary))
            with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}), patch(
                "urllib.request.urlopen", return_value=Response("deepseek-flash")
            ):
                self.assertEqual(client.probe()["status"], "PASS")
            with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}), patch(
                "urllib.request.urlopen", return_value=Response("unlisted-model")
            ):
                with self.assertRaisesRegex(ResearchError, "MODEL_NOT_AVAILABLE"):
                    client.probe()

    def test_a01_calendar_open_closed_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = runtime(Path(temporary))
            calendar = TradingCalendar(config.root / "config" / "trading_sessions.csv")
            self.assertTrue(calendar.get(date(2026, 9, 9)).is_open)
            self.assertFalse(calendar.get(date(2026, 9, 12)).is_open)
            with self.assertRaises(CalendarError):
                calendar.get(date(2027, 1, 1))

    def test_a05_amount_units_are_explicit(self) -> None:
        self.assertEqual(amount_to_yi("1万亿", "x"), Decimal("10000"))
        self.assertEqual(amount_to_yi("1亿元", "x"), Decimal("1"))
        self.assertEqual(amount_to_yi("10000万元", "x"), Decimal("1"))

    def test_a04_crosscheck_boundary_and_same_provider_label(self) -> None:
        self.assertEqual(close_crosscheck(Decimal("100"), Decimal("100.05"))["status"], "SAME_PROVIDER_CONSISTENT")
        self.assertEqual(close_crosscheck(Decimal("100"), Decimal("100.05001"))["status"], "CONFLICT")
        self.assertEqual(close_crosscheck(Decimal("0"), Decimal("0"))["status"], "NOT_COMPARABLE")

    def test_a08_sentiment_formula_and_missing(self) -> None:
        history = [{key: Decimal(index) for key in ("limit_up", "blast_rate", "limit_down", "volume_ratio", "advance_ratio")} for index in range(60)]
        current = {key: Decimal("30") for key in history[0]}
        result = sentiment_temperature(current, history)
        self.assertEqual(result["status"], "VALID")
        self.assertEqual(result["score"], "50.2")
        self.assertEqual(empirical_percentile(Decimal("30"), [Decimal(index) for index in range(60)]), Decimal("50.83333333333333333333333333"))
        current["blast_rate"] = None
        self.assertIsNone(sentiment_temperature(current, history)["score"])

    def test_a13_nested_outbound_secrets_and_paths_blocked(self) -> None:
        with self.assertRaises(ResearchError):
            assert_outbound_safe({"safe": [{"reason": "ak_" + "1234567890123456secret"}]})
        with self.assertRaises(ResearchError):
            assert_outbound_safe({"safe": "C:\\private\\raw.json"})
        with self.assertRaises(ResearchError):
            assert_outbound_safe({"nested": {"raw_path": "hidden"}})

    def test_a11_model_numeric_hallucination_rejected(self) -> None:
        evidence = {
            "evidence_hash": "h", "next_session": "2026-09-10",
            "facts": [{"evidence_id": "F001", "display_value": "1%", "allowed_section_ids": ["S1"]}], "comparisons": [],
        }
        payload = {
            "prompt_version": "review.research.v1", "evidence_hash": "h", "limitations": [], "watch_items": [],
            "claims": [{"claim_id": "C1", "section_id": "S1", "claim_type": "INTERPRETATION", "text_template": "上涨了2%", "evidence_ids": ["F001"], "uncertainties": [], "causal_strength": "DESCRIPTIVE"}],
        }
        claims, _, rejected = validate_research(payload, evidence)
        self.assertEqual(claims, [])
        self.assertIn("C1:RAW_NUMBER", rejected)

    def test_schema_files_are_valid_json_and_strict_at_top(self) -> None:
        root = Path(__file__).resolve().parents[1] / "schemas"
        for path in root.glob("*.json"):
            schema = json.loads(path.read_text(encoding="utf-8"))
            self.assertFalse(schema["additionalProperties"], path.name)


if __name__ == "__main__":
    unittest.main()
