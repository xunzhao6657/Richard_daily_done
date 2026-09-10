from __future__ import annotations

import json
import math
import os
import re
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .secrets import SecretUnavailable, load_secret
from .util import BJ, canonical_json, sha256_json


class ResearchError(RuntimeError):
    pass


FORBIDDEN_KEYS = {
    "api_key", "authorization", "credential", "credentials", "headers", "raw_path",
    "raw_response", "raw_sha256", "receipt", "receipts", "secret", "secret_file",
    "source_locator", "vendor_narrative",
}
LOCAL_PATH = re.compile(r"(?:[A-Za-z]:\\|\\\\[^\\\s]+\\|file://)", re.IGNORECASE)
SECRET_LIKE = re.compile(r"(?:sk|ak)_[A-Za-z0-9_-]{16,}", re.IGNORECASE)
TOKEN = re.compile(r"\{\{(fact|comparison):([^}]+)\}\}")
RAW_NUMBER = re.compile(r"(?<![A-Za-z_])[-+]?\d+(?:\.\d+)?\s*(?:%|点|亿元|万亿元|家)?")
CHINESE_QUANTITY = re.compile(r"[零〇一二两三四五六七八九十百千万亿]+(?:个|家|点|日|月|年|成|％|%)")
URL_LIKE = re.compile(r"(?:https?://|www\.)", re.IGNORECASE)
UNREGISTERED_COMPARATIVE = re.compile(r"(?:高位|低位|放量|缩量|同比|环比|显著|明显|持续走强|持续走弱)")


def assert_outbound_safe(value: Any, location: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).lower()
            if normalized in FORBIDDEN_KEYS or normalized.endswith("_credential"):
                raise ResearchError(f"OUTBOUND_FORBIDDEN_FIELD:{location}.{key}")
            assert_outbound_safe(item, f"{location}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            assert_outbound_safe(item, f"{location}[{index}]")
    elif isinstance(value, str) and (LOCAL_PATH.search(value) or SECRET_LIKE.search(value)):
        raise ResearchError(f"OUTBOUND_SENSITIVE_STRING:{location}")


def evidence_dto(snapshot: dict[str, Any], facts: list[dict[str, Any]], comparisons: list[dict[str, Any]], next_session: str | None) -> dict[str, Any]:
    allowed_fact_keys = {"evidence_id", "label", "display_value", "trade_date", "available_time", "source_label", "allowed_section_ids"}
    clean_facts = [{key: item[key] for key in allowed_fact_keys} for item in facts]
    clean_comparisons = [{
        "comparison_id": item["comparison_id"],
        "target_id": item["target_id"],
        "forecast_display": item["forecast_display"],
        "actual_display": item["actual_display"],
        "verdict": item["verdict"],
        "reason_codes": item["reason_codes"],
    } for item in comparisons]
    clean_states = [{
        "provider": item["provider"],
        "status": item["status"],
        "reason": item["reason"],
    } for item in snapshot.get("source_states", [])]
    value = {
        "schema_version": "review.evidence.v1",
        "snapshot_hash": snapshot["snapshot_hash"],
        "report_date": snapshot["report_date"],
        "cutoff_at": snapshot["cutoff_at"],
        "next_session": next_session,
        "facts": clean_facts,
        "metrics": [],
        "comparisons": clean_comparisons,
        "events": [],
        "allowed_section_ids": [f"S{index}" for index in range(1, 7)],
        "source_states": clean_states,
    }
    value["evidence_hash"] = sha256_json(value)
    assert_outbound_safe(value)
    return value


class TokenBudget:
    def __init__(self, root: Path, total_input: int, total_output: int, review_input: int, review_output: int):
        self.root = root
        self.total_input = total_input
        self.total_output = total_output
        self.review_input = review_input
        self.review_output = review_output

    def reserve(self, input_tokens: int, output_tokens: int) -> dict[str, Any]:
        day = datetime.now(BJ).date().isoformat()
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{day}.jsonl"
        lock = self.root / f"{day}.lock"
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(descriptor)
        except FileExistsError as error:
            raise ResearchError("BUDGET_LOCKED") from error
        try:
            entries = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []
            total_in = sum(int(item["input_tokens"]) for item in entries)
            total_out = sum(int(item["output_tokens"]) for item in entries)
            review_in = sum(int(item["input_tokens"]) for item in entries if item.get("purpose") == "post_market_review")
            review_out = sum(int(item["output_tokens"]) for item in entries if item.get("purpose") == "post_market_review")
            if total_in + input_tokens > self.total_input or total_out + output_tokens > self.total_output:
                raise ResearchError("ACCOUNT_DAILY_BUDGET_EXCEEDED")
            if review_in + input_tokens > self.review_input or review_out + output_tokens > self.review_output:
                raise ResearchError("REVIEW_DAILY_BUDGET_EXCEEDED")
            reservation = {
                "reservation_id": "llmres-" + uuid.uuid4().hex,
                "purpose": "post_market_review",
                "reserved_at": datetime.now(BJ).isoformat(),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            }
            with path.open("a", encoding="utf-8", newline="") as handle:
                handle.write(canonical_json(reservation) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            return reservation
        finally:
            lock.unlink(missing_ok=True)


class DeepSeekClient:
    def __init__(self, config: dict[str, Any], secret_file: Path, prompt: str, budget_root: Path):
        self.config = config
        self.secret_file = secret_file
        self.prompt = prompt
        self.budget_root = budget_root

    def _accepted_response_models(self) -> set[str]:
        configured = self.config.get("accepted_response_models", [self.config["model"]])
        return {str(item) for item in configured}

    def probe(self) -> dict[str, Any]:
        key = load_secret(self.config["secret_env"], self.secret_file)
        body = {
            "model": self.config["model"],
            "messages": [{"role": "user", "content": "Return a JSON object whose status field is ok."}],
            "thinking": {"type": "disabled"},
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "max_tokens": 64,
            "stream": False,
        }
        request = urllib.request.Request(
            self.config["base_url"] + "/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config["connect_timeout_seconds"]) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raise ResearchError("AUTH_ERROR" if error.code in {401, 403} else "NETWORK_ERROR") from error
        except (urllib.error.URLError, TimeoutError, PermissionError) as error:
            raise ResearchError("NETWORK_ERROR") from error
        try:
            choice = payload["choices"][0]
            probe_payload = json.loads(choice["message"]["content"])
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
            raise ResearchError("INVALID_JSON_RESPONSE") from error
        if payload.get("model") not in self._accepted_response_models():
            raise ResearchError("MODEL_NOT_AVAILABLE")
        if choice.get("finish_reason") != "stop" or probe_payload.get("status") != "ok":
            raise ResearchError("MODEL_PROBE_FAILED")
        return {"status": "PASS", "model": self.config["model"]}

    def research(self, evidence: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        assert_outbound_safe(evidence)
        key = load_secret(self.config["secret_env"], self.secret_file)
        evidence_json = canonical_json(evidence)
        estimated = math.ceil(len((self.prompt + evidence_json).encode("utf-8")) / 3) + 64
        reservation = TokenBudget(
            self.budget_root,
            int(self.config["daily_input_token_limit"]),
            int(self.config["daily_output_token_limit"]),
            int(self.config["review_input_token_limit"]),
            int(self.config["review_output_token_limit"]),
        ).reserve(estimated, int(self.config["max_tokens"]))
        body = {
            "model": self.config["model"],
            "messages": [{"role": "system", "content": self.prompt}, {"role": "user", "content": evidence_json}],
            "thinking": {"type": "disabled"},
            "response_format": {"type": "json_object"},
            "temperature": self.config["temperature"],
            "max_tokens": self.config["max_tokens"],
            "stream": False,
        }
        request = urllib.request.Request(
            self.config["base_url"] + "/chat/completions",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self.config["read_timeout_seconds"]) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            code = "AUTH_ERROR" if error.code in {401, 403} else "RATE_LIMIT_ERROR" if error.code == 429 else "NETWORK_ERROR"
            raise ResearchError(code) from error
        except (urllib.error.URLError, TimeoutError, PermissionError) as error:
            raise ResearchError("NETWORK_ERROR") from error
        try:
            choice = result["choices"][0]
            if result.get("model") not in self._accepted_response_models():
                raise ResearchError("MODEL_RESPONSE_MISMATCH")
            if choice.get("finish_reason") != "stop":
                raise ResearchError("FINISH_REASON")
            payload = json.loads(choice["message"]["content"])
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
            raise ResearchError("INVALID_JSON_RESPONSE") from error
        return payload, {
            "request_id": result.get("id"),
            "requested_model": self.config["model"],
            "returned_model": result.get("model"),
            "usage": result.get("usage"),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "input_hash": sha256_json(evidence),
            "budget_reservation": reservation,
        }


def validate_research(payload: dict[str, Any], evidence: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    expected = {"prompt_version", "evidence_hash", "claims", "watch_items", "limitations"}
    if not isinstance(payload, dict) or set(payload) != expected:
        return [], [], ["RESEARCH_SCHEMA_KEYS"]
    if payload["prompt_version"] != "review.research.v1" or payload["evidence_hash"] != evidence["evidence_hash"]:
        return [], [], ["RESEARCH_IDENTITY"]
    if not isinstance(payload["claims"], list) or not isinstance(payload["watch_items"], list) or not isinstance(payload["limitations"], list):
        return [], [], ["RESEARCH_SCHEMA_TYPES"]
    evidence_ids = {item["evidence_id"] for item in evidence["facts"]}
    comparison_ids = {item["comparison_id"] for item in evidence["comparisons"]}
    allowed_tokens = evidence_ids | comparison_ids
    allowed_sections = {item["evidence_id"]: set(item["allowed_section_ids"]) for item in evidence["facts"]}
    allowed_sections.update({item["comparison_id"]: {"S4", "S6"} for item in evidence["comparisons"]})
    claims: list[dict[str, Any]] = []
    rejections: list[str] = []
    claim_keys = {"claim_id", "section_id", "claim_type", "text_template", "evidence_ids", "uncertainties", "causal_strength"}
    for item in payload["claims"]:
        reason = None
        if not isinstance(item, dict) or set(item) != claim_keys:
            reason = "CLAIM_SCHEMA"
        elif item["section_id"] not in {f"S{i}" for i in range(1, 7)}:
            reason = "SECTION"
        elif item["claim_type"] not in {"FACT_SUMMARY", "INTERPRETATION", "HYPOTHESIS", "RISK"}:
            reason = "CLAIM_TYPE"
        elif item["claim_type"] == "FACT_SUMMARY":
            reason = "FACT_SUMMARY_ALREADY_RENDERED"
        elif item["causal_strength"] not in {"DESCRIPTIVE", "ASSOCIATION", "HYPOTHESIS"}:
            reason = "CAUSAL_STRENGTH"
        elif not isinstance(item["evidence_ids"], list) or not set(item["evidence_ids"]).issubset(allowed_tokens):
            reason = "UNKNOWN_EVIDENCE"
        elif not item["evidence_ids"]:
            reason = "EVIDENCE_REQUIRED"
        elif any(item["section_id"] not in allowed_sections[identifier] for identifier in item["evidence_ids"]):
            reason = "SECTION_EVIDENCE_MISMATCH"
        else:
            tokens = TOKEN.findall(item["text_template"])
            prose = TOKEN.sub("", item["text_template"])
            if RAW_NUMBER.search(prose) or CHINESE_QUANTITY.search(prose):
                reason = "RAW_NUMBER"
            elif URL_LIKE.search(item["text_template"]):
                reason = "URL_NOT_ALLOWED"
            elif UNREGISTERED_COMPARATIVE.search(prose):
                reason = "UNREGISTERED_COMPARATIVE"
            elif "F009" in item["evidence_ids"] and re.search(r"(?:机构|主力|大资金|中小单)", prose):
                reason = "VENDOR_FLOW_OVERCLAIM"
            elif len(tokens) != len(set(tokens)):
                reason = "DUPLICATE_TOKEN"
            elif re.search(r"\}\}\s*(?:点|%|％|亿元|万亿元|家)", item["text_template"]):
                reason = "TOKEN_UNIT_DUPLICATION"
            elif any(identifier not in allowed_tokens for _, identifier in tokens):
                reason = "UNKNOWN_TOKEN"
            elif any(identifier not in item["evidence_ids"] for _, identifier in tokens):
                reason = "TOKEN_NOT_CITED"
        if reason:
            rejections.append(f"{item.get('claim_id', '?') if isinstance(item, dict) else '?'}:{reason}")
        else:
            claims.append(item)
    watch_keys = {"watch_id", "entity_id", "hypothesis_template", "variable_id", "trigger_rule_id", "invalidator_rule_id", "evidence_ids", "valid_until_session"}
    watch_items: list[dict[str, Any]] = []
    for item in payload["watch_items"]:
        reason = None
        if not isinstance(item, dict) or set(item) != watch_keys:
            reason = "WATCH_SCHEMA"
        elif item["entity_id"] != "市场":
            reason = "WATCH_ENTITY"
        elif item["trigger_rule_id"] is not None or item["invalidator_rule_id"] is not None:
            reason = "UNREGISTERED_RULE"
        elif item["valid_until_session"] != evidence.get("next_session"):
            reason = "WATCH_EXPIRY"
        elif not isinstance(item["evidence_ids"], list) or not item["evidence_ids"] or not set(item["evidence_ids"]).issubset(evidence_ids):
            reason = "WATCH_EVIDENCE"
        elif RAW_NUMBER.search(TOKEN.sub("", item["hypothesis_template"])) or CHINESE_QUANTITY.search(TOKEN.sub("", item["hypothesis_template"])):
            reason = "WATCH_RAW_NUMBER"
        elif URL_LIKE.search(item["hypothesis_template"]):
            reason = "WATCH_URL"
        else:
            tokens = TOKEN.findall(item["hypothesis_template"])
            if any(kind != "fact" or identifier not in evidence_ids for kind, identifier in tokens):
                reason = "WATCH_UNKNOWN_TOKEN"
            elif any(identifier not in item["evidence_ids"] for _, identifier in tokens):
                reason = "WATCH_TOKEN_NOT_CITED"
        if reason:
            rejections.append(f"{item.get('watch_id', '?') if isinstance(item, dict) else '?'}:{reason}")
        else:
            watch_items.append(item)
    return claims, watch_items, rejections


def inject_tokens(text: str, evidence: dict[str, Any]) -> str:
    facts = {item["evidence_id"]: item["display_value"] for item in evidence["facts"]}
    comparisons = {item["comparison_id"]: f"{item['forecast_display']}；实际{item['actual_display']}；{item['verdict']}" for item in evidence["comparisons"]}
    def replace(match: re.Match[str]) -> str:
        source = facts if match.group(1) == "fact" else comparisons
        if match.group(2) not in source:
            raise ResearchError("UNKNOWN_RENDER_TOKEN")
        return source[match.group(2)]
    return TOKEN.sub(replace, text)
