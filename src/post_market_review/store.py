from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS review_runs (
  run_id TEXT PRIMARY KEY, report_date TEXT NOT NULL, mode TEXT NOT NULL,
  state TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  manifest_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS receipts (
  receipt_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, provider TEXT NOT NULL,
  dataset_id TEXT NOT NULL, received_at TEXT NOT NULL, raw_path TEXT NOT NULL,
  raw_sha256 TEXT NOT NULL, request_sha256 TEXT, attempt INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL, error_code TEXT,
  FOREIGN KEY(run_id) REFERENCES review_runs(run_id)
);
CREATE TABLE IF NOT EXISTS snapshots (
  snapshot_hash TEXT PRIMARY KEY, run_id TEXT NOT NULL, report_date TEXT NOT NULL,
  cutoff_at TEXT NOT NULL, payload_json TEXT NOT NULL,
  FOREIGN KEY(run_id) REFERENCES review_runs(run_id)
);
CREATE TABLE IF NOT EXISTS publications (
  publication_id TEXT PRIMARY KEY, report_date TEXT NOT NULL, slot TEXT NOT NULL,
  mode TEXT NOT NULL, run_id TEXT NOT NULL, published_at TEXT NOT NULL,
  manifest_json TEXT NOT NULL,
  UNIQUE(report_date, slot, mode)
);
"""


class Ledger:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            receipt_columns = {row[1] for row in connection.execute("PRAGMA table_info(receipts)")}
            if "request_sha256" not in receipt_columns or "attempt" not in receipt_columns:
                backup_path = path.with_name(path.name + ".pre-receipt-v2.bak")
                if not backup_path.exists():
                    with sqlite3.connect(backup_path) as backup_connection:
                        connection.backup(backup_connection)
                if "request_sha256" not in receipt_columns:
                    connection.execute("ALTER TABLE receipts ADD COLUMN request_sha256 TEXT")
                if "attempt" not in receipt_columns:
                    connection.execute("ALTER TABLE receipts ADD COLUMN attempt INTEGER NOT NULL DEFAULT 1")

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def create_run(self, manifest: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO review_runs VALUES (?,?,?,?,?,?,?)",
                (manifest["run_id"], manifest["report_date"], manifest["mode"], manifest["state"],
                 manifest["created_at"], manifest["created_at"], json.dumps(manifest, ensure_ascii=False)),
            )

    def update_run(self, manifest: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE review_runs SET state=?,updated_at=?,manifest_json=? WHERE run_id=?",
                (manifest["state"], manifest["updated_at"], json.dumps(manifest, ensure_ascii=False), manifest["run_id"]),
            )

    def add_receipt(self, run_id: str, receipt: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO receipts (
                     receipt_id,run_id,provider,dataset_id,received_at,raw_path,raw_sha256,
                     request_sha256,attempt,status,error_code
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (receipt["receipt_id"], run_id, receipt["provider"], receipt["dataset_id"], receipt["received_at"],
                 receipt["raw_path"], receipt["raw_sha256"], receipt.get("request_sha256"), receipt.get("attempt", 1),
                 receipt["status"], receipt.get("error_code")),
            )

    def add_snapshot(self, run_id: str, snapshot: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO snapshots VALUES (?,?,?,?,?)",
                (snapshot["snapshot_hash"], run_id, snapshot["report_date"], snapshot["cutoff_at"], json.dumps(snapshot, ensure_ascii=False)),
            )

    def publication_for(self, report_date: str, slot: str, mode: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT manifest_json FROM publications WHERE report_date=? AND slot=? AND mode=?",
                (report_date, slot, mode),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def latest_ready(self, report_date: str, mode: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT manifest_json FROM review_runs WHERE report_date=? AND mode=? AND state='READY' ORDER BY updated_at DESC LIMIT 1",
                (report_date, mode),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def add_publication(self, publication: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO publications VALUES (?,?,?,?,?,?,?)",
                (publication["publication_id"], publication["report_date"], publication["slot"], publication["mode"],
                 publication["run_id"], publication["published_at"], json.dumps(publication, ensure_ascii=False)),
            )

    def run(self, run_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT manifest_json FROM review_runs WHERE run_id=?", (run_id,)).fetchone()
        return json.loads(row[0]) if row else None
