from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


BJ = timezone(timedelta(hours=8), "Asia/Shanghai")


def now_beijing() -> datetime:
    return datetime.now(BJ)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def atomic_write_bytes(path: Path, value: bytes, overwrite: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise FileExistsError(path)
    descriptor, temporary = tempfile.mkstemp(prefix="." + path.name + "-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def atomic_write_text(path: Path, value: str, overwrite: bool = True) -> None:
    atomic_write_bytes(path, value.encode("utf-8"), overwrite)


def atomic_write_json(path: Path, value: Any, overwrite: bool = True) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n", overwrite)


def env_path(name: str, fallback: Path | None = None) -> Path | None:
    raw = os.environ.get(name, "").strip()
    if raw:
        return Path(os.path.expandvars(raw)).expanduser().resolve()
    return fallback.resolve() if fallback else None


def decimal_value(value: Any, field: str) -> Decimal:
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"INVALID_DECIMAL:{field}") from error


AMOUNT = re.compile(r"^\s*([-+]?\d+(?:\.\d+)?)\s*(万亿元|万亿|亿元|亿|万元|万|元)?\s*$")


def amount_to_yi(value: Any, field: str) -> Decimal:
    match = AMOUNT.match(str(value))
    if not match:
        raise ValueError(f"INVALID_AMOUNT:{field}")
    number = decimal_value(match.group(1), field)
    unit = match.group(2) or "元"
    factors = {
        "万亿元": Decimal("10000"), "万亿": Decimal("10000"),
        "亿元": Decimal("1"), "亿": Decimal("1"),
        "万元": Decimal("0.0001"), "万": Decimal("0.0001"), "元": Decimal("0.00000001"),
    }
    return number * factors[unit]


def display_decimal(value: Decimal, places: int = 2) -> str:
    quantum = Decimal(1).scaleb(-places)
    return format(value.quantize(quantum), "f")


def safe_error(error: BaseException) -> str:
    code = str(error).split(":", 1)[0].upper()
    allowed = {
        "AUTH_ERROR", "BACKEND_ERROR", "DATE_MISMATCH", "DEADLINE_EXCEEDED",
        "DEEPSEEK_DISABLED", "INVALID_JSON_RESPONSE", "MODEL_NOT_AVAILABLE",
        "MODEL_RESPONSE_MISMATCH", "NETWORK_ERROR", "NO_CONTENT", "NO_RESULTS",
        "SCHEMA_CHANGED", "SECRET_UNAVAILABLE", "TIMEOUT", "TOOL_RUNTIME_ERROR",
        "UNKNOWN_CALENDAR", "WIND_DISABLED", "EARLY_PUBLISH_REJECTED", "LATE_WINDOW_EXCEEDED",
        "NO_READY", "PUBLISH_LOCKED", "PUBLICATION_FILE_EXISTS", "COPY_HASH_MISMATCH",
        "PUBLICATION_MISSING", "HANDOFF_MISSING", "RUN_NOT_FOUND", "REVALIDATION_INPUT_MISSING",
        "BACKUP_INTEGRITY_FAILED", "ACCOUNT_DAILY_BUDGET_EXCEEDED", "REVIEW_DAILY_BUDGET_EXCEEDED",
        "BUDGET_LOCKED", "RATE_LIMIT_ERROR", "FINISH_REASON",
    }
    return code if code in allowed else type(error).__name__.upper()
