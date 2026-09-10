from __future__ import annotations

import json
import os
import shutil
import uuid
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Callable, Iterator

from .analysis import build_facts, deterministic_analysis, make_snapshot
from .calendar import CalendarError, TradingCalendar
from .comparison import compare_forecast, load_morning_forecast
from .config import RuntimeConfig
from .institutional import institutional_review
from .report import build_document, render_all
from .research import DeepSeekClient, ResearchError, evidence_dto, validate_research
from .secrets import SecretUnavailable
from .store import Ledger
from .util import BJ, atomic_write_json, env_path, now_beijing, safe_error, sha256_bytes, sha256_json
from .wind import collect_wind


class PipelineError(RuntimeError):
    pass


def _cutoff(day: date, value: str) -> datetime:
    return datetime.combine(day, time.fromisoformat(value), BJ)


def _basename(day: date) -> str:
    return f"{day.year}年{day.month}月{day.day}日A股收盘总结"


def _update(ledger: Ledger, manifest: dict[str, Any], state: str, clock: Callable[[], datetime]) -> None:
    manifest["state"] = state
    manifest["updated_at"] = clock().isoformat()
    ledger.update_run(manifest)


def collect(config: RuntimeConfig, report_date: date, mode: str, clock: Callable[[], datetime] = now_beijing) -> dict[str, Any]:
    session = TradingCalendar(config.root / "config" / "trading_sessions.csv").get(report_date)
    if not session.is_open:
        return {"status": "SKIPPED", "reason": "NON_TRADING_DAY", "report_date": report_date.isoformat()}
    run_id = "collect-" + uuid.uuid4().hex
    created = clock()
    manifest = {
        "schema_version": "review.run.v1", "run_id": run_id, "report_date": report_date.isoformat(),
        "mode": mode, "state": "COLLECTING", "created_at": created.isoformat(), "updated_at": created.isoformat(),
    }
    ledger = Ledger(config.ledger_path)
    ledger.create_run(manifest)
    market, receipts, states = collect_wind(config, report_date.isoformat(), clock)
    for receipt in receipts:
        ledger.add_receipt(run_id, receipt)
    payload = {
        "schema_version": "review.collection.v1", "run_id": run_id, "report_date": report_date.isoformat(),
        "collected_at": clock().isoformat(), "market": market, "source_states": states,
    }
    payload["collection_hash"] = sha256_json(payload)
    output = config.state_root / "collections" / report_date.isoformat() / f"{run_id}.json"
    atomic_write_json(output, payload)
    manifest["collection_hash"] = payload["collection_hash"]
    manifest["collection_path"] = str(output)
    _update(ledger, manifest, "COLLECTED", clock)
    return {"status": "COLLECTED", "run_id": run_id, "collection_hash": payload["collection_hash"]}


def _prepare_failure(config: RuntimeConfig, report_date: date, mode: str, reason: str, clock: Callable[[], datetime]) -> dict[str, Any]:
    run_id = "failure-" + uuid.uuid4().hex
    created = clock()
    manifest = {
        "schema_version": "review.run.v1", "run_id": run_id, "report_date": report_date.isoformat(), "mode": mode,
        "state": "CREATED", "created_at": created.isoformat(), "updated_at": created.isoformat(),
        "report_status": "FAILURE_BULLETIN", "narrative_status": "TEMPLATE_FALLBACK", "failure_reason": reason,
    }
    ledger = Ledger(config.ledger_path)
    ledger.create_run(manifest)
    snapshot = make_snapshot(
        run_id, report_date.isoformat(), _cutoff(report_date, config.raw["schedule"]["freeze_at"]).isoformat(),
        mode, None, [{"provider": "workflow", "status": "ERROR", "reason": reason}], "NOT_EVALUATED",
    )
    ledger.add_snapshot(run_id, snapshot)
    facts, groups = build_facts(None)
    analysis = deterministic_analysis(None, facts, groups)
    comparisons = compare_forecast(None, None, {"reason": "NO_PUBLISHED_FORECAST"})
    evidence = evidence_dto(snapshot, facts, comparisons, session_next(config, report_date))
    institutional = institutional_review(None, comparisons)
    document = build_document(manifest, snapshot, facts, groups, analysis, comparisons, evidence, [], [], [], institutional)
    return _stage(config, manifest, snapshot, evidence, document, [], [], institutional, ledger, clock)


def session_next(config: RuntimeConfig, report_date: date) -> str | None:
    session = TradingCalendar(config.root / "config" / "trading_sessions.csv").get(report_date)
    return session.next_session.isoformat() if session.next_session else None


def prepare(config: RuntimeConfig, report_date: date, mode: str, clock: Callable[[], datetime] = now_beijing) -> dict[str, Any]:
    try:
        session = TradingCalendar(config.root / "config" / "trading_sessions.csv").get(report_date)
    except CalendarError:
        raise PipelineError("UNKNOWN_CALENDAR")
    if not session.is_open:
        return {"status": "SKIPPED", "reason": "NON_TRADING_DAY", "report_date": report_date.isoformat()}
    run_id = "review-" + uuid.uuid4().hex
    created = clock()
    manifest: dict[str, Any] = {
        "schema_version": "review.run.v1", "run_id": run_id, "report_date": report_date.isoformat(), "mode": mode,
        "state": "CREATED", "created_at": created.isoformat(), "updated_at": created.isoformat(),
        "report_status": "FAILURE_BULLETIN", "narrative_status": "TEMPLATE_FALLBACK",
        "calendar_source": session.source, "calendar_version": session.source_version,
    }
    ledger = Ledger(config.ledger_path)
    ledger.create_run(manifest)
    _update(ledger, manifest, "COLLECTING", clock)
    market, receipts, source_states = collect_wind(config, report_date.isoformat(), clock)
    for receipt in receipts:
        ledger.add_receipt(run_id, receipt)
    morning, morning_state = load_morning_forecast(config.morning_root, report_date.isoformat(), mode)
    source_states.append(morning_state)
    manifest["source_states"] = source_states
    cutoff = _cutoff(report_date, config.raw["schedule"]["freeze_at"])
    received_times = [datetime.fromisoformat(item["received_at"]) for item in receipts]
    cutoff_status = "ON_TIME" if received_times and max(received_times) <= cutoff else "LATE_CAPTURE"
    snapshot = make_snapshot(run_id, report_date.isoformat(), cutoff.isoformat(), mode, market, source_states, cutoff_status)
    ledger.add_snapshot(run_id, snapshot)
    _update(ledger, manifest, "FROZEN", clock)
    facts, groups = build_facts(market)
    analysis = deterministic_analysis(market, facts, groups)
    comparisons = compare_forecast(morning, market, morning_state)
    institutional = institutional_review(morning, comparisons)
    evidence = evidence_dto(snapshot, facts, comparisons, session.next_session.isoformat() if session.next_session else None)
    claims: list[dict[str, Any]] = []
    watch_items: list[dict[str, Any]] = []
    rejections: list[str] = []
    llm_deadline = _cutoff(report_date, config.raw["schedule"]["llm_deadline"])
    acceptance_late_llm = mode == "shadow" and os.environ.get("REVIEW_ACCEPTANCE_ALLOW_LATE_LLM") == "1"
    if acceptance_late_llm:
        manifest["acceptance_override"] = "LATE_LLM_SHADOW_ONLY"
    if config.raw["llm"]["enabled"] and facts and (clock() < llm_deadline or acceptance_late_llm):
        try:
            prompt = (config.root / "prompts" / "research-system.md").read_text(encoding="utf-8")
            budget_root = env_path("DEEPSEEK_BUDGET_ROOT", config.state_root / "llm-budget") or config.state_root / "llm-budget"
            raw, metadata = DeepSeekClient(config.raw["llm"], config.secret_file, prompt, budget_root).research(evidence)
            llm_raw_path = config.state_root / "raw" / "deepseek" / report_date.isoformat() / f"{run_id}.json"
            atomic_write_json(llm_raw_path, raw)
            claims, watch_items, rejections = validate_research(raw, evidence)
            manifest["narrative_status"] = "DEEPSEEK_VALIDATED" if claims else "TEMPLATE_FALLBACK"
            manifest["llm_metadata"] = metadata
            manifest["llm_raw_path"] = str(llm_raw_path)
            manifest["llm_raw_sha256"] = sha256_bytes(llm_raw_path.read_bytes())
        except (ResearchError, SecretUnavailable) as error:
            manifest["llm_error"] = safe_error(error)
    elif config.raw["llm"]["enabled"] and facts:
        manifest["llm_error"] = "DEADLINE_EXCEEDED"
    if market is not None:
        manifest["report_status"] = "PARTIAL"
    manifest["snapshot_hash"] = snapshot["snapshot_hash"]
    document = build_document(manifest, snapshot, facts, groups, analysis, comparisons, evidence, claims, watch_items, rejections, institutional)
    _update(ledger, manifest, "ANALYZED", clock)
    return _stage(config, manifest, snapshot, evidence, document, rejections, watch_items, institutional, ledger, clock)


def _stage(
    config: RuntimeConfig,
    manifest: dict[str, Any],
    snapshot: dict[str, Any],
    evidence: dict[str, Any],
    document: dict[str, Any],
    rejections: list[str],
    watch_items: list[dict[str, Any]],
    institutional: dict[str, Any],
    ledger: Ledger,
    clock: Callable[[], datetime],
) -> dict[str, Any]:
    run_dir = config.state_root / "staging" / manifest["report_date"] / manifest["run_id"]
    paths = render_all(document, run_dir, _basename(date.fromisoformat(manifest["report_date"])))
    audit = {
        "schema_version": "review.audit.v1",
        "manifest": {key: value for key, value in manifest.items() if not key.endswith("_path")},
        "snapshot": snapshot,
        "evidence": evidence,
        "institutional": institutional,
        "claim_rejections": rejections,
        "document_hash": sha256_json(document),
    }
    audit_path = run_dir / "audit.json"
    planned_publication_id = "pub-" + uuid.uuid4().hex
    manifest["planned_publication_id"] = planned_publication_id
    handoff = {
        "schema_version": "review.handoff.v1",
        "review_publication_id": planned_publication_id,
        "review_sha256": audit["document_hash"],
        "review_run_id": manifest["run_id"],
        "next_session": evidence.get("next_session"),
        "available_at": clock().isoformat(),
        "watch_items": watch_items,
        "evidence_refs": sorted({reference for item in watch_items for reference in item["evidence_ids"]}),
        "limitations": document["limitations"],
        "expires_at": evidence.get("next_session"),
    }
    handoff["handoff_hash"] = sha256_json(handoff)
    handoff_path = run_dir / "handoff.json"
    institutional_path = run_dir / "institutional-review.json"
    atomic_write_json(audit_path, audit)
    atomic_write_json(handoff_path, handoff)
    atomic_write_json(institutional_path, institutional)
    all_paths = {**paths, "audit": audit_path, "handoff": handoff_path, "institutional_review": institutional_path}
    hashes = {key: sha256_bytes(path.read_bytes()) for key, path in all_paths.items()}
    manifest["artifacts"] = {key: str(path) for key, path in all_paths.items()}
    manifest["artifact_hashes"] = hashes
    manifest["document_hash"] = audit["document_hash"]
    manifest["state"] = "READY"
    manifest["updated_at"] = clock().isoformat()
    public_ready = {
        "schema_version": "review.ready.v1", "run_id": manifest["run_id"], "report_date": manifest["report_date"],
        "mode": manifest["mode"], "report_status": manifest["report_status"], "narrative_status": manifest["narrative_status"],
        "artifacts": {key: path.name for key, path in all_paths.items()}, "artifact_hashes": hashes,
        "snapshot_hash": snapshot["snapshot_hash"], "ready_at": manifest["updated_at"],
    }
    ready_path = run_dir / "READY.json"
    atomic_write_json(ready_path, public_ready)
    manifest["ready_path"] = str(ready_path)
    ledger.update_run(manifest)
    return {"status": "READY", "run_id": manifest["run_id"], "report_status": manifest["report_status"], "narrative_status": manifest["narrative_status"], "ready_path": str(ready_path)}


@contextmanager
def _publish_lock(config: RuntimeConfig, report_date: str, mode: str) -> Iterator[None]:
    path = config.state_root / "locks" / f"publish-{report_date}-{mode}.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(descriptor)
    except FileExistsError as error:
        raise PipelineError("PUBLISH_LOCKED") from error
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def publish(config: RuntimeConfig, report_date: date, mode: str, clock: Callable[[], datetime] = now_beijing) -> dict[str, Any]:
    ledger = Ledger(config.ledger_path)
    existing = ledger.publication_for(report_date.isoformat(), config.raw["publication"]["slot"], mode)
    if existing:
        return existing
    current = clock()
    publish_at = _cutoff(report_date, config.raw["schedule"]["publish_at"])
    if current < publish_at:
        raise PipelineError("EARLY_PUBLISH_REJECTED")
    if current > publish_at + timedelta(minutes=int(config.raw["schedule"]["max_late_minutes"])):
        raise PipelineError("LATE_WINDOW_EXCEEDED")
    manifest = ledger.latest_ready(report_date.isoformat(), mode)
    if manifest is None:
        _prepare_failure(config, report_date, mode, "NO_READY", clock)
        manifest = ledger.latest_ready(report_date.isoformat(), mode)
    if manifest is None:
        raise PipelineError("NO_READY")
    with _publish_lock(config, report_date.isoformat(), mode):
        existing = ledger.publication_for(report_date.isoformat(), config.raw["publication"]["slot"], mode)
        if existing:
            return existing
        if mode == "production":
            destination = config.report_root / f"{report_date.year}年{report_date.month}月分析" / f"{report_date.year}年{report_date.month}月{report_date.day}日分析"
        else:
            destination = config.report_root / "review" / "shadow" / report_date.isoformat() / manifest["run_id"]
        destination.mkdir(parents=True, exist_ok=True)
        copied: dict[str, Path] = {}
        for key, source_value in manifest["artifacts"].items():
            source = Path(source_value)
            target = destination / source.name
            if target.exists():
                raise PipelineError("PUBLICATION_FILE_EXISTS")
            shutil.copy2(source, target)
            if sha256_bytes(target.read_bytes()) != manifest["artifact_hashes"][key]:
                raise PipelineError("COPY_HASH_MISMATCH")
            copied[key] = target
        ready_source = Path(manifest["ready_path"])
        shutil.copy2(ready_source, destination / "READY.json")
        publication = {
            "schema_version": "review.publication.v1",
            "publication_id": manifest["planned_publication_id"],
            "report_type": "post_market_review",
            "report_date": report_date.isoformat(),
            "slot": config.raw["publication"]["slot"],
            "mode": mode,
            "run_id": manifest["run_id"],
            "published_at": current.isoformat(),
            "late": current > publish_at,
            "status": manifest["report_status"],
            "artifact_hashes": manifest["artifact_hashes"],
            "source_snapshot_hash": manifest["snapshot_hash"],
            "forecast_ref": next((item for item in manifest.get("source_states", []) if item.get("provider") == "morning-forecast"), None),
            "revision_of": None,
        }
        atomic_write_json(destination / "publication.json", publication, overwrite=False)
        ledger.add_publication(publication)
        outbox = config.root / ".runtime" / "outbox" / manifest["run_id"]
        outbox.mkdir(parents=True, exist_ok=True)
        for path in copied.values():
            shutil.copy2(path, outbox / path.name)
        shutil.copy2(destination / "READY.json", outbox / "READY.json")
        atomic_write_json(outbox / "publication.json", publication)
        manifest["publication_id"] = publication["publication_id"]
        manifest["state"] = "PUBLISHED"
        manifest["updated_at"] = current.isoformat()
        ledger.update_run(manifest)
        return publication


def run(config: RuntimeConfig, report_date: date, mode: str, clock: Callable[[], datetime] = now_beijing) -> dict[str, Any]:
    prepared = prepare(config, report_date, mode, clock)
    if prepared["status"] == "SKIPPED":
        return prepared
    return publish(config, report_date, mode, clock)


def replay(config: RuntimeConfig, run_id: str) -> dict[str, Any]:
    manifest = Ledger(config.ledger_path).run(run_id)
    if not manifest:
        raise PipelineError("RUN_NOT_FOUND")
    results = {}
    for key, path_value in manifest.get("artifacts", {}).items():
        path = Path(path_value)
        results[key] = path.exists() and sha256_bytes(path.read_bytes()) == manifest["artifact_hashes"][key]
    ready = Path(manifest.get("ready_path", ""))
    return {"status": "PASS" if results and all(results.values()) and ready.exists() else "FAIL", "run_id": run_id, "offline": True, "hashes": results}


def revalidate(config: RuntimeConfig, run_id: str, clock: Callable[[], datetime] = now_beijing) -> dict[str, Any]:
    ledger = Ledger(config.ledger_path)
    source_manifest = ledger.run(run_id)
    if not source_manifest:
        raise PipelineError("RUN_NOT_FOUND")
    audit_path = Path(source_manifest.get("artifacts", {}).get("audit", ""))
    raw_path = Path(source_manifest.get("llm_raw_path", ""))
    if not audit_path.is_file() or not raw_path.is_file():
        raise PipelineError("REVALIDATION_INPUT_MISSING")
    audit = json.loads(audit_path.read_text(encoding="utf-8-sig"))
    raw = json.loads(raw_path.read_text(encoding="utf-8-sig"))
    snapshot = audit["snapshot"]
    evidence = audit["evidence"]
    claims, watch_items, rejections = validate_research(raw, evidence)
    facts, groups = build_facts(snapshot.get("market"))
    analysis = deterministic_analysis(snapshot.get("market"), facts, groups)
    created = clock()
    manifest = {
        "schema_version": "review.run.v1",
        "run_id": "revalidated-" + uuid.uuid4().hex,
        "source_run_id": run_id,
        "report_date": source_manifest["report_date"],
        "mode": source_manifest["mode"],
        "state": "CREATED",
        "created_at": created.isoformat(),
        "updated_at": created.isoformat(),
        "report_status": source_manifest["report_status"],
        "narrative_status": "DEEPSEEK_VALIDATED" if claims else "TEMPLATE_FALLBACK",
        "snapshot_hash": snapshot["snapshot_hash"],
        "source_states": snapshot["source_states"],
        "revalidation_only": True,
    }
    ledger.create_run(manifest)
    institutional = audit.get("institutional") or institutional_review(None, evidence["comparisons"])
    document = build_document(manifest, snapshot, facts, groups, analysis, evidence["comparisons"], evidence, claims, watch_items, rejections, institutional)
    return _stage(config, manifest, snapshot, evidence, document, rejections, watch_items, institutional, ledger, clock)


def watchdog(config: RuntimeConfig, report_date: date, mode: str) -> dict[str, Any]:
    publication = Ledger(config.ledger_path).publication_for(report_date.isoformat(), config.raw["publication"]["slot"], mode)
    if not publication:
        return {"status": "ERROR", "code": "PUBLICATION_MISSING", "report_date": report_date.isoformat()}
    return {"status": "PASS", "publication_id": publication["publication_id"], "late": publication["late"], "artifact_count": len(publication["artifact_hashes"])}
