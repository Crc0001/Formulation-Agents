# -*- coding: utf-8 -*-
"""Batch 102 per-item delivery scoreboard (read-only).

Writes reference/batch-102-resume-20261013/scoreboard.md and prints a summary.
Shows every queue item with its phases, run statuses, saved report volume and the
remaining delivery gaps, so per-item state and gaps can be reported verbatim.
"""
import json
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(r"C:\Users\Administrator\Desktop\Formulation-Agents")
FOLDER = ROOT / "reference" / "batch-102-resume-20261013"
DB = ROOT / "data" / "origin.sqlite3"


def local(stamp):
    if not stamp:
        return "-"
    return (datetime.fromisoformat(stamp.replace("Z", "+00:00")) + timedelta(hours=8)).strftime("%m-%d %H:%M")


def segments(issues):
    total = 0
    for issue in issues or []:
        match = re.search(r"(\d+)\u6bb5\u5c1a\u672a\u5b8c\u6210", str(issue))
        if match:
            total = max(total, int(match.group(1)))
    return total


def compact(state, runs):
    """One screen of queue + per-item one-liners, for quick read-only checks."""
    counts = {}
    for item in state.get("items", []):
        counts[item.get("status")] = counts.get(item.get("status"), 0) + 1
    print(
        f"queue enabled={state.get('enabled')} status={state.get('status')} "
        f"streak={state.get('external_failure_streak')}"
    )
    print("counts: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])))
    for item in state.get("items", []):
        phases = item.get("phases") or []
        last = phases[-1] if phases else {}
        rid = (last.get("run_id") or "")[:8]
        info = runs.get(last.get("run_id") or "", {})
        report = info.get("report") or {}
        sequence = "".join(str(p.get("phase")) for p in phases) or "-"
        note = (info.get("error") or "").split("；")[0][:60]
        print(
            f"{item['rows'][0]['entry_number']:>7} {item.get('status'):>12} ph={sequence:<3} run={rid:<8} "
            f"{info.get('status','-'):>10} f={len(report.get('formulations') or []):>3} p={len(report.get('processes') or []):>3} {note}"
        )


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
    if "--compact" in sys.argv:
        compact(state, runs)
        return
    events = {}
    for rid, kind, created in con.execute("select run_id, kind, created_at from events"):
        events.setdefault(rid, []).append((kind, created))

    lines = [
        "# 102 批次逐项交付记分板",
        "",
        f"生成：{datetime.now():%Y-%m-%d %H:%M}（只读）",
        "",
        f"- 队列：enabled={state.get('enabled')} · status={state.get('status')} · streak={state.get('external_failure_streak')}",
        "- 阶段序列=该品种已运行的阶段号；待跑阶段=retry_request.phase（无则按已跑阶段+1）；报告中处方/工艺取**末次运行**的已存成果",
        "",
        "| 目录号 | 品种 | 队列状态 | 阶段序列 | 待跑阶段 | 末次运行 | 运行状态 | 处方 | 工艺 | 待续段 | 交付缺口/错误 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    counts = {}
    for item in state.get("items", []):
        entry = item["rows"][0]["entry_number"]
        name = item["name"]
        counts[item.get("status")] = counts.get(item.get("status"), 0) + 1
        phases = item.get("phases") or []
        last = phases[-1] if phases else {}
        rid = last.get("run_id") or ""
        info = runs.get(rid, {})
        report = info.get("report") or {}
        issues = last.get("delivery_issues") or []
        note = (info.get("error") or "").split("；")[0][:80]
        if not note and issues:
            note = str(issues[0])[:80]
        retry = item.get("retry_request") or {}
        sequence = "".join(str(p.get("phase")) for p in phases) or "-"
        # 阶段只有 1/2/3；末阶段为 3 时没有"待跑阶段"，不能显示 4。
        last_phase = (phases[-1].get("phase") if phases else 0) or 0
        next_phase = retry.get("phase")
        if next_phase is None and item.get("status") not in (None, "三阶段已交付，待逐项验收"):
            next_phase = last_phase + 1 if last_phase < 3 else "-"
        lines.append(
            f"| {entry} | {name[:18]} | {item.get('status')} | {sequence} | {next_phase} | {rid[:8]} | "
            f"{info.get('status', '-')} | {len(report.get('formulations') or [])} | {len(report.get('processes') or [])} | "
            f"{segments(issues) or '-'} | {note or '-'} |"
        )
    lines += ["", "## 队列状态统计", ""]
    for status, number in sorted(counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"- {status}: {number}")
    lines += ["", "## 运行规模统计", ""]
    for rid, info in sorted(runs.items(), key=lambda kv: -len(events.get(kv[0], [])))[:8]:
        if rid in {p.get("run_id") for i in state.get("items", []) for p in (i.get("phases") or [])}:
            evs = events.get(rid, [])
            lines.append(f"- {rid[:8]} {info['status']} 事件={len(evs)} 起={local(evs[0][1]) if evs else '-'} 末={local(evs[-1][1]) if evs else '-'}")
    (FOLDER / "scoreboard.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:8]))
    print()
    print("status counts:", counts)
    print("written:", FOLDER / "scoreboard.md")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
