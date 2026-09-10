from __future__ import annotations

from pathlib import Path
from typing import Any

from post_market_review.config import RuntimeConfig


def runtime(root: Path, *, llm_enabled: bool = False) -> RuntimeConfig:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "prompts").mkdir(parents=True, exist_ok=True)
    (root / "prompts" / "research-system.md").write_text("test", encoding="utf-8")
    (root / "config" / "trading_sessions.csv").write_text(
        "market,session_date,status,source,source_version\n"
        "CN,2026-09-09,OPEN,SSE,2026\n"
        "CN,2026-09-10,OPEN,SSE,2026\n"
        "CN,2026-09-12,CLOSED,SSE,2026\n",
        encoding="utf-8",
    )
    raw: dict[str, Any] = {
        "schema_version": "review-runtime.v1",
        "timezone": "Asia/Shanghai",
        "windows_timezone": "China Standard Time",
        "mode": "shadow",
        "schedule": {
            "collect_at": "19:15:00", "freeze_at": "19:45:00", "llm_deadline": "19:54:00",
            "ready_deadline": "19:57:00", "publish_at": "20:00:00", "watchdog_at": "20:02:00",
            "max_late_minutes": 60,
        },
        "data": {"wind_enabled": True, "market_overview_enabled": True, "index_crosscheck_enabled": True, "akshare_enabled": False, "max_attempts": 3, "call_timeout_seconds": 45},
        "llm": {
            "enabled": llm_enabled, "base_url": "https://api.deepseek.com", "model": "deepseek-v4-flash",
            "accepted_response_models": ["deepseek-v4-flash", "deepseek-flash"],
            "secret_env": "DEEPSEEK_API_KEY", "temperature": 0.2, "max_tokens": 6000,
            "connect_timeout_seconds": 10, "read_timeout_seconds": 90,
            "daily_input_token_limit": 100000, "daily_output_token_limit": 20000,
            "review_input_token_limit": 40000, "review_output_token_limit": 12000,
        },
        "publication": {"slot": "20:00", "local_only": True, "upload_sanitized_artifact": True, "overwrite": False},
    }
    return RuntimeConfig(root, raw)


def market(available_time: str = "2026-09-09T19:40:00+08:00") -> dict[str, Any]:
    indexes = [
        {"windcode": "000001.SH", "name": "上证指数", "close": "3812.22", "return_pct": "0.23", "open": "3801.00", "high": "3820.00", "low": "3795.00"},
        {"windcode": "399001.SZ", "name": "深证成指", "close": "12234.50", "return_pct": "-0.12", "open": "12250.00", "high": "12300.00", "low": "12180.00"},
        {"windcode": "399006.SZ", "name": "创业板指", "close": "2660.10", "return_pct": "0.45", "open": "2644.00", "high": "2670.00", "low": "2635.00"},
    ]
    ranking = lambda prefix, sign: [{"windcode": f"{prefix}{i}", "name": f"行业{i}", "return_pct": str(sign * (6 - i) / 10)} for i in range(1, 6)]
    return {
        "dataset_id": "wind_market_overview", "trade_date": "2026-09-09", "available_time": available_time,
        "provider": "wind", "upstream": "wind-stock-research", "market_state": "CLOSED", "indexes": indexes,
        "breadth": {"advancers": 3100, "decliners": 1900, "unchanged": 120, "suspended": 20, "limit_up": 58, "limit_down": 6},
        "turnover_yi": "19000", "vendor_flow_yi": {"extra_large": "-31", "large": "25", "medium": "3", "small": "3"},
        "industry_classification": "Wind行业板块", "industry_top5": ranking("T", 1), "industry_bottom5": ranking("B", -1),
        "scale_indexes": [{"windcode": "000300.SH", "name": "沪深300", "return_pct": "0.4"}, {"windcode": "000852.SH", "name": "中证1000", "return_pct": "-0.2"}],
        "turnover_anchors": [{"windcode": f"A{i}", "name": f"股票{i}", "close": "10", "amount_yi": str(100 - i)} for i in range(1, 6)],
        "limit_ladder": [{"height": "3板", "count": 2, "representatives": ["甲", "乙"]}],
        "verification": [{"windcode": item["windcode"], "status": "SAME_PROVIDER_CONSISTENT", "relative_difference": "0"} for item in indexes],
        "raw_sha256": "a" * 64, "source_locator": "receipt-test",
    }
