# -*- coding: utf-8 -*-
"""Batch 102 per-item unfinished-segment tracker (read-only).

For every queue item that is not delivered, list the report's remaining gaps and the
source segments still pending extraction (`.. 段尚未完成；来源ID：...`). This is the
machine-checkable form of the batch's leftover work, and it distinguishes
"model budget/segment threshold" gaps from scientific gaps.
"""
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\Administrator\Desktop\Formulation-Agents")
FOLDER = ROOT / "reference" / "batch-102-resume-20261013"
DB = ROOT / "data" / "origin.sqlite3"
SEGMENT_RE = re.compile(r"(\d+)\u6bb5\u5c1a\u672a\u5b8c\u6210")
SOURCE_RE = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")


def analyse(item, runs):
    phases = item.get("phases") or []
    last = phases[-1] if phases else {}
    rid = last.get("run_id") or ""
    info = runs.get(rid, {})
    report = info.get("report") or {}
    issues = list(last.get("delivery_issues") or [])
    text = " ".join(str(x) for x in issues) + " " + str(info.get("error") or "")
    pending_segments = 0
    for issue in issues + [info.get("error") or ""]:
        match = SEGMENT_RE.search(str(issue))
        if match:
            pending_segments = max(pending_segments, int(match.group(1)))
    pending_sources = sorted({m for m in SOURCE_RE.findall(text)})
    return {
        "entry": item["rows"][0]["entry_number"],
        "name": item["name"],
        "status": item.get("status"),
        "phases": [p.get("phase") for p in phases],
        "run": rid,
        "run_status": info.get("status", "-"),
        "formulations": len(report.get("formulations") or []),
        "processes": len(report.get("processes") or []),
        "gaps": len(report.get("gaps") or []),
        "pending_segments": pending_segments,
        "pending_sources": pending_sources,
        "issues": issues,
        "error": info.get("error") or "",
        "retry_request": item.get("retry_request"),
    }


def main():
    uri = "file:" + str(DB).replace("\\", "/") + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    runs = {}
    for rid, status, payload in con.execute("select id, status, payload from runs"):
        try:
            body = json.loads(payload) if payload else {}
        except Exception:
            body = {}
        runs[rid] = {"status": status, "error": body.get("error") or "", "report": body.get("report") or {}}
    state = json.loads((ROOT / "data" / "origin-batch-jobs" / "102.json").read_text(encoding="utf-8"))

    lines = [
        "# 102 批次待续段清单（只读）",
        "",
        f"生成：{datetime.now():%Y-%m-%d %H:%M}",
        "",
        "> \"待续段\"=来源原文尚未整理的段数（属运行预算/分段上限造成，不是科学结论缺口）；",
        "> \"科学缺口\"=报告 gaps 条数（信息未公开或未取得原文）。两者必须分开看。",
        "> 注意：仍标「排队」的品种其末次运行是**历史**运行，待续段与科学缺口列反映历史状态，本轮重跑后会更新；",
        "> 「研究中」的品种尚未落定，两个缺口列在收尾前不代表最终值。",
        "",
        "| 目录号 | 品种 | 队列状态 | 阶段 | 运行 | 运行状态 | 处方 | 工艺 | 待续段 | 待续来源数 | 科学缺口 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    total_segments = 0
    for item in state.get("items", []):
        info = analyse(item, runs)
        if info["status"] == "三阶段已交付，待逐项验收":
            continue
        total_segments += info["pending_segments"]
        lines.append(
            f"| {info['entry']} | {info['name'][:18]} | {info['status']} | {''.join(str(p) for p in info['phases']) or '-'} | "
            f"{info['run'][:8]} | {info['run_status']} | {info['formulations']} | {info['processes']} | "
            f"{info['pending_segments'] or '-'} | {len(info['pending_sources']) or '-'} | {info['gaps']} |"
        )
    lines += ["", f"未交付项待续段合计：**{total_segments} 段**", "", "## 逐项缺口原文", ""]
    for item in state.get("items", []):
        info = analyse(item, runs)
        if info["status"] == "三阶段已交付，待逐项验收":
            continue
        lines.append(f"### {info['entry']} {info['name']}")
        lines.append("")
        lines.append(f"- 运行 `{info['run'][:8]}`（{info['run_status']}），已存处方 {info['formulations']} / 工艺 {info['processes']} / 科学缺口 {info['gaps']}")
        if info["pending_segments"]:
            lines.append(f"- 待续 {info['pending_segments']} 段，来源（{len(info['pending_sources'])} 个）：{', '.join(info['pending_sources']) or '-'}")
        for issue in info["issues"][:6]:
            lines.append(f"- 交付检查：{str(issue)[:200]}")
        if info["error"]:
            lines.append(f"- 运行 error：{info['error'][:200]}")
        lines.append("")
    out = FOLDER / "pending-segments.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"undelivered items: {sum(1 for i in state.get('items', []) if i.get('status') != '三阶段已交付，待逐项验收')}")
    print(f"pending segments total: {total_segments}")
    print("written:", out)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
