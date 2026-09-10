from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FORBIDDEN_PUBLIC_PATTERNS = (
    re.compile(r"(?:ak_|sk-)[A-Za-z0-9_-]{16,}"),
    re.compile(r"(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]{16,}"),
    re.compile(r"(?:DEEPSEEK_API_KEY|WIND_APP_SECRET|WIND_APP_ID|Authorization\s*:)", re.IGNORECASE),
    re.compile(r"[A-Za-z]:\\(?:Users|finance agent)\\", re.IGNORECASE),
    re.compile(r"file://", re.IGNORECASE),
    re.compile(r"<script\b", re.IGNORECASE),
    re.compile(r"\son[a-z]+\s*=", re.IGNORECASE),
    re.compile(r"javascript\s*:", re.IGNORECASE),
)


@dataclass(frozen=True)
class PublishedReport:
    report_date: str
    kind: str
    mode: str
    published_at: str
    html_path: Path
    publication_path: Path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_public_html(path: Path) -> None:
    if path.is_symlink():
        raise ValueError(f"symbolic links are not publishable: {path}")
    text = path.read_text(encoding="utf-8-sig")
    lowered = text.lower()
    if "<html" not in lowered or not re.search(r"charset\s*=\s*['\"]utf-8['\"]", lowered):
        raise ValueError(f"not a standalone UTF-8 HTML report: {path}")
    for pattern in FORBIDDEN_PUBLIC_PATTERNS:
        if pattern.search(text):
            raise ValueError(f"public HTML rejected by safety rule {pattern.pattern}: {path}")


def _load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"object expected: {path}")
    return value


def _kind(publication: dict) -> str | None:
    schema = publication.get("schema_version")
    if schema == "publication.v1" and publication.get("slot") == "08:00":
        return "morning"
    if schema == "review.publication.v1" or publication.get("report_type") == "post_market_review":
        return "review"
    return None


def _report_html(publication_path: Path, kind: str) -> Path | None:
    if kind == "morning":
        candidate = publication_path.parent / "report.html"
        return candidate if candidate.is_file() else None
    candidates = sorted(publication_path.parent.glob("*.html"))
    return candidates[0] if len(candidates) == 1 else None


def _expected_hash(publication_path: Path, publication: dict, kind: str) -> str | None:
    if kind == "review":
        hashes = publication.get("artifact_hashes") or {}
        return hashes.get("html")
    ready_path = publication_path.parent / "READY.json"
    if not ready_path.is_file():
        return None
    hashes = _load_json(ready_path).get("hashes") or {}
    return hashes.get("report_html")


def discover_reports(roots: Iterable[Path]) -> list[PublishedReport]:
    selected: dict[tuple[str, str], PublishedReport] = {}
    visited: set[Path] = set()
    for root in roots:
        resolved_root = root.resolve()
        if resolved_root in visited or not resolved_root.is_dir():
            continue
        visited.add(resolved_root)
        for publication_path in resolved_root.rglob("publication.json"):
            publication = _load_json(publication_path)
            report_date = str(publication.get("report_date", ""))
            mode = str(publication.get("mode", ""))
            kind = _kind(publication)
            if mode == "test" or kind is None or not DATE_RE.fullmatch(report_date):
                continue
            datetime.strptime(report_date, "%Y-%m-%d")
            html_path = _report_html(publication_path, kind)
            expected = _expected_hash(publication_path, publication, kind)
            if html_path is None or not expected or _sha256(html_path).lower() != str(expected).lower():
                continue
            validate_public_html(html_path)
            item = PublishedReport(
                report_date=report_date,
                kind=kind,
                mode=mode,
                published_at=str(publication.get("published_at", "")),
                html_path=html_path,
                publication_path=publication_path,
            )
            key = (report_date, kind)
            current = selected.get(key)
            rank = (1 if item.mode == "production" else 0, item.published_at)
            current_rank = (1 if current and current.mode == "production" else 0, current.published_at if current else "")
            if current is None or rank > current_rank:
                selected[key] = item
    return sorted(selected.values(), key=lambda item: (item.report_date, item.kind))


def archive_reports(roots: Iterable[Path], destination: Path) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for report in discover_reports(roots):
        day = report.report_date.replace("-", "")
        target = destination / day[:4] / day[4:6] / day / f"{report.kind}.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        content = report.html_path.read_bytes()
        if not target.exists() or target.read_bytes() != content:
            target.write_bytes(content)
        written.append(target)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Archive allowlisted published report HTML for GitHub Pages.")
    parser.add_argument("--morning-root", type=Path)
    parser.add_argument("--review-root", type=Path)
    parser.add_argument("--output", type=Path, default=Path("published-reports"))
    args = parser.parse_args()
    roots = [path for path in (args.morning_root, args.review_root) if path]
    if not roots:
        raise SystemExit("at least one report root is required")
    written = archive_reports(roots, args.output)
    print(json.dumps({"status": "PASS", "archived_html": len(written), "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
