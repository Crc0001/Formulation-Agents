"""Versioned contracts for model evaluation and audit records."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import Field, StringConstraints

from virtual_reactor_api.contracts import StrictModel


EVALUATION_SCHEMA_VERSION = "1.15.0"
EvaluationSchemaVersion = Annotated[
    str,
    StringConstraints(pattern=r"^\d+\.\d+\.\d+$"),
]
EvaluationStatus = Literal[
    "running",
    "generated",
    "ready",
    "ready_with_warnings",
    "draft_ready",
    "draft_blocked",
    "blocked",
    "needs_clarification",
    "failed",
]


class EvaluationEvent(StrictModel):
    runId: str
    sequence: int = Field(ge=1)
    eventType: str
    createdAt: datetime
    payload: dict[str, Any]
    payloadSha256: str


class EvaluationRunSummary(StrictModel):
    evaluationSchemaVersion: EvaluationSchemaVersion = EVALUATION_SCHEMA_VERSION
    runId: str
    createdAt: datetime
    completedAt: datetime | None
    status: EvaluationStatus
    request: dict[str, Any]
    metadata: dict[str, Any]
    eventCount: int = Field(ge=0)
    error: str | None


class EvaluationRunDetail(EvaluationRunSummary):
    finalResult: dict[str, Any] | None
    events: list[EvaluationEvent]


class EvaluationRunPage(StrictModel):
    items: list[EvaluationRunSummary]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=200)
    offset: int = Field(ge=0)
