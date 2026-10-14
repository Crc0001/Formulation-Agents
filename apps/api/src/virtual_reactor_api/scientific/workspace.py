"""Persistent, run-scoped filesystem workspace primitives."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from threading import RLock
from typing import Any
from uuid import UUID, uuid4


_DIRECTORIES = (
    "input",
    "evidence",
    "analysis",
    "analysis/tool-receipts",
    "output",
)


class AgentRunWorkspace:
    def __init__(self, run_id: str, root: Path) -> None:
        self.run_id = run_id
        self.root = root.resolve()
        self._write_lock = RLock()

    def resolve(self, relative_path: str) -> Path:
        if not relative_path or "\x00" in relative_path or "\\" in relative_path:
            raise ValueError("path must remain inside the workspace")
        pure = PurePosixPath(relative_path)
        if pure.is_absolute() or ".." in pure.parts or ":" in relative_path:
            raise ValueError("path must remain inside the workspace")
        target = (self.root / Path(*pure.parts)).resolve(strict=False)
        if target != self.root and self.root not in target.parents:
            raise ValueError("path must remain inside the workspace")
        current = target.parent
        while current != self.root:
            if current.exists() and current.is_symlink():
                raise ValueError("symlink path must remain inside the workspace")
            current = current.parent
        return target

    def write_json(self, relative_path: str, value: Any) -> Path:
        payload = json.dumps(
            _json_value(value), ensure_ascii=False, sort_keys=True, indent=2
        ).encode("utf-8")
        target = self.resolve(relative_path)
        with self._write_lock:
            _atomic_write(target, payload)
        return target

    def append_jsonl(self, relative_path: str, value: Any) -> Path:
        target = self.resolve(relative_path)
        line = json.dumps(
            _json_value(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        with self._write_lock:
            existing = target.read_text("utf-8") if target.exists() else ""
            _atomic_write(target, f"{existing}{line}\n".encode("utf-8"))
        return target


class WorkspaceManager:
    def __init__(self, runs_root: Path) -> None:
        self.runs_root = runs_root.resolve()

    def create(self, run_id: str) -> AgentRunWorkspace:
        try:
            parsed = UUID(run_id)
        except (ValueError, AttributeError) as error:
            raise ValueError("runId must be a UUID") from error
        normalized = str(parsed)
        candidate = (self.runs_root / normalized).resolve(strict=False)
        if candidate.parent != self.runs_root:
            raise ValueError("run workspace must be a direct child of runs root")
        candidate.mkdir(parents=True, exist_ok=True)
        workspace = AgentRunWorkspace(normalized, candidate)
        for relative in _DIRECTORIES:
            workspace.resolve(relative).mkdir(parents=True, exist_ok=True)
        workspace.write_json(
            "manifest.json",
            {
                "manifestVersion": "1.0.0",
                "runId": normalized,
                "createdAt": datetime.now(UTC).isoformat(),
                "status": "running",
                "artifacts": [],
            },
        )
        return workspace


def _atomic_write(target: Path, payload: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.parent / f".{target.name}.{uuid4().hex}.tmp"
    try:
        with temporary.open("wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def _json_value(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _json_value(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(key): _json_value(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(child) for child in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return repr(value)

