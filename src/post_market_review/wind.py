from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from .config import RuntimeConfig
from .util import amount_to_yi, atomic_write_text, decimal_value, now_beijing, safe_error, sha256_bytes, sha256_json


class WindError(RuntimeError):
    pass


INDEXES = {
    "000001.SH": "上证指数",
    "399001.SZ": "深证成指",
    "399006.SZ": "创业板指",
}


class WindClient:
    def __init__(self, config: RuntimeConfig, clock: Callable[[], datetime] = now_beijing):
        self.config = config
        self.clock = clock
        self.cli = config.wind_cli
        self.archive_root = config.state_root / "raw" / "wind"
        self.timeout = int(config.raw["data"]["call_timeout_seconds"])
        self.max_attempts = int(config.raw["data"]["max_attempts"])
        self.receipts: list[dict[str, Any]] = []

    def call(self, report_date: str, dataset_id: str, server: str, tool: str, params: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        if not self.cli.exists():
            raise WindError("TOOL_RUNTIME_ERROR")
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            requested_at = self.clock()
            receipt: dict[str, Any] | None = None
            try:
                process = subprocess.run(
                    [os.environ.get("NODE_EXE", "node"), str(self.cli), "call", server, tool, "-"],
                    input=json.dumps(params, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                    cwd=self.cli.parent,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=self.timeout,
                    check=False,
                )
                received_at = self.clock()
                stdout = process.stdout.decode("utf-8-sig", errors="strict")
                receipt = self._archive(report_date, dataset_id, requested_at, received_at, stdout, process.returncode, sha256_json(params))
                receipt["attempt"] = attempt
                self.receipts.append(receipt)
                if process.returncode != 0:
                    raise WindError("TOOL_RUNTIME_ERROR")
                outer = json.loads(stdout)
                if outer.get("isError"):
                    raise WindError("BACKEND_ERROR")
                content = outer.get("content")
                if not isinstance(content, list):
                    raise WindError("SCHEMA_CHANGED")
                text_items = [item.get("text") for item in content if isinstance(item, dict) and isinstance(item.get("text"), str)]
                if not text_items:
                    raise WindError("NO_CONTENT")
                payload = json.loads(text_items[0])
                if payload.get("error") not in {None, ""}:
                    raise WindError("BACKEND_ERROR")
                receipt["status"] = "OK"
                return payload, receipt
            except subprocess.TimeoutExpired as error:
                last_error = WindError("TIMEOUT")
                receipt = self._archive(
                    report_date, dataset_id, requested_at, self.clock(), "", 1, sha256_json(params),
                )
                receipt["attempt"] = attempt
                self.receipts.append(receipt)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                last_error = WindError("SCHEMA_CHANGED")
            except WindError as error:
                last_error = error
                if str(error) in {"BACKEND_ERROR", "SCHEMA_CHANGED"}:
                    pass
            if receipt is not None:
                receipt["status"] = "ERROR"
                receipt["error_code"] = safe_error(last_error or WindError("TOOL_RUNTIME_ERROR"))
            if isinstance(last_error, WindError) and str(last_error).split(":", 1)[0] in {"BACKEND_ERROR", "SCHEMA_CHANGED", "DATE_MISMATCH"}:
                break
            if attempt < self.max_attempts:
                time.sleep(2 if attempt == 1 else 5)
        raise last_error or WindError("TOOL_RUNTIME_ERROR")

    def _archive(
        self,
        report_date: str,
        dataset_id: str,
        requested_at: datetime,
        received_at: datetime,
        stdout: str,
        returncode: int,
        request_sha256: str,
    ) -> dict[str, Any]:
        raw = stdout.encode("utf-8")
        digest = sha256_bytes(raw)
        receipt_id = "receipt-" + uuid.uuid4().hex
        path = self.archive_root / dataset_id / report_date / f"{receipt_id}.json"
        atomic_write_text(path, stdout)
        return {
            "receipt_id": receipt_id,
            "provider": "wind",
            "dataset_id": dataset_id,
            "requested_at": requested_at.isoformat(),
            "received_at": received_at.isoformat(),
            "raw_path": str(path),
            "raw_sha256": digest,
            "request_sha256": request_sha256,
            "status": "ERROR" if returncode else "RECEIVED",
            "error_code": None if returncode == 0 else "TOOL_RUNTIME_ERROR",
        }


def _integer(value: Any, field: str) -> int:
    try:
        return int(str(value))
    except ValueError as error:
        raise WindError(f"SCHEMA_CHANGED:{field}") from error


def _rankings(value: Any, field: str) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise WindError(f"SCHEMA_CHANGED:{field}")
    output = []
    for item in value[:5]:
        if not isinstance(item, dict) or not {"windcode", "name", "price_chg_pct"}.issubset(item):
            raise WindError(f"SCHEMA_CHANGED:{field}")
        output.append({
            "windcode": str(item["windcode"]),
            "name": str(item["name"]),
            "return_pct": str(decimal_value(item["price_chg_pct"], field)),
        })
    if len(output) != 5:
        raise WindError(f"SCHEMA_CHANGED:{field}")
    return output


def normalize_market_overview(payload: dict[str, Any], report_date: str, available_time: str) -> dict[str, Any]:
    trading_time = str(payload.get("TradingTime", ""))
    if trading_time[:10] != report_date:
        raise WindError("DATE_MISMATCH")
    if "已收盘" not in str(payload.get("当前交易状态", "")):
        raise WindError("SCHEMA_CHANGED:MARKET_NOT_CLOSED")
    index_rows = payload.get("重要指数")
    if not isinstance(index_rows, list):
        raise WindError("SCHEMA_CHANGED:INDEXES")
    by_code = {str(item.get("windcode")): item for item in index_rows if isinstance(item, dict)}
    indexes: list[dict[str, str]] = []
    for code, name in INDEXES.items():
        item = by_code.get(code)
        if not item:
            raise WindError(f"SCHEMA_CHANGED:MISSING_{code}")
        indexes.append({
            "windcode": code,
            "name": name,
            "close": str(decimal_value(item.get("last"), code + ".close")),
            "return_pct": str(decimal_value(item.get("price_chg_pct"), code + ".return")),
            "open": str(decimal_value(item.get("open"), code + ".open")),
            "high": str(decimal_value(item.get("high"), code + ".high")),
            "low": str(decimal_value(item.get("low"), code + ".low")),
        })
    breadth = payload.get("涨跌分布")
    if not isinstance(breadth, dict):
        raise WindError("SCHEMA_CHANGED:BREADTH")
    normalized_breadth = {
        "advancers": _integer(breadth.get("advancers"), "advancers"),
        "decliners": _integer(breadth.get("decliners"), "decliners"),
        "unchanged": _integer(breadth.get("unchanged"), "unchanged"),
        "suspended": _integer(breadth.get("suspended"), "suspended"),
        "limit_up": _integer(breadth.get("limitup"), "limitup"),
        "limit_down": _integer(breadth.get("limitdown"), "limitdown"),
    }
    market = payload.get("万得全A")
    if not isinstance(market, dict):
        raise WindError("SCHEMA_CHANGED:WIND_ALL_A")
    leaders = payload.get("style_leaders")
    if not isinstance(leaders, dict):
        raise WindError("SCHEMA_CHANGED:LEADERS")
    scale_rows = leaders.get("规模指数", [])
    scales = [{
        "windcode": str(item.get("windcode")),
        "name": str(item.get("name")),
        "return_pct": str(decimal_value(item.get("price_chg_pct"), "scale.return")),
    } for item in scale_rows if isinstance(item, dict) and item.get("windcode") and item.get("name")]
    ladder = payload.get("今日涨停_天梯表现", {})
    today_ladder = ladder.get("今日", []) if isinstance(ladder, dict) else []
    normalized_ladder = []
    for item in today_ladder:
        if not isinstance(item, dict):
            continue
        normalized_ladder.append({
            "height": str(item.get("连板高度", "")),
            "count": _integer(item.get("家数", 0), "ladder.count"),
            "representatives": [str(name) for name in item.get("代表个股", [])[:10]],
        })
    stock_rankings = payload.get("股票排名", {})
    amount_ranking = stock_rankings.get("成交额排名", []) if isinstance(stock_rankings, dict) else []
    anchors = []
    for item in amount_ranking[:5]:
        if not isinstance(item, dict):
            continue
        anchors.append({
            "windcode": str(item.get("windcode", "")),
            "name": str(item.get("name", "")),
            "close": str(decimal_value(item.get("last"), "anchor.close")),
            "amount_yi": str(amount_to_yi(item.get("amount"), "anchor.amount")),
        })
    return {
        "dataset_id": "wind_market_overview",
        "trade_date": report_date,
        "available_time": available_time,
        "provider": "wind",
        "upstream": "wind-stock-research",
        "market_state": "CLOSED",
        "indexes": indexes,
        "breadth": normalized_breadth,
        "turnover_yi": str(amount_to_yi(market.get("amount"), "turnover")),
        "vendor_flow_yi": {
            "extra_large": str(amount_to_yi(market.get("xlflow"), "xlflow")),
            "large": str(amount_to_yi(market.get("largeflow"), "largeflow")),
            "medium": str(amount_to_yi(market.get("mediumflow"), "mediumflow")),
            "small": str(amount_to_yi(market.get("smallflow"), "smallflow")),
        },
        "industry_classification": "Wind行业板块",
        "industry_top5": _rankings(leaders.get("行业板块前5"), "industry.top5"),
        "industry_bottom5": _rankings(leaders.get("行业板块后5"), "industry.bottom5"),
        "scale_indexes": scales,
        "turnover_anchors": anchors,
        "limit_ladder": normalized_ladder,
    }


def _parse_kline(payload: dict[str, Any], code: str, report_date: str) -> dict[str, str]:
    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("columns"), list) or not isinstance(data.get("rows"), list):
        raise WindError("SCHEMA_CHANGED:KLINE")
    names = [item.get("name") for item in data["columns"]]
    if len(data["rows"]) != 1:
        raise WindError("SCHEMA_CHANGED:KLINE_ROWS")
    row = dict(zip(names, data["rows"][0]))
    if str(row.get("TIME", ""))[:10] != report_date:
        raise WindError("DATE_MISMATCH")
    return {"windcode": code, "close": str(decimal_value(row.get("MATCH"), code + ".kline_close"))}


def close_crosscheck(primary: Decimal, secondary: Decimal) -> dict[str, str]:
    if primary == 0:
        return {"status": "NOT_COMPARABLE", "reason": "PRIMARY_ZERO"}
    relative = abs(secondary - primary) / abs(primary)
    return {
        "status": "SAME_PROVIDER_CONSISTENT" if relative <= Decimal("0.0005") else "CONFLICT",
        "relative_difference": str(relative),
    }


def collect_wind(config: RuntimeConfig, report_date: str, clock: Callable[[], datetime] = now_beijing) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
    if not config.raw["data"]["wind_enabled"]:
        return None, [], [{"provider": "wind", "status": "DISABLED", "reason": "WIND_DISABLED"}]
    client = WindClient(config, clock)
    states: list[dict[str, Any]] = []
    try:
        payload, receipt = client.call(report_date, "wind_market_overview", "stock_research", "stock_get_market_realtime_analysis", {"marketType": "1"})
        market = normalize_market_overview(payload, report_date, receipt["received_at"])
        market["raw_sha256"] = receipt["raw_sha256"]
        market["source_locator"] = receipt["receipt_id"]
        states.append({"provider": "wind:market_overview", "status": "OK", "reason": "NORMALIZED", "attempt_count": sum(item["dataset_id"] == "wind_market_overview" for item in client.receipts)})
    except Exception as error:
        states.append({"provider": "wind:market_overview", "status": "ERROR", "reason": safe_error(error), "attempt_count": sum(item["dataset_id"] == "wind_market_overview" for item in client.receipts)})
        return None, client.receipts, states
    verification: list[dict[str, Any]] = []
    if config.raw["data"]["index_crosscheck_enabled"]:
        for code in INDEXES:
            try:
                payload, receipt = client.call(
                    report_date, "wind_index_crosscheck", "index_data", "get_index_kline",
                    {"windcode": code, "begin_date": report_date, "end_date": report_date, "period": "1d"},
                )
                check = _parse_kline(payload, code, report_date)
                primary = Decimal(next(item["close"] for item in market["indexes"] if item["windcode"] == code))
                secondary = Decimal(check["close"])
                verification.append({"windcode": code, **close_crosscheck(primary, secondary)})
            except Exception as error:
                verification.append({"windcode": code, "status": "NOT_AVAILABLE", "reason": safe_error(error)})
    market["verification"] = verification
    states.append({"provider": "wind:index_crosscheck", "status": "OK" if verification and all(item["status"] == "SAME_PROVIDER_CONSISTENT" for item in verification) else "PARTIAL", "reason": "SAME_PROVIDER_NOT_INDEPENDENT"})
    states.append({"provider": "akshare", "status": "DISABLED", "reason": "CONFIG_DISABLED"})
    return market, client.receipts, states
