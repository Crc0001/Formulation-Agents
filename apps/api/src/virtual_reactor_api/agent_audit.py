"""Audit every model turn made inside one Deep Agent run."""

from __future__ import annotations

import asyncio
import re
from threading import Lock
import time
from time import perf_counter
from typing import Any, Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse

from virtual_reactor_api.evaluation_recorder import (
    record_evaluation_event,
    serialize_for_evaluation,
)
from virtual_reactor_api.evaluation_store import redact_sensitive
from virtual_reactor_api.model_retry import ModelRetryDecision, classify_model_error


_INLINE_SECRET = re.compile(
    r"(?i)(api[_-]?key|authorization|access[_-]?token|password|secret)\s*[:=]\s*[^\s,;]+"
)


class AgentModelTurnBudgetExceeded(RuntimeError):
    """Raised when one run exceeds its configured model-turn budget."""


class AgentAuditMiddleware(AgentMiddleware):
    def __init__(
        self,
        *,
        max_model_turns: int,
        retry_delay_seconds: float = 10,
        async_sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
        sync_sleeper: Callable[[float], None] = time.sleep,
        progress_reporter: Callable[[str], Awaitable[None]] | None = None,
        event_recorder: Callable[[str, dict[str, Any]], None] = record_evaluation_event,
    ) -> None:
        if max_model_turns < 1:
            raise ValueError("max_model_turns must be positive")
        if retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds must not be negative")
        self._max_model_turns = max_model_turns
        self._retry_delay_seconds = retry_delay_seconds
        self._async_sleeper = async_sleeper
        self._sync_sleeper = sync_sleeper
        self._progress_reporter = progress_reporter
        self._event_recorder = event_recorder
        self._turn_count = 0
        self._budget_recorded = False
        self._lock = Lock()

    def wrap_model_call(self, request: ModelRequest, handler: Callable) -> Any:
        turn = self._begin_turn()
        for attempt in (1, 2):
            self._record_request(turn, request, attempt)
            started = perf_counter()
            try:
                response = handler(request)
            except Exception as error:
                self._record_error(turn, attempt, error, started)
                decision = classify_model_error(error)
                if not decision.retryable:
                    raise
                if attempt == 2:
                    self._record_retry_exhausted(turn, decision)
                    raise
                self._record_retry_scheduled(turn, decision)
                self._sync_sleeper(self._retry_delay_seconds)
                continue
            self._record_response(turn, attempt, response, started)
            if attempt == 2:
                self._record_retry_succeeded(turn)
            return response
        raise AssertionError("unreachable model retry state")

    async def awrap_model_call(self, request: ModelRequest, handler: Callable) -> Any:
        turn = self._begin_turn()
        for attempt in (1, 2):
            self._record_request(turn, request, attempt)
            started = perf_counter()
            try:
                response = await handler(request)
            except Exception as error:
                self._record_error(turn, attempt, error, started)
                decision = classify_model_error(error)
                if not decision.retryable:
                    raise
                if attempt == 2:
                    self._record_retry_exhausted(turn, decision)
                    raise
                self._record_retry_scheduled(turn, decision)
                await self._report_progress(
                    "模型服务暂时不可用，10 秒后自动重试（1/1）。"
                )
                await self._async_sleeper(self._retry_delay_seconds)
                continue
            self._record_response(turn, attempt, response, started)
            if attempt == 2:
                self._record_retry_succeeded(turn)
                await self._report_progress("模型请求已恢复，继续生成。")
            return response
        raise AssertionError("unreachable model retry state")

    def _begin_turn(self) -> int:
        with self._lock:
            self._turn_count += 1
            turn = self._turn_count
            if turn > self._max_model_turns:
                if not self._budget_recorded:
                    self._budget_recorded = True
                    self._event_recorder(
                        "agent_budget_exhausted",
                        {
                            "budgetType": "model_turns",
                            "maximum": self._max_model_turns,
                            "attemptedTurn": turn,
                        },
                    )
                raise AgentModelTurnBudgetExceeded(
                    "本次智能体模型调用预算已耗尽。"
                )
        return turn

    def _record_request(
        self,
        turn: int,
        request: ModelRequest,
        attempt: int,
    ) -> None:
        self._event_recorder(
            "agent_model_request",
            _sanitize(
                {
                    "turn": turn,
                    "attempt": attempt,
                    "messages": request.messages,
                    "systemMessage": request.system_message,
                    "tools": [_tool_name(item) for item in request.tools],
                    "toolChoice": request.tool_choice,
                    "modelSettings": request.model_settings,
                }
            ),
        )

    def _record_response(
        self,
        turn: int,
        attempt: int,
        response: ModelResponse,
        started: float,
    ) -> None:
        messages = getattr(response, "result", [])
        usage: dict[str, int] = {}
        finish_reasons: list[str] = []
        for message in messages:
            metadata = getattr(message, "usage_metadata", None)
            if isinstance(metadata, dict):
                for key, value in metadata.items():
                    if isinstance(value, int):
                        usage[key] = usage.get(key, 0) + value
            response_metadata = getattr(message, "response_metadata", None)
            if isinstance(response_metadata, dict):
                reason = response_metadata.get("finish_reason")
                if isinstance(reason, str):
                    finish_reasons.append(reason)
        self._event_recorder(
            "agent_model_response",
            _sanitize(
                {
                    "turn": turn,
                    "attempt": attempt,
                    "messages": messages,
                    "structuredResponse": getattr(
                        response, "structured_response", None
                    ),
                    "usage": usage,
                    "finishReasons": finish_reasons,
                    "durationMs": max(
                        0, round((perf_counter() - started) * 1000)
                    ),
                }
            ),
        )

    def _record_error(
        self,
        turn: int,
        attempt: int,
        error: Exception,
        started: float,
    ) -> None:
        self._event_recorder(
            "agent_model_error",
            _sanitize(
                {
                    "turn": turn,
                    "attempt": attempt,
                    "errorType": type(error).__name__,
                    "message": str(error),
                    "durationMs": max(
                        0, round((perf_counter() - started) * 1000)
                    ),
                }
            ),
        )

    def _record_retry_scheduled(
        self,
        turn: int,
        decision: ModelRetryDecision,
    ) -> None:
        self._event_recorder(
            "agent_model_retry_scheduled",
            {
                "turn": turn,
                "failedAttempt": 1,
                "nextAttempt": 2,
                "delaySeconds": self._retry_delay_seconds,
                "category": decision.category,
                "statusCode": decision.statusCode,
            },
        )

    def _record_retry_succeeded(self, turn: int) -> None:
        self._event_recorder(
            "agent_model_retry_succeeded",
            {"turn": turn, "successfulAttempt": 2},
        )

    def _record_retry_exhausted(
        self,
        turn: int,
        decision: ModelRetryDecision,
    ) -> None:
        self._event_recorder(
            "agent_model_retry_exhausted",
            {
                "turn": turn,
                "attempts": 2,
                "category": decision.category,
                "statusCode": decision.statusCode,
            },
        )

    async def _report_progress(self, message: str) -> None:
        if self._progress_reporter is None:
            return
        try:
            await self._progress_reporter(message)
        except Exception as error:
            self._event_recorder(
                "agent_model_retry_progress_failed",
                _sanitize(
                    {
                        "errorType": type(error).__name__,
                        "message": str(error),
                    }
                ),
            )


def _tool_name(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or value.get("function", {}).get("name") or "unknown")
    return str(getattr(value, "name", value.__class__.__name__))


def _sanitize(value: Any) -> Any:
    serialized = redact_sensitive(serialize_for_evaluation(value))
    return _scrub_text(serialized)


def _scrub_text(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _scrub_text(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_scrub_text(child) for child in value]
    if isinstance(value, str):
        return _INLINE_SECRET.sub(lambda match: f"{match.group(1)}=[已移除]", value)
    return value
