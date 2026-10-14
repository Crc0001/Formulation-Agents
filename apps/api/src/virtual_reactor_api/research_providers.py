"""Provider-neutral research result adapters.

The SciSpace connector is intentionally kept out of the simulation layer. This
module accepts exported/search-result JSON and converts it to the evidence shape
used by the generator, so a future official API adapter can replace the import
without changing configuration or simulation contracts.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def normalize_scispace_results(payload: Mapping[str, Any] | Sequence[Any]) -> list[dict[str, Any]]:
    """Normalize SciSpace-like paper results without inventing citations."""
    raw = payload.get("results", payload.get("papers", [])) if isinstance(payload, Mapping) else payload
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        title = str(item.get("title") or "未命名文献").strip()
        url = str(item.get("url") or item.get("link") or "").strip()
        doi = str(item.get("doi") or "").strip()
        key = (doi or url or title).casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        output.append({
            "provider": "scispace",
            "title": title,
            "url": url,
            "doi": doi,
            "authors": item.get("authors") or [],
            "year": item.get("year"),
            "journal": item.get("journal") or item.get("venue") or "",
            "abstract": str(item.get("abstract") or item.get("snippet") or ""),
            "citationCount": item.get("citationCount", item.get("citation_count")),
        })
    return output


def scispace_result_to_evidence(result: Mapping[str, Any], *, source_id: str,
                                supported_paths: Sequence[str],
                                locator: str = "SciSpace paper metadata") -> dict[str, Any]:
    """Create an EvidenceItem-compatible mapping for results with a URL."""
    url = str(result.get("url") or "").strip()
    if not url:
        raise ValueError("SciSpace result lacks a URL and cannot become traceable evidence")
    excerpt = str(result.get("abstract") or "").strip()
    if not excerpt:
        raise ValueError("SciSpace result lacks an abstract/excerpt")
    if not supported_paths:
        raise ValueError("supported_paths is required for traceable evidence")
    return {
        "sourceId": source_id,
        "title": str(result.get("title") or "未命名文献"),
        "url": url,
        "locator": locator,
        "excerpt": excerpt,
        "evidenceLevel": "primary" if result.get("doi") else "unknown",
        "supportedPaths": list(supported_paths),
    }
