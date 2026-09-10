from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from .institutional import actual_market_values, score_target
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


def compare_forecast(forecast: dict[str, Any] | None, market: dict[str, Any] | None, source: dict[str, Any]) -> list[dict[str, Any]]:
    target_names = ["sse_return", "sse_close", "sse_direction", "turnover", "style", "sector_rank", "fund_flow", "hsi_return", "hsi_close", "scenario"]
    if forecast is None:
        return [{
            "comparison_id": f"CMP{index:03d}", "target_id": target, "status": "NA",
            "forecast_display": "未取得已发表晨报预测", "actual_display": "未比较",
            "verdict": "NA", "reason_codes": [source["reason"]], "is_preliminary": True,
        } for index, target in enumerate(target_names, 1)]
    actuals, actual_display = actual_market_values(market)
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
            comparison["actual_display"] = actual_display[target_id]
            comparison["status"] = "MEASURED"
            metrics = score_target(target, actuals[target_id])
            comparison["metrics"] = metrics
            if metrics.get("mae") is not None:
                comparison["verdict"] = "OBJECTIVE_ERROR_ONLY"
                comparison["reason_codes"] = ["NO_PREREGISTERED_HIT_THRESHOLD"]
            elif metrics.get("predicted_class"):
                comparison["verdict"] = "HIT" if metrics["predicted_class"] == metrics["actual_class"] else "MISS"
            else:
                comparison["verdict"] = "NA"
                comparison["reason_codes"] = [metrics.get("reason", "RULE_UNAVAILABLE")]
        comparisons.append(comparison)
    return comparisons
