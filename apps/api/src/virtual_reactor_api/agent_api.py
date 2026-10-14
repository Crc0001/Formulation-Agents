"""FastAPI routes for natural-language reaction configuration generation."""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from functools import lru_cache
from typing import Annotated, Any, Protocol

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from virtual_reactor_api.agent_models import (
    AgentGenerationResult,
    ReactionGenerationRequest,
)
from virtual_reactor_api.agent_runtime import (
    AgentConfigurationError,
    AgentRuntimeError,
    create_reaction_agent_service,
)
from virtual_reactor_api.agent_service import ReactionAgentService


router = APIRouter(prefix="/api/v1/agent", tags=["reaction-agent"])


@lru_cache(maxsize=1)
def _create_cached_service() -> ReactionAgentService:
    return create_reaction_agent_service()


class _LazyReactionAgentService:
    """Delay external configuration until after FastAPI validates the body."""

    async def generate(
        self,
        request: ReactionGenerationRequest,
        on_progress: Any = None,
    ) -> AgentGenerationResult:
        return await _create_cached_service().generate(request, on_progress)


_lazy_service = _LazyReactionAgentService()


class ReactionAgentRunner(Protocol):
    async def generate(
        self,
        request: ReactionGenerationRequest,
        on_progress: Any = None,
    ) -> AgentGenerationResult: ...


def get_reaction_agent_service() -> ReactionAgentRunner:
    """Return a lazy service without reading or exposing provider credentials."""

    return _lazy_service


ReactionAgentServiceDep = Annotated[
    ReactionAgentRunner,
    Depends(get_reaction_agent_service),
]


@router.post(
    "/reaction-configs",
    response_model=AgentGenerationResult,
)
async def generate_reaction_config(
    request: ReactionGenerationRequest,
    service: ReactionAgentServiceDep,
) -> AgentGenerationResult:
    """Research and generate one reaction configuration."""

    try:
        return await service.generate(request)
    except AgentConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except AgentRuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error),
        ) from error


@router.post("/reaction-configs/stream")
async def stream_reaction_config(
    request: ReactionGenerationRequest,
    service: ReactionAgentServiceDep,
) -> StreamingResponse:
    """Stream real orchestration stages followed by one structured result."""

    async def event_stream():
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

        async def report(phase: str, message: str, _revision_count: int) -> None:
            await queue.put(
                {
                    "kind": "progress",
                    "phase": phase,
                    "message": message,
                }
            )

        async def produce() -> None:
            try:
                result = await service.generate(request, report)
                await queue.put(
                    {
                        "kind": "result",
                        "result": result.model_dump(mode="json"),
                    }
                )
            except (AgentConfigurationError, AgentRuntimeError) as error:
                await queue.put({"kind": "error", "message": str(error)})
            except Exception:
                await queue.put(
                    {"kind": "error", "message": "智能体执行失败，请稍后重试。"}
                )
            finally:
                await queue.put(None)

        producer = asyncio.create_task(produce())
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield "data: " + json.dumps(
                    event,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ) + "\n\n"
        finally:
            if not producer.done():
                producer.cancel()
                with suppress(asyncio.CancelledError):
                    await producer

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
