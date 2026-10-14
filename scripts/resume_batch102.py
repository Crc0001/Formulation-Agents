# -*- coding: utf-8 -*-
"""Batch 102 auto-resume supervisor.

Queue control only: never touches scientific gates or model budgets.
When the queue is stopped (enabled=False) and resumable work remains, requeue the
stuck items via the retry endpoint. Progress resets the failure streak; three
consecutive attempts without progress are held for engineering diagnosis.

Run status is read directly from origin.sqlite3 (there is no GET /api/origin/runs/{id}).
Rewritten in Python on 2026-10-13 because Windows PowerShell 5.1 does not interpret
\\uXXXX escapes, so the previous PowerShell version compared status literals that could
never match and silently did nothing.
"""
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\Administrator\Desktop\Formulation-Agents")
FOLDER = ROOT / "reference" / "batch-102-resume-20261013"
BATCH = 102
# 每项自动重排上限；默认 3（保持既有行为）。要放开时设置环境变量
# BATCH102_MAX_REQUEUES=<n> 再重启本监督器即可，不需要改代码。
try:
    MAX_PER_ITEM = max(0, int(os.environ.get("BATCH102_MAX_REQUEUES", "3")))
except ValueError:
    MAX_PER_ITEM = 3
# 命中 429 后需要"安静"多久才恢复补排（分钟，默认 30）。判定方式=该窗口内不得有任何 429，
# 而不是"最后一次 429 之后 N 分钟"：2026-10-13 实测后者会变成每 15 分钟试 1 项、
# 每项都立刻 429，把重排次数与配额一起烧掉。
try:
    RATE_LIMIT_COOLDOWN_MIN = float(os.environ.get("BATCH102_RATE_LIMIT_COOLDOWN_MIN", "30"))
except ValueError:
    RATE_LIMIT_COOLDOWN_MIN = 30.0
API = "http://127.0.0.1:2806"
POLL_SECONDS = 60

S_QUEUED = "排队"
S_RUNNING = "研究中"
S_BLOCKED = "中断待核"
S_DONE = "三阶段已交付，待逐项验收"
LIVE_RUN = ("running", "queued")


def log(message):
    FOLDER.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {message}"
    with (FOLDER / "resume.log").open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def run_statuses():
    """id -> status for every run in origin.sqlite3 (read-only)."""
    uri = "file:" + str(ROOT / "data" / "origin.sqlite3").replace("\\", "/") + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        return {row[0]: row[1] for row in con.execute("select id, status from runs")}
    finally:
        con.close()


def post(path):
    request = urllib.request.Request(API + path, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def rate_limited_run_ids(minutes=180):
    """Run ids whose model calls hit 429 recently (infrastructure failure, not research failure)."""
    uri = "file:" + str(ROOT / "data" / "origin.sqlite3").replace("\\", "/") + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        return {
            row[0] for row in con.execute(
                "select distinct run_id from events where kind='model_error' "
                "and payload like '%RateLimit%' and julianday(created_at) > julianday('now', ?)",
                (f"-{int(minutes)} minutes",),
            )
        }
    finally:
        con.close()


def load_refunds():
    path = FOLDER / "resume-refunds.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_refunds(refunds):
    (FOLDER / "resume-refunds.json").write_text(
        json.dumps(refunds, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def refund_rate_limit_failures(attempts, refunds, state, limited_runs):
    """Give back a requeue credit when the previous attempt died from 429, not from research.

    Idempotent: keyed by the offending run id, so one refund per rate-limited run.
    """
    changed = False
    for item in state.get("items", []):
        entry = item["rows"][0]["entry_number"]
        phases = item.get("phases") or []
        run_id = phases[-1]["run_id"] if phases else None
        if not run_id or run_id not in limited_runs:
            continue
        if refunds.get(entry) == run_id:
            continue
        if int(attempts.get(entry, 0)) > 0:
            attempts[entry] = int(attempts[entry]) - 1
            log(f"  refund {entry}: previous run {run_id[:8]} died on 429 (not a research retry)")
        refunds[entry] = run_id
        changed = True
    return changed


def load_attempts():
    """Requeue counter per directory entry; missing/corrupt file -> empty map."""
    path = FOLDER / "resume-attempts.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): int(v) for k, v in data.items() if isinstance(v, (int, float))}


def rate_limit_state(minutes=5):
    """Return (count, latest_timestamp) for 429 signals within the last `minutes`.

    必须用 julianday 比较：created_at 是 ISO（`2026-10-13T05:27:47+00:00`），而
    `datetime('now','-5 minutes')` 返回空格分隔格式；按字符串比较时 'T'(0x54) > ' '(0x20)，
    同一天的**全部**事件都会判定为"在窗口内"，导致冷却永不解除（2026-10-13 实测：
    错误写法 32 条、正确写法 0 条，监督器因此空转 2 小时）。
    """
    uri = "file:" + str(ROOT / "data" / "origin.sqlite3").replace("\\", "/") + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        row = con.execute(
            "select count(*), max(created_at) from events "
            "where kind='model_error' and payload like '%RateLimit%' "
            "and julianday(created_at) > julianday('now', ?)",
            (f"-{int(minutes)} minutes",),
        ).fetchone()
        return (row[0] or 0), row[1]
    finally:
        con.close()


def save_attempts(attempts):
    (FOLDER / "resume-attempts.json").write_text(
        json.dumps(attempts, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def classify(state, statuses):
    """Return (pending_entries, already_queued, retry_targets) for the current queue state.

    already_queued = items that still carry a retry_request. Those are ALREADY scheduled:
    the tick will dispatch them as soon as the queue is enabled again, so the supervisor
    must not requeue them (doing so burned 102-8 to its cap on 2026-10-13 13:16/13:17).
    """
    pending, already_queued, retry = [], [], []
    for item in state.get("items", []):
        entry = item["rows"][0]["entry_number"]
        phases = item.get("phases") or []
        last_run = phases[-1]["run_id"] if phases else None
        run_status = statuses.get(last_run)
        status = item.get("status")
        if item.get("retry_request"):
            already_queued.append(entry)
            continue
        if status == S_RUNNING and run_status in LIVE_RUN:
            pending.append(entry)
            continue
        if status == S_QUEUED:
            pending.append(entry)
            continue
        stuck_mid_run = status == S_RUNNING and run_status not in LIVE_RUN
        if status == S_BLOCKED or stuck_mid_run:
            retry.append(
                {
                    "entry": entry,
                    "project": item.get("project_id"),
                    "run": last_run,
                    "run_status": run_status,
                    "item_status": status,
                }
            )
    return pending, already_queued, retry


def run_payload(run_id):
    if not run_id:return {}
    con=sqlite3.connect((ROOT/'data/origin.sqlite3').resolve().as_uri()+'?mode=ro',uri=True)
    try:
        row=con.execute('select payload from runs where id=?',(run_id,)).fetchone()
        return json.loads(row[0]) if row else {}
    finally:con.close()


def progressed(before, after):
    """Count durable work, not a changed summary or repeated old evidence."""
    old, new = before.get('report') or {}, after.get('report') or {}
    if set(new.get('origin_extraction_done',[]))-set(old.get('origin_extraction_done',[])):return True
    old_rows=(old.get('decision_comparison') or {}).get('rows') or []
    new_rows=(new.get('decision_comparison') or {}).get('rows') or []
    return len(new_rows)>len(old_rows)


def save_control(control):
    path=ROOT/'data/origin-batch-supervision'/f'{BATCH}.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(control,ensure_ascii=False,indent=2),encoding='utf-8')
    temp.replace(path)


def main():
    log('progress-based supervisor started; archived-source continuation; max consecutive no-progress=3')
    path=ROOT/'data/origin-batch-supervision'/f'{BATCH}.json'
    try:control=json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):control={'items':{}}
    while True:
        try:
            # Pause is respected while work is queued: only an exhausted dispatch pass
            # is resumed. Cancelled runs are never silently restarted here.
            state=json.loads((ROOT/'data/origin-batch-jobs'/f'{BATCH}.json').read_text(encoding='utf-8'))
            if state.get('enabled'):
                time.sleep(POLL_SECONDS);continue
            if state.get('status','').startswith('已停止后续派单'):
                time.sleep(POLL_SECONDS);continue
            pending, already_queued, targets=classify(state,run_statuses())
            if rate_limit_state(RATE_LIMIT_COOLDOWN_MIN)[0]:
                log('rate limit cooldown; no dispatch')
                time.sleep(POLL_SECONDS);continue
            scheduled=0
            for target in targets:
                pid=target.get('project')
                if not pid:continue
                run=run_payload(target['run'])
                if run.get('status')=='cancelled':continue
                entry=control['items'].setdefault(pid,{'no_progress':0})
                if entry.get('run_id')!=run.get('id'):
                    before=run_payload(entry.get('baseline_run'))
                    if before:
                        entry['no_progress']=0 if progressed(before,run) else entry.get('no_progress',0)+1
                    entry.update(run_id=run.get('id'),status='awaiting_resume')
                if entry.get('no_progress',0)>=3:
                    entry['status']='no_progress';continue
                # Save baseline before request; the endpoint keeps the old run immutable.
                entry['baseline_run']=run.get('id')
                save_control(control)
                query=urllib.parse.urlencode({'project_id':pid,'model_profile':'glm','summary_only':'true'})
                post(f'/api/origin-registry/batches/{BATCH}/research/retry?{query}')
                scheduled+=1
                entry['status']='queued'
                log(f"resume {target['entry']} from checkpoint, consecutive_no_progress={entry['no_progress']}")
                save_control(control)
                if rate_limit_state(1)[0]:
                    log('fresh rate limit; stop adding retries; server circuit breaker remains active')
                    break
            save_control(control)
            # Never reactivate a queue whose only remaining work is held for diagnosis.
            if not scheduled and (pending or already_queued):
                post(f'/api/origin-registry/batches/{BATCH}/research?model_profile=glm')
            elif not scheduled and targets:
                log('remaining work has no progress or is cancelled; no empty queue activation')
        except Exception as ex:
            log(f'supervisor error: {type(ex).__name__}')
        time.sleep(POLL_SECONDS)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
