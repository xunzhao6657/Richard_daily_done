from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from .util import sha256_bytes


def _published_candidates(root: Path, report_date: str, mode: str) -> list[Path]:
    candidates = list(root.glob(f"{mode}/{report_date}/*/publication.json"))
    candidates += list(root.glob(f"**/{report_date}/*/publication.json"))
    return sorted(set(candidates), key=lambda path: path.stat().st_mtime, reverse=True)


def load_morning_forecast(root: Path | None, report_date: str, mode: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if root is None or not root.exists():
        return None, {"provider": "morning-forecast", "status": "NOT_AVAILABLE", "reason": "ROOT_NOT_CONFIGURED"}
    for publication_path in _published_candidates(root, report_date, mode):
        try:
            publication = json.loads(publication_path.read_text(encoding="utf-8-sig"))
            if publication.get("report_date") != report_date or publication.get("mode") != mode:
                continue
            forecast_path = Path(publication["forecast_path"])
            if not forecast_path.exists():
                forecast_path = publication_path.parent / "forecast.json"
            digest = sha256_bytes(forecast_path.read_bytes())
            if digest != publication.get("forecast_sha256"):
                return None, {"provider": "morning-forecast", "status": "INVALID", "reason": "HASH_MISMATCH"}
            forecast = json.loads(forecast_path.read_text(encoding="utf-8-sig"))
            return forecast, {
                "provider": "morning-forecast",
                "status": "OK",
                "reason": "PUBLISHED_HASH_VERIFIED",
                "publication_id": publication.get("publication_id"),
                "forecast_sha256": digest,
            }
        except (OSError, KeyError, ValueError, json.JSONDecodeError):
            continue
    return None, {"provider": "morning-forecast", "status": "NOT_AVAILABLE", "reason": "NO_PUBLISHED_FORECAST"}


def _actual_market(market: dict[str, Any]) -> dict[str, Decimal]:
    actual: dict[str, Decimal] = {"turnover": Decimal(market["turnover_yi"])}
    for item in market["indexes"]:
        if item["windcode"] == "000001.SH":
            actual["sse_close"] = Decimal(item["close"])
            actual["sse_return"] = Decimal(item["return_pct"])
            actual["sse_direction"] = Decimal(item["return_pct"])
    return actual


def compare_forecast(forecast: dict[str, Any] | None, market: dict[str, Any] | None, source: dict[str, Any]) -> list[dict[str, Any]]:
    target_names = ["sse_return", "sse_close", "sse_direction", "turnover", "style", "sector_rank", "fund_flow", "hsi_return", "hsi_close", "scenario"]
    if forecast is None:
        return [{
            "comparison_id": f"CMP{index:03d}", "target_id": target, "status": "NA",
            "forecast_display": "未取得已发表晨报预测", "actual_display": "未比较",
            "verdict": "NA", "reason_codes": [source["reason"]], "is_preliminary": True,
        } for index, target in enumerate(target_names, 1)]
    actuals = _actual_market(market) if market else {}
    comparisons: list[dict[str, Any]] = []
    for index, target_id in enumerate(target_names, 1):
        target = forecast.get("targets", {}).get(target_id, {})
        comparison = {
            "comparison_id": f"CMP{index:03d}", "target_id": target_id, "status": "NA",
            "forecast_display": "未预测", "actual_display": "未比较", "verdict": "NOT_PREDICTED",
            "reason_codes": [], "is_preliminary": True,
        }
        if target.get("status") != "VALID":
            comparison["reason_codes"] = target.get("reason_codes", ["NOT_PREDICTED"])
        elif target_id not in actuals:
            comparison.update({"forecast_display": str(target.get("display_values", {})), "verdict": "NA", "reason_codes": ["ACTUAL_OR_RULE_UNAVAILABLE"]})
        else:
            display_values = target.get("display_values", {})
            comparison["forecast_display"] = str(display_values)
            comparison["actual_display"] = str(actuals[target_id])
            comparison["status"] = "MEASURED"
            if target_id in {"sse_return", "sse_close", "turnover"} and target.get("q50") is not None:
                predicted = Decimal(str(target["q50"]))
                error = actuals[target_id] - predicted
                comparison["verdict"] = "OBJECTIVE_ERROR_ONLY"
                comparison["error"] = str(error)
                comparison["reason_codes"] = ["NO_PREREGISTERED_HIT_THRESHOLD"]
            elif target_id == "sse_direction":
                probabilities = target.get("probabilities", {})
                predicted_direction = max(probabilities, key=probabilities.get) if probabilities else None
                actual_direction = "up" if actuals[target_id] > 0 else "down" if actuals[target_id] < 0 else "flat"
                comparison["verdict"] = "HIT" if predicted_direction == actual_direction else "MISS"
                comparison["predicted_direction"] = predicted_direction
                comparison["actual_direction"] = actual_direction
            else:
                comparison["verdict"] = "NA"
                comparison["reason_codes"] = ["RULE_UNAVAILABLE"]
        comparisons.append(comparison)
    return comparisons

