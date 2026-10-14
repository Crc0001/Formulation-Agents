"""SerpApi search tools for the generator agent."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from langchain_core.tools import BaseTool, ToolException, tool

from virtual_reactor_api.evaluation_recorder import record_evaluation_event


SERPAPI_SEARCH_URL = "https://serpapi.com/search.json"
logger = logging.getLogger(__name__)

_TRANSIENT_REQUEST_ERRORS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadError,
    httpx.ReadTimeout,
    httpx.RemoteProtocolError,
)

_NO_RESULTS_MARKERS = (
    "hasn't returned any results",
    "has not returned any results",
    "no results for this query",
)


@dataclass(frozen=True, slots=True)
class SerpApiResponse:
    payload: Mapping[str, Any]
    http_status: int
    provider_status: str
    is_empty: bool = False


class SerpApiToolError(ToolException):
    def __init__(
        self,
        message: str,
        *,
        category: str,
        http_status: int | None = None,
        provider_status: str = "",
        provider_message: str = "",
    ) -> None:
        super().__init__(message)
        self.category = category
        self.http_status = http_status
        self.provider_status = provider_status
        self.provider_message = provider_message


def create_serpapi_scholar_tool(
    api_key: str,
    *,
    max_results: int | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    retry_delay_seconds: float = 0.25,
) -> BaseTool:
    """Create a Scholar-only search tool for the main generator."""

    @tool("search_chemical_literature")
    async def search_chemical_literature(query: str) -> str:
        """Search Google Scholar for chemical literature and return audit fields."""

        tool_name = "search_chemical_literature"
        engine = "google_scholar"
        record_evaluation_event(
            "search_request",
            {
                "tool": tool_name,
                "engine": engine,
                "query": query,
                "maxResults": max_results,
            },
        )
        try:
            response = await _request_serpapi_payload(
                api_key,
                engine=engine,
                query=query,
                service_name="Google Scholar",
                transport=transport,
                retry_delay_seconds=retry_delay_seconds,
                max_results=max_results,
            )
        except SerpApiToolError as error:
            record_evaluation_event(
                "search_error",
                {
                    "tool": tool_name,
                    "engine": engine,
                    "query": query,
                    "error": str(error),
                    "category": error.category,
                    "httpStatus": error.http_status,
                    "providerStatus": error.provider_status,
                    "providerMessage": error.provider_message,
                },
            )
            raise
        payload = response.payload
        if response.is_empty:
            record_evaluation_event(
                "search_empty",
                {
                    "tool": tool_name,
                    "engine": engine,
                    "query": query,
                    "httpStatus": response.http_status,
                    "providerStatus": response.provider_status,
                    "resultCount": 0,
                },
            )
        record_evaluation_event(
            "search_provider_response",
            {"tool": tool_name, "engine": engine, "query": query, "payload": payload},
        )
        result = json.dumps(
            normalize_scholar_results(payload, max_results=max_results),
            ensure_ascii=False,
        )
        record_evaluation_event(
            "search_result",
            {"tool": tool_name, "engine": engine, "query": query, "result": result},
        )
        return result

    search_chemical_literature.handle_tool_error = lambda error: str(error)
    return search_chemical_literature


def create_serpapi_google_tool(
    api_key: str,
    *,
    max_results: int | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    retry_delay_seconds: float = 0.25,
) -> BaseTool:
    """Create an ordinary-Google tool for authoritative web leads."""

    @tool("search_web_sources")
    async def search_web_sources(query: str) -> str:
        """Search ordinary Google for patents, SDS, databases, and source pages."""

        tool_name = "search_web_sources"
        engine = "google"
        record_evaluation_event(
            "search_request",
            {
                "tool": tool_name,
                "engine": engine,
                "query": query,
                "maxResults": max_results,
            },
        )
        try:
            response = await _request_serpapi_payload(
                api_key,
                engine=engine,
                query=query,
                service_name="普通 Google",
                transport=transport,
                retry_delay_seconds=retry_delay_seconds,
                max_results=max_results,
            )
        except SerpApiToolError as error:
            record_evaluation_event(
                "search_error",
                {
                    "tool": tool_name,
                    "engine": engine,
                    "query": query,
                    "error": str(error),
                    "category": error.category,
                    "httpStatus": error.http_status,
                    "providerStatus": error.provider_status,
                    "providerMessage": error.provider_message,
                },
            )
            raise
        payload = response.payload
        if response.is_empty:
            record_evaluation_event(
                "search_empty",
                {
                    "tool": tool_name,
                    "engine": engine,
                    "query": query,
                    "httpStatus": response.http_status,
                    "providerStatus": response.provider_status,
                    "resultCount": 0,
                },
            )
        record_evaluation_event(
            "search_provider_response",
            {"tool": tool_name, "engine": engine, "query": query, "payload": payload},
        )
        result = json.dumps(
            normalize_google_results(payload, max_results=max_results),
            ensure_ascii=False,
        )
        record_evaluation_event(
            "search_result",
            {"tool": tool_name, "engine": engine, "query": query, "result": result},
        )
        return result

    search_web_sources.handle_tool_error = lambda error: str(error)
    return search_web_sources


def create_serpapi_patents_tool(
    api_key: str,
    *,
    max_results: int | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    retry_delay_seconds: float = 0.25,
) -> BaseTool:
    """Create a Google-Patents-only discovery tool."""

    @tool("search_google_patents")
    async def search_google_patents(query: str) -> str:
        """Search Google Patents for relevant patent families and publication IDs."""

        tool_name = "search_google_patents"
        engine = "google_patents"
        record_evaluation_event(
            "search_request",
            {
                "tool": tool_name,
                "engine": engine,
                "query": query,
                "maxResults": max_results,
            },
        )
        try:
            response = await _request_serpapi_payload(
                api_key,
                engine=engine,
                query=query,
                service_name="Google Patents",
                transport=transport,
                retry_delay_seconds=retry_delay_seconds,
                max_results=max_results,
            )
        except SerpApiToolError as error:
            record_evaluation_event(
                "search_error",
                {
                    "tool": tool_name,
                    "engine": engine,
                    "query": query,
                    "error": str(error),
                    "category": error.category,
                    "httpStatus": error.http_status,
                    "providerStatus": error.provider_status,
                    "providerMessage": error.provider_message,
                },
            )
            raise
        payload = response.payload
        if response.is_empty:
            record_evaluation_event(
                "search_empty",
                {
                    "tool": tool_name,
                    "engine": engine,
                    "query": query,
                    "httpStatus": response.http_status,
                    "providerStatus": response.provider_status,
                    "resultCount": 0,
                },
            )
        record_evaluation_event(
            "search_provider_response",
            {"tool": tool_name, "engine": engine, "query": query, "payload": payload},
        )
        result = json.dumps(
            normalize_patent_results(payload, max_results=max_results),
            ensure_ascii=False,
        )
        record_evaluation_event(
            "search_result",
            {"tool": tool_name, "engine": engine, "query": query, "result": result},
        )
        return result

    search_google_patents.handle_tool_error = lambda error: str(error)
    return search_google_patents


async def _request_serpapi_payload(
    api_key: str,
    *,
    engine: str,
    query: str,
    service_name: str,
    transport: httpx.AsyncBaseTransport | None,
    retry_delay_seconds: float,
    max_results: int | None,
) -> SerpApiResponse:
    async with httpx.AsyncClient(
        transport=transport,
        timeout=httpx.Timeout(15.0),
    ) as client:
        for attempt in range(2):
            try:
                params: dict[str, str | int] = {
                    "engine": engine,
                    "q": query,
                    "api_key": api_key,
                }
                if max_results is not None:
                    params["num"] = max_results
                response = await client.get(
                    SERPAPI_SEARCH_URL,
                    params=params,
                )
                if response.status_code >= 500 and attempt == 0:
                    logger.warning(
                        "%s request failed transiently; retrying "
                        "(attempt=1, error=%s)",
                        service_name,
                        f"HTTP {response.status_code}",
                    )
                    if retry_delay_seconds > 0:
                        await asyncio.sleep(retry_delay_seconds)
                    continue
                break
            except _TRANSIENT_REQUEST_ERRORS as error:
                if attempt == 0:
                    logger.warning(
                        "%s request failed transiently; retrying "
                        "(attempt=1, error=%s)",
                        service_name,
                        type(error).__name__,
                    )
                    if retry_delay_seconds > 0:
                        await asyncio.sleep(retry_delay_seconds)
                    continue
                raise SerpApiToolError(
                    f"无法连接 {service_name} 检索服务，请稍后重试。",
                    category="network",
                ) from error
            except httpx.RequestError as error:
                raise SerpApiToolError(
                    f"无法连接 {service_name} 检索服务，请稍后重试。",
                    category="network",
                ) from error

    try:
        payload = response.json()
    except ValueError as error:
        if response.status_code in {401, 403}:
            raise SerpApiToolError(
                f"SerpApi 密钥无效或无权访问 {service_name}。",
                category="authentication",
                http_status=response.status_code,
            ) from error
        if response.status_code == 429:
            raise SerpApiToolError(
                "SerpApi 检索额度已用尽或请求过于频繁，请稍后重试或检查套餐。",
                category="quota_or_rate_limit",
                http_status=response.status_code,
            ) from error
        if response.status_code in {400, 422}:
            raise SerpApiToolError(
                f"{service_name} 检索参数无效，请调整查询后重试。",
                category="invalid_request",
                http_status=response.status_code,
            ) from error
        if response.status_code >= 500:
            raise SerpApiToolError(
                f"{service_name} 检索服务暂时不可用，请稍后重试。",
                category="provider_unavailable",
                http_status=response.status_code,
            ) from error
        raise SerpApiToolError(
            f"{service_name} 检索服务返回了无法解析的数据。",
            category="invalid_response",
            http_status=response.status_code,
        ) from error
    if not isinstance(payload, Mapping):
        raise SerpApiToolError(
            f"{service_name} 检索服务返回了无效数据。",
            category="invalid_response",
            http_status=response.status_code,
        )
    provider_status = _safe_provider_text(
        (payload.get("search_metadata") or {}).get("status")
        if isinstance(payload.get("search_metadata"), Mapping)
        else "",
        api_key,
    )
    provider_message = _safe_provider_text(payload.get("error"), api_key)
    if _is_empty_response(response.status_code, provider_status, provider_message, payload):
        return SerpApiResponse({}, response.status_code, provider_status, is_empty=True)
    if response.status_code >= 500:
        raise SerpApiToolError(
            f"{service_name} 检索服务暂时不可用，请稍后重试。",
            category="provider_unavailable",
            http_status=response.status_code,
            provider_status=provider_status,
            provider_message=provider_message,
        )
    if response.status_code in {401, 403} or _contains_any(
        provider_message, ("invalid api key", "unauthorized", "not authorized")
    ):
        raise SerpApiToolError(
            f"SerpApi 密钥无效或无权访问 {service_name}。",
            category="authentication",
            http_status=response.status_code,
            provider_status=provider_status,
            provider_message=provider_message,
        )
    if response.status_code == 429 or _contains_any(
        provider_message,
        ("run out of searches", "quota", "rate limit", "too many requests"),
    ):
        raise SerpApiToolError(
            "SerpApi 检索额度已用尽或请求过于频繁，请稍后重试或检查套餐。",
            category="quota_or_rate_limit",
            http_status=response.status_code,
            provider_status=provider_status,
            provider_message=provider_message,
        )
    if response.status_code in {400, 422} or _contains_any(
        provider_message, ("invalid parameter", "missing parameter")
    ):
        raise SerpApiToolError(
            f"{service_name} 检索参数无效，请调整查询后重试。",
            category="invalid_request",
            http_status=response.status_code,
            provider_status=provider_status,
            provider_message=provider_message,
        )
    if response.status_code >= 400 or provider_message:
        raise SerpApiToolError(
            f"SerpApi 拒绝了 {service_name} 请求：{provider_message or '未知原因'}。",
            category="provider_rejected",
            http_status=response.status_code,
            provider_status=provider_status,
            provider_message=provider_message,
        )
    return SerpApiResponse(payload, response.status_code, provider_status)


def _safe_provider_text(value: Any, api_key: str, *, limit: int = 240) -> str:
    text = str(value or "").replace(api_key, "***")
    return text[:limit]


def _contains_any(value: str, markers: tuple[str, ...]) -> bool:
    lowered = value.casefold()
    return any(marker in lowered for marker in markers)


def _is_empty_response(
    status_code: int,
    provider_status: str,
    provider_message: str,
    payload: Mapping[str, Any],
) -> bool:
    if status_code != 200 or provider_status.casefold() not in {"", "success"}:
        return False
    results = payload.get("organic_results")
    no_results = results is None or results == []
    return no_results and _contains_any(provider_message, _NO_RESULTS_MARKERS)


def normalize_scholar_results(
    payload: Mapping[str, Any],
    *,
    max_results: int | None = None,
    snippet_limit: int = 800,
) -> list[dict[str, Any]]:
    """Keep Scholar evidence fields without inventing metadata."""

    results = payload.get("organic_results")
    if not isinstance(results, list):
        return []

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in results:
        if not isinstance(item, Mapping):
            continue
        dedupe_key = _result_dedupe_key(item)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        publication_info = item.get("publication_info")
        inline_links = item.get("inline_links")
        cited_by = (
            inline_links.get("cited_by")
            if isinstance(inline_links, Mapping)
            else None
        )
        if max_results is not None and len(normalized) >= max_results:
            break
        normalized.append(
            {
                "title": str(item.get("title") or "未命名文献"),
                "link": str(item.get("link") or ""),
                "snippet": str(item.get("snippet") or "")[:snippet_limit],
                "publication_info": (
                    dict(publication_info)
                    if isinstance(publication_info, Mapping)
                    else None
                ),
                "result_id": item.get("result_id"),
                "cited_by": (
                    dict(cited_by)
                    if isinstance(cited_by, Mapping)
                    else None
                ),
            }
        )
    return normalized


def normalize_google_results(
    payload: Mapping[str, Any],
    *,
    max_results: int | None = None,
    snippet_limit: int = 800,
) -> list[dict[str, Any]]:
    """Keep web discovery fields and label snippets as leads."""

    results = payload.get("organic_results")
    if not isinstance(results, list):
        return []

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in results:
        if not isinstance(item, Mapping):
            continue
        dedupe_key = _result_dedupe_key(item)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append(
            {
                "engine": "google",
                "title": str(item.get("title") or "未命名网页"),
                "link": str(item.get("link") or ""),
                "snippet": str(item.get("snippet") or "")[:snippet_limit],
                "source": str(item.get("source") or ""),
                "position": item.get("position"),
                "evidence_scope": "search_snippet_lead",
            }
        )
        if max_results is not None and len(normalized) >= max_results:
            break
    return normalized


def normalize_patent_results(
    payload: Mapping[str, Any],
    *,
    max_results: int | None = None,
    snippet_limit: int = 800,
) -> list[dict[str, Any]]:
    """Keep patent identifiers needed for the separate full-text reader."""

    results = payload.get("organic_results")
    if not isinstance(results, list):
        return []
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in results:
        if not isinstance(item, Mapping):
            continue
        dedupe_key = _result_dedupe_key(item)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append(
            {
                "engine": "google_patents",
                "title": str(item.get("title") or "未命名专利"),
                "link": str(item.get("link") or ""),
                "snippet": str(item.get("snippet") or "")[:snippet_limit],
                "publication_number": item.get("publication_number"),
                "priority_date": item.get("priority_date"),
                "filing_date": item.get("filing_date"),
                "grant_date": item.get("grant_date"),
                "inventor": item.get("inventor"),
                "assignee": item.get("assignee"),
                "evidence_scope": "patent_search_lead",
            }
        )
        if max_results is not None and len(normalized) >= max_results:
            break
    return normalized


def _result_dedupe_key(item: Mapping[str, Any]) -> str:
    link = str(item.get("link") or "").strip()
    if link:
        parts = urlsplit(link)
        return "url:" + urlunsplit(
            (parts.scheme.casefold(), parts.netloc.casefold(), parts.path.rstrip("/"), parts.query, "")
        )
    return "title:" + str(item.get("title") or "").strip().casefold()
