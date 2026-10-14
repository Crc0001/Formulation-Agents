"""Deterministic high-value query planning for reaction research."""
from __future__ import annotations

import re


def plan_research_queries(text: str) -> list[str]:
    """Build exact-system queries before any model-led broad search."""
    clean = " ".join(text.split())
    names = re.findall(r"[A-Za-z][A-Za-z0-9()\-+]*|[\u4e00-\u9fff]{2,}(?:酸|醛|酯|酮|胺|醇|物|体)?", clean)
    names = list(dict.fromkeys(n for n in names if len(n) >= 3))
    joined = " ".join(names[:8])
    queries: list[str] = []
    if joined:
        queries.append(f'"{joined}" reaction procedure')
        queries.append(f'"{joined}" patent example yield')
    if any(k in clean for k in ("工艺", "优化", "收率", "纯度", "杂质", "当量", "温度", "时间")):
        queries.append(f'"{joined}" process optimization yield purity temperature time')
    if "硝基苯甲醛" in clean and "乙酰乙酸" in clean:
        queries.extend([
            '"3-nitrobenzaldehyde" "isopropyl acetoacetate" Knoevenagel',
            '"3-nitrobenzaldehyde" piperidine acetic acid isopropanol',
            '"3-nitrobenzylidene" "isopropyl acetoacetate" patent',
        ])
    return list(dict.fromkeys(queries))
