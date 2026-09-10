from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

from .util import sha256_json


def _float(value: Any) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("non-finite number")
    return number


def score_target(target: dict[str, Any], actual: Any) -> dict[str, Any]:
    if target.get("status") != "VALID":
        return {"status": "NOT_EVALUABLE", "reason": "FORECAST_NOT_VALID"}
    values = target.get("values") or {}
    if "classes" in values:
        probabilities = {item["class_id"]: _float(item["probability_decimal"]) for item in values["classes"]}
        actual_class = str(actual)
        if actual_class not in probabilities:
            return {"status": "NOT_EVALUABLE", "reason": "ACTUAL_CLASS_UNKNOWN"}
        return {
            "status": "MEASURED",
            "brier": sum((probability - (1.0 if name == actual_class else 0.0)) ** 2 for name, probability in probabilities.items()),
            "log_loss": -math.log(max(probabilities[actual_class], 1e-15)),
            "predicted_class": max(probabilities, key=probabilities.get), "actual_class": actual_class,
        }
    required = ("q10", "q25", "q50", "q75", "q90")
    if not all(name in values for name in required):
        return {"status": "NOT_EVALUABLE", "reason": "QUANTILES_MISSING"}
    quantiles = {name: _float(values[name]) for name in required}
    observed = _float(actual)
    losses = []
    for name, tau in (("q10", 0.10), ("q25", 0.25), ("q50", 0.50), ("q75", 0.75), ("q90", 0.90)):
        residual = observed - quantiles[name]
        losses.append(max(tau * residual, (tau - 1) * residual))
    result: dict[str, Any] = {
        "status": "MEASURED", "mae": abs(observed - quantiles["q50"]),
        "squared_error": (observed - quantiles["q50"]) ** 2,
        "pinball": sum(losses) / len(losses),
    }
    conformal = target.get("conformal")
    if isinstance(conformal, dict) and conformal.get("status") == "VALID":
        lower, upper = _float(conformal["lower"]), _float(conformal["upper"])
        alpha = 1 - _float(conformal["coverage_target"])
        coverage = 1.0 if lower <= observed <= upper else 0.0
        winkler = upper - lower
        if observed < lower:
            winkler += (2 / alpha) * (lower - observed)
        elif observed > upper:
            winkler += (2 / alpha) * (observed - upper)
        result.update({"coverage": coverage, "interval_width": upper - lower, "winkler": winkler})
    return result


def actual_market_values(market: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, str]]:
    if not market:
        return {}, {}
    values: dict[str, Any] = {"turnover": Decimal(market["turnover_yi"]) * Decimal("100000000")}
    display: dict[str, str] = {"turnover": f"{market['turnover_yi']}亿元"}
    for item in market["indexes"]:
        if item["windcode"] == "000001.SH":
            decimal_return = Decimal(item["return_pct"]) / Decimal("100")
            values.update({"sse_close": Decimal(item["close"]), "sse_return": decimal_return, "sse_direction": "up" if decimal_return > 0 else "down" if decimal_return < 0 else "flat"})
            display.update({"sse_close": f"{item['close']}点", "sse_return": f"{item['return_pct']}%", "sse_direction": values["sse_direction"]})
    return values, display


def institutional_review(forecast: dict[str, Any] | None, comparisons: list[dict[str, Any]]) -> dict[str, Any]:
    measured = [item for item in comparisons if item.get("metrics", {}).get("status") == "MEASURED"]
    governance = forecast.get("governance", {}) if forecast else {}
    model = governance.get("production_model", {})
    calibration = governance.get("calibration", {})
    monitoring = governance.get("model_monitoring", {})
    queue: list[dict[str, Any]] = []
    for item in measured:
        metrics = item["metrics"]
        error_type = None
        if metrics.get("coverage") == 0:
            error_type = "C"
            issue = "实际值落在已登记Conformal区间之外"
        elif metrics.get("predicted_class") and metrics.get("predicted_class") != metrics.get("actual_class"):
            error_type = "M"
            issue = "最高概率类别未实现"
        if error_type:
            queue.append({
                "queue_id": "rq-" + sha256_json([item["target_id"], metrics, error_type])[:20],
                "target_id": item["target_id"], "error_type": error_type, "issue": issue,
                "evidence": {"comparison_id": item["comparison_id"], "metrics": metrics},
                "hypothesis": "校准或特征稳定性需要更多前向证据",
                "proposed_change": "建立独立研究候选，不修改已发表预测",
                "required_backtest": "PIT Walk-Forward、基准、校准、子阶段、成本与过拟合检验",
                "priority": "P1", "status": "OPEN",
            })
    return {
        "schema_version": "review.institutional.v1",
        "forecast_schema_version": forecast.get("schema_version") if forecast else None,
        "forecast_quality": "MEASURED" if measured else "NOT_EVALUATED",
        "daily_metrics": [{"target_id": item["target_id"], **item["metrics"]} for item in measured],
        "trading_quality": {"status": "NOT_EVALUATED", "reason": "NO_AUDITED_POSITION_AND_EXECUTION_LEDGER"},
        "model_identity": model,
        "calibration": calibration,
        "model_monitoring": monitoring,
        "research_queue": queue,
        "governance_limitations": [
            "预测质量与交易质量分别报告，不合并为单一总分。",
            "单日评分不能证明模型具备生产资格；仍需滚动样本外、基准、校准和稳定性证据。",
        ],
    }
