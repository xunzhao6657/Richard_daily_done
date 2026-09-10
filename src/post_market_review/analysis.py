from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from .util import display_decimal, sha256_json


def _fact(items: list[dict[str, Any]], label: str, display: str, market: dict[str, Any], source: str = "Wind") -> str:
    evidence_id = f"F{len(items) + 1:03d}"
    items.append({
        "evidence_id": evidence_id,
        "label": label,
        "display_value": display,
        "trade_date": market["trade_date"],
        "available_time": market["available_time"],
        "source_label": source,
    })
    return evidence_id


def build_facts(market: dict[str, Any] | None) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    facts: list[dict[str, Any]] = []
    groups: dict[str, list[str]] = {"indexes": [], "structure": [], "emotion": [], "industries": [], "anchors": []}
    if market is None:
        return facts, groups
    for item in market["indexes"]:
        arrow = "↑ +" if Decimal(item["return_pct"]) > 0 else "↓ " if Decimal(item["return_pct"]) < 0 else ""
        groups["indexes"].append(_fact(
            facts,
            item["name"],
            f"{display_decimal(Decimal(item['close']))}点，{arrow}{display_decimal(Decimal(item['return_pct']))}%",
            market,
        ))
    groups["structure"].append(_fact(facts, "万得全A成交额", f"{display_decimal(Decimal(market['turnover_yi']))}亿元", market))
    breadth = market["breadth"]
    groups["structure"].append(_fact(
        facts,
        "市场涨跌分布",
        f"上涨{breadth['advancers']}家、下跌{breadth['decliners']}家、平盘{breadth['unchanged']}家、停牌{breadth['suspended']}家",
        market,
    ))
    groups["emotion"].append(_fact(
        facts,
        "收盘涨跌停",
        f"涨停{breadth['limit_up']}家、跌停{breadth['limit_down']}家",
        market,
    ))
    top = "；".join(f"{item['name']} {('↑ +' if Decimal(item['return_pct']) > 0 else '↓ ')}{display_decimal(Decimal(item['return_pct']))}%" for item in market["industry_top5"])
    bottom = "；".join(f"{item['name']} {('↑ +' if Decimal(item['return_pct']) > 0 else '↓ ')}{display_decimal(Decimal(item['return_pct']))}%" for item in market["industry_bottom5"])
    groups["industries"].append(_fact(facts, market["industry_classification"] + "前五", top, market))
    groups["industries"].append(_fact(facts, market["industry_classification"] + "后五", bottom, market))
    flow = market["vendor_flow_yi"]
    groups["structure"].append(_fact(
        facts,
        "供应商大单分层统计",
        f"超大单{display_decimal(Decimal(flow['extra_large']))}亿元、大单{display_decimal(Decimal(flow['large']))}亿元",
        market,
    ))
    if market["turnover_anchors"]:
        anchors = "；".join(f"{item['name']} {display_decimal(Decimal(item['amount_yi']))}亿元" for item in market["turnover_anchors"])
        groups["anchors"].append(_fact(facts, "成交额锚点前五", anchors, market))
    if market["limit_ladder"]:
        ladder = "；".join(f"{item['height']} {item['count']}家（{'、'.join(item['representatives'])}）" for item in market["limit_ladder"])
        groups["emotion"].append(_fact(facts, "连板梯队", ladder, market))
    section_map = {
        "indexes": {"S1", "S6"}, "structure": {"S1", "S2", "S6"},
        "emotion": {"S3", "S6"}, "industries": {"S2", "S3", "S6"}, "anchors": {"S2", "S6"},
    }
    allowed_by_id: dict[str, set[str]] = {item["evidence_id"]: set() for item in facts}
    for group, identifiers in groups.items():
        for identifier in identifiers:
            allowed_by_id[identifier].update(section_map[group])
    for item in facts:
        item["allowed_section_ids"] = sorted(allowed_by_id[item["evidence_id"]])
    return facts, groups


def empirical_percentile(value: Decimal, history: list[Decimal]) -> Decimal:
    if len(history) != 60:
        raise ValueError("HISTORY_WINDOW")
    lower = sum(1 for item in history if item < value)
    equal = sum(1 for item in history if item == value)
    return Decimal(100) * (Decimal(lower) + Decimal("0.5") * Decimal(equal)) / Decimal(60)


def sentiment_temperature(current: dict[str, Decimal | None], history: list[dict[str, Decimal]]) -> dict[str, Any]:
    required = {"limit_up", "blast_rate", "limit_down", "volume_ratio", "advance_ratio"}
    if set(current) != required or any(current[key] is None for key in required) or len(history) != 60:
        return {"score": None, "band": None, "status": "UNAVAILABLE", "reason": "MISSING_FACTOR_OR_HISTORY", "rule_version": "sentiment.v1"}
    factors = []
    for key in required:
        series = [row[key] for row in history]
        factors.append(empirical_percentile(current[key], series))  # type: ignore[arg-type]
    score = (factors[0] + (Decimal(100) - factors[1]) + (Decimal(100) - factors[2]) + factors[3] + factors[4]) / Decimal(5)
    band = "过热" if score >= 80 else "偏热" if score >= 65 else "中性" if score >= 45 else "偏冷" if score >= 30 else "冰冷"
    return {
        "score": str(score.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)),
        "raw_score": str(score),
        "band": band,
        "status": "VALID",
        "reason": None,
        "rule_version": "sentiment.v1",
    }


def deterministic_analysis(market: dict[str, Any] | None, facts: list[dict[str, Any]], groups: dict[str, list[str]]) -> dict[str, Any]:
    if market is None:
        return {
            "market_label": "未取得可核验的收盘行情",
            "breadth_label": "未获取",
            "style_label": "未获取",
            "sentiment": {"score": None, "band": None, "status": "UNAVAILABLE", "reason": "MARKET_DATA_UNAVAILABLE", "rule_version": "sentiment.v1"},
        }
    indexes_up = sum(Decimal(item["return_pct"]) > 0 for item in market["indexes"])
    breadth = market["breadth"]
    denominator = breadth["advancers"] + breadth["decliners"]
    advance_ratio = Decimal(breadth["advancers"]) / Decimal(denominator) if denominator else None
    if advance_ratio is not None and advance_ratio >= Decimal("0.6") and indexes_up >= 2:
        label = "多数指数上涨且市场广度偏强"
    elif advance_ratio is not None and advance_ratio <= Decimal("0.4") and indexes_up <= 1:
        label = "市场广度偏弱，指数表现分化或走弱"
    else:
        label = "指数与市场广度呈分化状态"
    scales = {item["windcode"]: Decimal(item["return_pct"]) for item in market["scale_indexes"]}
    if "000300.SH" in scales and "000852.SH" in scales:
        spread = scales["000300.SH"] - scales["000852.SH"]
        style = "大盘相对占优" if spread > Decimal("0.3") else "小盘相对占优" if spread < Decimal("-0.3") else "大小盘差异有限"
    else:
        style = "规模风格未获取"
    sentiment = sentiment_temperature({
        "limit_up": Decimal(breadth["limit_up"]),
        "blast_rate": None,
        "limit_down": Decimal(breadth["limit_down"]),
        "volume_ratio": None,
        "advance_ratio": advance_ratio,
    }, [])
    return {
        "market_label": label,
        "breadth_label": f"上涨占涨跌家数{display_decimal(advance_ratio * 100) if advance_ratio is not None else 'NA'}%",
        "style_label": style,
        "sentiment": sentiment,
        "evidence_groups": groups,
    }


def market_observations(market: dict[str, Any] | None) -> list[dict[str, Any]]:
    if market is None:
        return []
    observations: list[dict[str, Any]] = []
    available = market["available_time"]
    event_time = market["trade_date"] + "T15:00:00+08:00"

    def add(instrument: str, field: str, value: Any, unit: str, universe: str) -> None:
        observations.append({
            "observation_id": f"OBS{len(observations) + 1:04d}",
            "dataset_id": market["dataset_id"],
            "instrument_id": instrument,
            "field": field,
            "value_decimal": str(Decimal(str(value))),
            "unit": unit,
            "currency": "CNY" if unit in {"CNY", "CNY_100M"} else None,
            "trade_date": market["trade_date"],
            "period": "1d",
            "event_time": event_time,
            "publish_time": None,
            "vendor_time": available,
            "first_seen_at": available,
            "ingest_time": available,
            "available_time": available,
            "provider": market["provider"],
            "upstream": market["upstream"],
            "source_locator": market.get("source_locator", "wind_market_overview"),
            "raw_sha256": market.get("raw_sha256"),
            "universe_id": universe,
            "definition_version": "wind_market_overview.v1",
            "revision_id": "initial",
            "quality_status": "VALID",
            "reason_codes": ["LOCAL_FIRST_SEEN"],
        })

    for item in market["indexes"]:
        for field in ("open", "high", "low", "close"):
            add(item["windcode"], field, item[field], "INDEX_POINT", "CN_INDEX")
        add(item["windcode"], "return_pct", item["return_pct"], "PERCENT_POINT", "CN_INDEX")
    add("WIND_ALL_A", "turnover", market["turnover_yi"], "CNY_100M", "CN_A_SHARE_WIND")
    for key, value in market["breadth"].items():
        add("CN_A_SHARE_WIND", key, value, "COUNT", "CN_A_SHARE_WIND")
    for key, value in market["vendor_flow_yi"].items():
        add("CN_A_SHARE_WIND", f"vendor_{key}_flow", value, "CNY_100M", "CN_A_SHARE_WIND")
    for item in market["industry_top5"] + market["industry_bottom5"]:
        add(item["windcode"], "return_pct", item["return_pct"], "PERCENT_POINT", market["industry_classification"])
    for item in market["turnover_anchors"]:
        add(item["windcode"], "turnover", item["amount_yi"], "CNY_100M", "CN_A_SHARE_WIND")
    return observations


def make_snapshot(run_id: str, report_date: str, cutoff_at: str, mode: str, market: dict[str, Any] | None, source_states: list[dict[str, Any]], cutoff_status: str) -> dict[str, Any]:
    value = {
        "schema_version": "review.snapshot.v1",
        "run_id": run_id,
        "report_date": report_date,
        "cutoff_at": cutoff_at,
        "created_at": market["available_time"] if market else None,
        "mode": mode,
        "cutoff_status": cutoff_status,
        "market": market,
        "observations": market_observations(market),
        "derived_metrics": [],
        "source_states": source_states,
    }
    value["snapshot_hash"] = sha256_json(value)
    return value
