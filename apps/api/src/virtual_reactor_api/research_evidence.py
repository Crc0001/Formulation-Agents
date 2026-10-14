"""Evidence ranking and cross-provider merging for reaction research."""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from urllib.parse import urlparse


def classify_source(item: Mapping[str, object], query: str = "") -> str:
    url = str(item.get("url") or item.get("link") or "").casefold()
    host = urlparse(url).hostname or ""
    title = str(item.get("title") or "").casefold()
    if any(x in host for x in ("wikipedia.org", "blogspot.", "medium.com", "reddit.com")):
        return "lead_only"
    if "patent" in host or "patent" in title or re.search(r"\b[A-Z]{2,3}\d{5,}\b", title):
        return "process_primary"
    if str(item.get("doi") or "").strip():
        return "paper_candidate"
    return "unverified_lead"


def merge_research_results(items: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    merged: dict[str, dict[str, object]] = {}
    for item in items:
        doi = str(item.get("doi") or "").strip().casefold()
        title = " ".join(str(item.get("title") or "").casefold().split())
        key = doi or title
        if not key:
            continue
        row = merged.setdefault(key, {**item, "providers": []})
        providers = row["providers"]
        if isinstance(providers, list):
            provider = str(item.get("provider") or item.get("source") or "unknown")
            if provider not in providers:
                providers.append(provider)
        if not row.get("abstract") and item.get("abstract"):
            row["abstract"] = item["abstract"]
        row["evidenceClass"] = classify_source(row)
    return list(merged.values())
