"""SQLite persistence for complete, append-only model evaluation records."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from virtual_reactor_api.evaluation_contracts import (
    EVALUATION_SCHEMA_VERSION,
    EvaluationEvent,
    EvaluationRunDetail,
    EvaluationRunPage,
    EvaluationRunSummary,
    EvaluationStatus,
)


_REDACTED = "[已从评估记录中移除]"
_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "access_token",
    "refresh_token",
    "secret",
    "client_secret",
    "password",
}
_SENSITIVE_URL_VALUE = re.compile(
    r"(?i)([?&](?:api[_-]?key|apikey|access_token|refresh_token|client_secret|password)=)[^&#\s]*"
)


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): (
                _REDACTED
                if str(key).lower().replace("-", "_") in _SENSITIVE_KEYS
                else redact_sensitive(child)
            )
            for key, child in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_sensitive(child) for child in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "model_dump"):
        return redact_sensitive(value.model_dump(mode="json"))
    if isinstance(value, str):
        return _SENSITIVE_URL_VALUE.sub(rf"\1{_REDACTED}", value)
    return value


class EvaluationStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def create_run(
        self,
        request: Mapping[str, Any],
        metadata: Mapping[str, Any],
        *,
        run_id: str | None = None,
    ) -> str:
        active_run_id = run_id or str(uuid4())
        created_at = _now()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO evaluation_runs (
                    run_id, schema_version, created_at, status,
                    request_json, metadata_json, event_count
                ) VALUES (?, ?, ?, 'running', ?, ?, 0)
                """,
                (
                    active_run_id,
                    EVALUATION_SCHEMA_VERSION,
                    created_at,
                    canonical_json(redact_sensitive(request)),
                    canonical_json(redact_sensitive(metadata)),
                ),
            )
        return active_run_id

    def append_event(
        self,
        run_id: str,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> EvaluationEvent:
        safe_payload = redact_sensitive(payload)
        payload_json = canonical_json(safe_payload)
        payload_sha256 = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        created_at = _now()
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT event_count FROM evaluation_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown evaluation run: {run_id}")
            sequence = int(row[0]) + 1
            connection.execute(
                """
                INSERT INTO evaluation_events (
                    run_id, sequence, event_type, created_at,
                    payload_json, payload_sha256
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    sequence,
                    event_type,
                    created_at,
                    payload_json,
                    payload_sha256,
                ),
            )
            connection.execute(
                "UPDATE evaluation_runs SET event_count = ? WHERE run_id = ?",
                (sequence, run_id),
            )
            connection.commit()
        return EvaluationEvent(
            runId=run_id,
            sequence=sequence,
            eventType=event_type,
            createdAt=datetime.fromisoformat(created_at),
            payload=safe_payload,
            payloadSha256=payload_sha256,
        )

    def complete_run(
        self,
        run_id: str,
        status: EvaluationStatus,
        *,
        final_result: Mapping[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        if status == "running":
            raise ValueError("A completed evaluation run cannot remain running")
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE evaluation_runs
                SET completed_at = ?, status = ?, final_result_json = ?, error = ?
                WHERE run_id = ?
                """,
                (
                    _now(),
                    status,
                    None
                    if final_result is None
                    else canonical_json(redact_sensitive(final_result)),
                    error,
                    run_id,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown evaluation run: {run_id}")

    def get_run(self, run_id: str) -> EvaluationRunDetail | None:
        with self._connect() as connection:
            run = connection.execute(
                "SELECT * FROM evaluation_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if run is None:
                return None
            events = connection.execute(
                """
                SELECT run_id, sequence, event_type, created_at,
                       payload_json, payload_sha256
                FROM evaluation_events
                WHERE run_id = ? ORDER BY sequence ASC
                """,
                (run_id,),
            ).fetchall()
        return _detail_from_rows(run, events)

    def list_runs(
        self,
        *,
        status: EvaluationStatus | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> EvaluationRunPage:
        if not 1 <= limit <= 200 or offset < 0:
            raise ValueError("Invalid evaluation pagination")
        clauses: list[str] = []
        parameters: list[Any] = []
        if status is not None:
            clauses.append("status = ?")
            parameters.append(status)
        if query is not None and query.strip():
            clauses.append("(request_json LIKE ? OR metadata_json LIKE ? OR run_id LIKE ?)")
            pattern = f"%{query.strip()}%"
            parameters.extend([pattern, pattern, pattern])
        where = "" if not clauses else " WHERE " + " AND ".join(clauses)
        with self._connect() as connection:
            total = int(
                connection.execute(
                    "SELECT COUNT(*) FROM evaluation_runs" + where,
                    parameters,
                ).fetchone()[0]
            )
            rows = connection.execute(
                "SELECT * FROM evaluation_runs"
                + where
                + " ORDER BY created_at DESC, run_id DESC LIMIT ? OFFSET ?",
                [*parameters, limit, offset],
            ).fetchall()
        return EvaluationRunPage(
            items=[_summary_from_row(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA foreign_keys=ON;
                CREATE TABLE IF NOT EXISTS evaluation_runs (
                    run_id TEXT PRIMARY KEY,
                    schema_version TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    status TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    final_result_json TEXT,
                    error TEXT,
                    event_count INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS evaluation_events (
                    run_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    PRIMARY KEY (run_id, sequence),
                    FOREIGN KEY (run_id) REFERENCES evaluation_runs(run_id)
                        ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_evaluation_runs_created
                    ON evaluation_runs(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_evaluation_runs_status
                    ON evaluation_runs(status);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _summary_from_row(row: sqlite3.Row) -> EvaluationRunSummary:
    return EvaluationRunSummary(
        evaluationSchemaVersion=row["schema_version"],
        runId=row["run_id"],
        createdAt=datetime.fromisoformat(row["created_at"]),
        completedAt=(
            None
            if row["completed_at"] is None
            else datetime.fromisoformat(row["completed_at"])
        ),
        status=row["status"],
        request=json.loads(row["request_json"]),
        metadata=json.loads(row["metadata_json"]),
        eventCount=row["event_count"],
        error=row["error"],
    )


def _detail_from_rows(
    run: sqlite3.Row,
    events: list[sqlite3.Row],
) -> EvaluationRunDetail:
    summary = _summary_from_row(run)
    return EvaluationRunDetail(
        **summary.model_dump(),
        finalResult=(
            None
            if run["final_result_json"] is None
            else json.loads(run["final_result_json"])
        ),
        events=[
            EvaluationEvent(
                runId=row["run_id"],
                sequence=row["sequence"],
                eventType=row["event_type"],
                createdAt=datetime.fromisoformat(row["created_at"]),
                payload=json.loads(row["payload_json"]),
                payloadSha256=row["payload_sha256"],
            )
            for row in events
        ],
    )
