"""Small, provenance-preserving extractor for patent process examples."""
from __future__ import annotations

import re
from collections.abc import Mapping
from urllib.parse import urlparse


def extract_patent_examples(text: str, *, patent_number: str, source_url: str) -> list[dict[str, object]]:
    if not patent_number.strip():
        raise ValueError("patent_number is required")
    parsed = urlparse(source_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("source_url must be an absolute HTTP(S) URL")
    blocks = re.split(r"(?i)(?=(?:example|embodiment)\s*\d+|实施例\s*\d+)", text)
    examples: list[dict[str, object]] = []
    occurrences: dict[int, int] = {}
    for block_index, block in enumerate(blocks):
        match = re.search(r"(?i)(?:example|embodiment|实施例)\s*(\d+)", block)
        if not match:
            continue
        def find(pattern: str) -> str | None:
            found = re.search(pattern, block, re.I | re.S)
            return found.group(1).strip() if found else None
        example_number = int(match.group(1))
        occurrences[example_number] = occurrences.get(example_number, 0) + 1
        occurrence = occurrences[example_number]
        locator = f"{patent_number} · 实施例 {example_number}"
        if occurrence > 1:
            locator += f"（文档内第 {occurrence} 次出现）"
        examples.append({
            "sourceType": "patent_example",
            "patentNumber": patent_number,
            "sourceUrl": source_url,
            "exampleNumber": example_number,
            "exampleOccurrence": occurrence,
            "documentBlockIndex": block_index,
            "locator": locator,
            "temperature": find(r"(?:under|at|在)\s*([0-9]+\s*(?:to|～|-)?\s*[0-9]*\s*°?\s*C)") or find(r"([0-9]+\s*(?:to|～|-)?\s*[0-9]*\s*°\s*C)"),
            "time": find(r"(?:for|反应|during)\s*([0-9]+\s*(?:to|～|-)?\s*[0-9]*\s*(?:h|hours?|小时))") or find(r"([0-9]+\s*(?:to|～|-)?\s*[0-9]*\s*(?:h|hours?|小时))"),
            "solvent": "isopropanol" if re.search(r"isopropanol|Virahol|异丙醇", block, re.I) else None,
            "yield": find(r"(?:yield|收率)\s*(?:is|为|达到)?\s*([0-9]+(?:\.[0-9]+)?\s*%)"),
            "purity": find(r"(?:purity|纯度)\D{0,30}([0-9]+(?:\.[0-9]+)?\s*%)"),
            "rawText": block.strip()[:5000],
            "rawTextTruncated": len(block.strip()) > 5000,
        })
    return examples


def build_optimization_matrix(examples: list[Mapping[str, object]]) -> list[dict[str, object]]:
    return [
        {"factor": factor, "exampleNumber": row.get("exampleNumber"), "value": row.get(key), "sourceType": row.get("sourceType"), "patentNumber": row.get("patentNumber"), "sourceUrl": row.get("sourceUrl")}
        for row in examples
        for factor, key in (("temperature", "temperature"), ("time", "time"), ("yield", "yield"), ("purity", "purity"))
        if row.get(key) is not None
    ]
