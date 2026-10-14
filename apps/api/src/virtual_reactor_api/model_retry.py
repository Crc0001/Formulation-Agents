"""Classify transient model-provider failures without exposing response data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import httpx


ModelRetryCategory = Literal[
    "timeout",
    "connection",
    "conflict",
    "rate_limit",
    "upstream_5xx",
    "non_retryable",
]


@dataclass(frozen=True, slots=True)
class ModelRetryDecision:
    retryable: bool
    category: ModelRetryCategory
    statusCode: int | None


def classify_model_error(error: BaseException) -> ModelRetryDecision:
    """Return a bounded retry decision using structured exception attributes."""

    for current in _exception_chain(error):
        status_code = _status_code(current)
        if status_code is not None:
            return _classify_status(status_code)
        if isinstance(current, (TimeoutError, httpx.TimeoutException)) or (
            type(current).__name__ == "APITimeoutError"
        ):
            return ModelRetryDecision(True, "timeout", None)
        if isinstance(current, (ConnectionError, httpx.NetworkError)) or (
            type(current).__name__ == "APIConnectionError"
        ):
            return ModelRetryDecision(True, "connection", None)
    return ModelRetryDecision(False, "non_retryable", None)


def _classify_status(status_code: int) -> ModelRetryDecision:
    if status_code == 408:
        return ModelRetryDecision(True, "timeout", status_code)
    if status_code == 409:
        return ModelRetryDecision(True, "conflict", status_code)
    if status_code == 429:
        return ModelRetryDecision(True, "rate_limit", status_code)
    if status_code >= 500:
        return ModelRetryDecision(True, "upstream_5xx", status_code)
    return ModelRetryDecision(False, "non_retryable", status_code)


def _status_code(error: BaseException) -> int | None:
    direct = getattr(error, "status_code", None)
    if isinstance(direct, int):
        return direct
    response = getattr(error, "response", None)
    nested = getattr(response, "status_code", None)
    return nested if isinstance(nested, int) else None


def _exception_chain(error: BaseException):
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__
