from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from .calendar import CalendarError, TradingCalendar
from .config import RuntimeConfig, default_config_path, load_config
from .pipeline import PipelineError, collect, prepare, publish, replay, revalidate, run, watchdog
from .research import DeepSeekClient, ResearchError
from .secrets import SecretUnavailable, load_secret
from .store import Ledger
from .util import atomic_write_json, now_beijing, safe_error


def _json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _day(value: str | None) -> date:
    return date.fromisoformat(value) if value else now_beijing().date()


def _writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, prefix="doctor-", delete=True):
            pass
        return True
    except OSError:
        return False


def doctor(config: RuntimeConfig, probe_model: bool) -> dict[str, Any]:
    checks: list[dict[str, str]] = []

    def add(name: str, passed: bool, detail: str, missing_status: str = "FAIL") -> None:
        checks.append({"check": name, "status": "PASS" if passed else missing_status, "detail": detail})

    add("python", sys.version_info >= (3, 11), f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    add("python_docx", importlib.util.find_spec("docx") is not None, "installed" if importlib.util.find_spec("docx") else "missing")
    add("wind_cli", config.wind_cli.is_file(), "configured" if config.wind_cli.is_file() else "missing")
    add("state_root", _writable(config.state_root), "writable" if _writable(config.state_root) else "not_writable")
    add("report_root", _writable(config.report_root), "writable" if _writable(config.report_root) else "not_writable")
    try:
        calendar = TradingCalendar(config.root / "config" / "trading_sessions.csv")
        calendar.get(now_beijing().date())
        add("calendar", True, "current_date_covered")
    except CalendarError:
        add("calendar", False, "current_date_unknown")
    try:
        secret = load_secret(config.raw["llm"]["secret_env"], config.secret_file)
        add("deepseek_secret", bool(secret), "available_redacted")
        secret = ""
    except SecretUnavailable:
        add("deepseek_secret", False, "unavailable_template_fallback_enabled", "WARN")
    if probe_model:
        try:
            prompt = (config.root / "prompts" / "research-system.md").read_text(encoding="utf-8")
            budget_root = config.state_root / "llm-budget"
            result = DeepSeekClient(config.raw["llm"], config.secret_file, prompt, budget_root).probe()
            add("deepseek_model", result["status"] == "PASS", result["model"])
        except (ResearchError, SecretUnavailable) as error:
            add("deepseek_model", False, safe_error(error))
    return {"schema_version": "review.doctor.v1", "status": "PASS" if all(item["status"] != "FAIL" for item in checks) else "FAIL", "checks": checks, "secrets_redacted": True}


def backup(config: RuntimeConfig) -> dict[str, Any]:
    if not config.ledger_path.exists():
        return {"status": "SKIPPED", "reason": "LEDGER_NOT_CREATED"}
    destination = config.state_root / "backups" / (now_beijing().strftime("review-ledger-%Y%m%dT%H%M%S.sqlite"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(config.ledger_path) as source, sqlite3.connect(destination) as target:
        source.backup(target)
    with sqlite3.connect(destination) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        destination.unlink(missing_ok=True)
        raise PipelineError("BACKUP_INTEGRITY_FAILED")
    return {"status": "PASS", "backup": str(destination), "integrity": integrity}


def status(config: RuntimeConfig, report_date: date, mode: str) -> dict[str, Any]:
    ledger = Ledger(config.ledger_path)
    publication = ledger.publication_for(report_date.isoformat(), config.raw["publication"]["slot"], mode)
    ready = ledger.latest_ready(report_date.isoformat(), mode)
    return {
        "schema_version": "review.status.v1",
        "report_date": report_date.isoformat(),
        "mode": mode,
        "publication": publication,
        "ready": None if ready is None else {"run_id": ready["run_id"], "state": ready["state"], "report_status": ready.get("report_status")},
    }


def reconcile(config: RuntimeConfig, report_date: date, mode: str) -> dict[str, Any]:
    item = {
        "schema_version": "review.reconcile.v1",
        "report_date": report_date.isoformat(),
        "mode": mode,
        "created_at": now_beijing().isoformat(),
        "status": "NO_PENDING_AUTOMATIC_REVISIONS",
        "reason": "Actual revisions require a registered compatible evaluation rule; published files remain immutable.",
    }
    path = config.state_root / "reconcile" / f"{report_date.isoformat()}-{mode}.json"
    atomic_write_json(path, item)
    return item


def handoff(config: RuntimeConfig, report_date: date, mode: str) -> dict[str, Any]:
    publication = Ledger(config.ledger_path).publication_for(report_date.isoformat(), config.raw["publication"]["slot"], mode)
    if not publication:
        raise PipelineError("PUBLICATION_MISSING")
    if mode == "production":
        directory = config.report_root / f"{report_date.year}年{report_date.month}月分析" / f"{report_date.year}年{report_date.month}月{report_date.day}日分析"
    else:
        directory = config.report_root / "review" / "shadow" / report_date.isoformat() / publication["run_id"]
    path = directory / "handoff.json"
    if not path.exists():
        raise PipelineError("HANDOFF_MISSING")
    return {"status": "PASS", "handoff": str(path), "publication_id": publication["publication_id"]}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="post-market-review")
    parser.add_argument("--config", type=Path, default=default_config_path())
    sub = parser.add_subparsers(dest="command", required=True)
    doctor_parser = sub.add_parser("doctor")
    doctor_parser.add_argument("--redact", action="store_true", help="Accepted for explicit redacted output; output is always redacted")
    doctor_parser.add_argument("--probe-model", action="store_true")
    for name in ("collect", "prepare", "publish", "run", "watchdog", "status", "reconcile", "handoff"):
        command = sub.add_parser(name)
        command.add_argument("--date")
        if name != "collect":
            command.add_argument("--mode", choices=("shadow", "production"), default=None)
    replay_parser = sub.add_parser("replay")
    replay_parser.add_argument("--run-id", required=True)
    replay_parser.add_argument("--offline", action="store_true", required=True)
    revalidate_parser = sub.add_parser("revalidate")
    revalidate_parser.add_argument("--run-id", required=True)
    sub.add_parser("backup")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        mode = getattr(args, "mode", None) or config.raw["mode"]
        if args.command == "doctor":
            result = doctor(config, args.probe_model)
        elif args.command == "collect":
            result = collect(config, _day(args.date), config.raw["mode"])
        elif args.command == "prepare":
            result = prepare(config, _day(args.date), mode)
        elif args.command == "publish":
            result = publish(config, _day(args.date), mode)
        elif args.command == "run":
            result = run(config, _day(args.date), mode)
        elif args.command == "watchdog":
            result = watchdog(config, _day(args.date), mode)
        elif args.command == "status":
            result = status(config, _day(args.date), mode)
        elif args.command == "reconcile":
            result = reconcile(config, _day(args.date), mode)
        elif args.command == "handoff":
            result = handoff(config, _day(args.date), mode)
        elif args.command == "replay":
            result = replay(config, args.run_id)
        elif args.command == "revalidate":
            result = revalidate(config, args.run_id)
        elif args.command == "backup":
            result = backup(config)
        else:
            parser.error("unknown command")
            return 2
        _json(result)
        return 0 if result.get("status") not in {"FAIL", "ERROR"} else 10
    except (CalendarError, PipelineError, ResearchError, SecretUnavailable, ValueError, OSError) as error:
        _json({"schema_version": "error.v1", "status": "ERROR", "code": safe_error(error), "message": str(error).split(":", 1)[0], "secrets_redacted": True})
        return 10


if __name__ == "__main__":
    raise SystemExit(main())
