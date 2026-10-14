"""Read-only HTTP access and exports for model evaluation audit records."""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from virtual_reactor_api.agent_runtime import resolve_evaluation_database_path
from virtual_reactor_api.evaluation_contracts import (
    EvaluationRunDetail,
    EvaluationRunPage,
    EvaluationStatus,
)
from virtual_reactor_api.evaluation_export import export_jsonl, export_xlsx
from virtual_reactor_api.evaluation_store import EvaluationStore


router = APIRouter(prefix="/api/v1/evaluations", tags=["agent-evaluations"])


@lru_cache(maxsize=1)
def get_evaluation_store() -> EvaluationStore:
    return EvaluationStore(resolve_evaluation_database_path())


EvaluationStoreDep = Annotated[EvaluationStore, Depends(get_evaluation_store)]


@router.get("/runs", response_model=EvaluationRunPage)
def list_evaluation_runs(
    store: EvaluationStoreDep,
    status: EvaluationStatus | None = None,
    query: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EvaluationRunPage:
    return store.list_runs(status=status, query=query, limit=limit, offset=offset)


@router.get("/runs/{run_id}", response_model=EvaluationRunDetail)
def get_evaluation_run(run_id: str, store: EvaluationStoreDep) -> EvaluationRunDetail:
    detail = store.get_run(run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="未找到该评估记录。")
    return detail


@router.get("/export.jsonl")
def download_evaluations_jsonl(
    store: EvaluationStoreDep,
    status: EvaluationStatus | None = None,
    query: str | None = None,
) -> Response:
    payload = export_jsonl(_collect_runs(store, status=status, query=query))
    return _download(payload, "jsonl", "application/x-ndjson; charset=utf-8")


@router.get("/export.xlsx")
def download_evaluations_xlsx(
    store: EvaluationStoreDep,
    status: EvaluationStatus | None = None,
    query: str | None = None,
) -> Response:
    payload = export_xlsx(_collect_runs(store, status=status, query=query))
    return _download(
        payload,
        "xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def _collect_runs(
    store: EvaluationStore,
    *,
    status: EvaluationStatus | None,
    query: str | None,
) -> list[EvaluationRunDetail]:
    details: list[EvaluationRunDetail] = []
    offset = 0
    while True:
        page = store.list_runs(status=status, query=query, limit=200, offset=offset)
        for summary in page.items:
            detail = store.get_run(summary.runId)
            if detail is not None:
                details.append(detail)
        offset += len(page.items)
        if offset >= page.total or not page.items:
            return details


def _download(payload: bytes, extension: str, media_type: str) -> Response:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return Response(
        content=payload,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="virtual-reactor-evaluations-{stamp}.{extension}"'
            )
        },
    )
