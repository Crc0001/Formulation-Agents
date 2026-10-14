# -*- coding: utf-8 -*-
"""Batch 102 low-frequency health monitor.

Every 30 minutes check that automation is still alive and make progress; append ONE line
to monitor.log and stay silent otherwise. It deliberately does NOT report normal progress:
the user only wants to know about bugs that halt the run.

Checks per cycle:
  - server /api/health reachable and reports ok
  - supervisor process (resume_batch102.py) and watcher process alive
  - watch.log fresher than 3 minutes
  - no active run stuck (no new event for > 12 minutes while still 'running')
  - last 30 min of events contain no fatal error types
It only reads. It never requeues, restarts or edits anything.
"""
import json
import os
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(r"C:\Users\Administrator\Desktop\Formulation-Agents")
FOLDER = ROOT / "reference" / "batch-102-resume-20261013"
DB = ROOT / "data" / "origin.sqlite3"
INTERVAL_MIN = 30
WATCH_STALE_MIN = 3
RUN_STALL_MIN = 12
FATAL_KINDS = ("runtime_error", "provider_failure", "publication_limit")


def now():
    return datetime.now()


def log(message):
    FOLDER.mkdir(parents=True, exist_ok=True)
    with (FOLDER / "monitor.log").open("a", encoding="utf-8") as handle:
        handle.write(f"{now():%Y-%m-%d %H:%M:%S} {message}\n")


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def process_alive(fragment):
    """Return pid for any process whose command line contains `fragment` (python or powershell)."""
    try:
        import subprocess

        # 不限定 Name='python.exe'：采样器是 powershell.exe，限定名称会误报"缺失"。
        # GBK 是 Windows 默认解码，会让含非 GBK 字节的进程命令行直接抛 UnicodeDecodeError。
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process | "
             "Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90,
        ).stdout.strip()
        data = json.loads(out) if out else []
        if isinstance(data, dict):
            data = [data]
        for item in data:
            if fragment.lower() in (item.get("CommandLine") or "").lower():
                return item.get("ProcessId")
    except Exception:
        return None
    return None


def health():
    try:
        with urllib.request.urlopen("http://127.0.0.1:2806/api/health", timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as ex:
        return {"status": f"unreachable:{type(ex).__name__}"}


def db_snapshot():
    uri = "file:" + str(DB).replace("\\", "/") + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        active = list(con.execute("select id,status from runs where status in ('running','queued')"))
        stalled = []
        for rid, status in active:
            row = con.execute("select max(created_at) from events where run_id=?", (rid,)).fetchone()
            last = row[0] if row else None
            if last:
                age = datetime.now(timezone.utc) - datetime.fromisoformat(last.replace("Z", "+00:00"))
                if age > timedelta(minutes=RUN_STALL_MIN):
                    stalled.append((rid[:8], int(age.total_seconds() // 60)))
            else:
                stalled.append((rid[:8], -1))
        cut = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        # 只把"最近 10 分钟"的 fatal 当作故障：更早的失败已由后续运行取代，
        # 每轮重复报警会淹没真正的异常（2026-10-13 13:25 的三次 429 即属此类）。
        fatal = list(con.execute(
            "select run_id, kind from events where kind in ({}) and created_at > ?".format(
                ",".join("?" * len(FATAL_KINDS))), (*FATAL_KINDS, cut)))
        # 只在没有在途运行、且队列也没在派单时才算"真的停摆"。
        return {"active": active, "stalled": stalled, "fatal": fatal}
    finally:
        con.close()


def supervisor_in_cooldown(window_min=8):
    """True when resume.log shows a recent rate-limit cooldown (by design, not a fault)."""
    path = FOLDER / "resume.log"
    if not path.exists():
        return False
    cutoff = now() - timedelta(minutes=window_min)
    try:
        for line in reversed(path.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]):
            if "RATE LIMIT cooldown" not in line:
                continue
            try:
                stamp = datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            return stamp >= cutoff
    except Exception:
        return False
    return False


def check():
    problems = []
    notes = []
    h = health()
    if h.get("status") != "ok":
        problems.append(f"health={h.get('status')}")
    if not process_alive("resume_batch102.py"):
        problems.append("supervisor missing")
    if not process_alive("watch-batch102.ps1"):
        problems.append("watcher missing")
    watch = FOLDER / "watch.log"
    if not watch.exists():
        problems.append("watch.log missing")
    else:
        age_min = (now() - datetime.fromtimestamp(watch.stat().st_mtime)).total_seconds() / 60
        if age_min > WATCH_STALE_MIN:
            problems.append(f"watch.log stale {age_min:.1f}min")
    snap = db_snapshot()
    for rid, minutes in snap["stalled"]:
        problems.append(f"run {rid} stalled {minutes}min")
    state = read_json(ROOT / "data" / "origin-batch-jobs" / "102.json") or {}
    items = state.get("items") or []
    counts = {}
    for item in items:
        counts[item.get("status")] = counts.get(item.get("status"), 0) + 1
    # 429 是外部配额，不是程序 bug：单独统计，避免把限流误报成故障。
    rate_limited, _ = rate_limit_count()
    cooldown = supervisor_in_cooldown()
    if rate_limited:
        notes.append(f"rate-limit-cooldown(429_last30min={rate_limited})")
    # fatal / 停摆只有在"监督器也没在冷却"时才算故障；冷却期队列停派是**正确刹车**。
    if snap["fatal"] and not snap["active"] and not state.get("enabled") and not cooldown:
        kinds = sorted({kind for _, kind in snap["fatal"]})
        problems.append(f"undispatched fatal ({','.join(kinds)}) with queue disabled")
    if not snap["active"] and not state.get("enabled") and not cooldown and (state.get("items") or []):
        blocked = counts.get("中断待核", 0)
        queued = counts.get("排队", 0)
        resumable = 0
        try:
            attempts = json.loads((FOLDER / "resume-attempts.json").read_text(encoding="utf-8"))
        except Exception:
            attempts = {}
        for item in state.get("items") or []:
            if item.get("status") == "中断待核" and int(attempts.get(item["rows"][0]["entry_number"], 0)) < int(
                os.environ.get("BATCH102_MAX_REQUEUES", "3")
            ):
                resumable += 1
        if blocked and not queued and resumable:
            problems.append(f"idle with {blocked} blocked ({resumable} resumable) and 0 queued (needs requeue)")
    # 无进展检测：交付数在 90 分钟内没有增加，而仍有未交付项 —— 这正是 2026-10-13
    # 13:03–15:45 空转两小时却每轮报 OK 的那类故障，必须在冷却注解之外单独报警。
    delivered = counts.get("三阶段已交付，待逐项验收", 0)
    out_state_path = FOLDER / "monitor-state.json"
    try:
        out_state = json.loads(out_state_path.read_text(encoding="utf-8"))
    except Exception:
        out_state = {}
    if out_state.get("delivered") != delivered:
        out_state = {"delivered": delivered, "since": now().isoformat(timespec="seconds")}
        out_state_path.write_text(json.dumps(out_state, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        try:
            since = datetime.fromisoformat(out_state.get("since") or now().isoformat(timespec="seconds"))
        except ValueError:
            since = now()
        stalled_min = (now() - since).total_seconds() / 60
        remaining_items = len(state.get("items") or []) - delivered
        if stalled_min >= 90 and remaining_items > 0:
            problems.append(f"no delivery progress for {stalled_min:.0f}min with {remaining_items} item(s) pending")
    return problems, counts, snap["active"], rate_limited, notes


def rate_limit_count():
    uri = "file:" + str(DB).replace("\\", "/") + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        row = con.execute(
            "select count(*), max(created_at) from events where kind='model_error' "
            "and payload like '%RateLimit%' and julianday(created_at) > julianday('now','-30 minutes')"
        ).fetchone()
        return (row[0] or 0), row[1]
    finally:
        con.close()


def main():
    once = "--once" in sys.argv
    log(f"monitor started (30min interval, silent unless abnormal{', once' if once else ''})")
    while True:
        try:
            problems, counts, active, rate_limited, notes = check()
            state = read_json(ROOT / "data" / "origin-batch-jobs" / "102.json") or {}
            summary = (
                "enabled={} counts={} active={} 429_last30min={}".format(
                    state.get("enabled"),
                    ",".join(f"{k}:{v}" for k, v in sorted(counts.items())),
                    len(active),
                    rate_limited,
                )
            )
            if notes:
                summary += " note=" + ";".join(notes)
            if problems:
                log("ALERT " + summary + " | " + "; ".join(problems))
            else:
                log("OK " + summary)
            if once:
                print(("ALERT " if problems else "OK ") + summary + (" | " + "; ".join(problems) if problems else ""))
                return
        except Exception as ex:
            log(f"monitor error: {type(ex).__name__}: {ex}")
            if once:
                return
        time.sleep(INTERVAL_MIN * 60)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()

