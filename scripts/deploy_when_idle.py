# -*- coding: utf-8 -*-
"""Deploy queued code patches during a safe window (no active runs).

Restarting 2806 kills in-flight runs and marks them interrupted, so this waits for a
moment when origin.sqlite3 has no running/queued run before restarting.
"""
import json
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\Administrator\Desktop\Formulation-Agents")
FOLDER = ROOT / "reference" / "batch-102-resume-20261013"
PYTHON = ROOT / "runtime" / "python" / "python.exe"
RESTART = ROOT / "scripts" / "restart-local.ps1"
POLL_SECONDS = 20
MAX_WAIT_MINUTES = 90


def log(message):
    FOLDER.mkdir(parents=True, exist_ok=True)
    with (FOLDER / "deploy.log").open("a", encoding="utf-8") as handle:
        handle.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {message}\n")


def live_runs():
    uri = "file:" + str(ROOT / "data" / "origin.sqlite3").replace("\\", "/") + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        return [row[0] for row in con.execute("select id from runs where status in ('running','queued')")]
    finally:
        con.close()


def main():
    log("deploy watcher started")
    deadline = time.time() + MAX_WAIT_MINUTES * 60
    while time.time() < deadline:
        try:
            live = live_runs()
        except Exception as ex:
            log(f"probe error: {type(ex).__name__}: {ex}")
            time.sleep(POLL_SECONDS)
            continue
        if not live:
            log("safe window found (0 active runs) -> restarting 2806")
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(RESTART)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
            )
            log("restart output: " + " | ".join((result.stdout or "").splitlines()))
            if result.returncode != 0:
                log(f"restart exit={result.returncode} stderr={result.stderr}")
                return
            log("deployment done")
            return
        log(f"waiting: {len(live)} active run(s)")
        time.sleep(POLL_SECONDS)
    log("deploy watcher timed out without a safe window")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
