# -*- coding: utf-8 -*-
"""Keep exactly one instance of each batch-102 daemon (supervisor / monitor / watcher).

Multiple copies appeared during 2026-10-13 debugging; concurrent supervisors write the same
queue file and can interleave retries. Keeps the oldest instance per role and stops the rest.
"""
import json
import subprocess
import sys

ROLES = {
    "supervisor": "resume_batch102.py",
    "monitor": "monitor_batch102.py",
    "watcher": "watch-batch102.ps1",
}


def processes():
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process | Select-Object ProcessId,Name,CommandLine,CreationDate | ConvertTo-Json -Compress"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    ).stdout.strip()
    data = json.loads(out) if out else []
    return data if isinstance(data, list) else [data]


def main():
    rows = processes()
    self_pid = os.getpid()
    self_names = tuple(ROLES.values()) + ("dedupe_batch102_daemons.py",)
    kept, stopped = {}, []
    for role, needle in ROLES.items():
        matches = []
        for r in rows:
            cmd = (r.get("CommandLine") or "")
            if needle.lower() not in cmd.lower():
                continue
            # 跳过本脚本自身：它的命令行里含这些脚本名，否则会把自己当守护进程、
            # 并因此误杀真正的实例（2026-10-13 实测踩过）。
            if "dedupe_batch102_daemons" in cmd:
                continue
            if int(r.get("ProcessId") or 0) == self_pid:
                continue
            matches.append(r)
        matches.sort(key=lambda r: str(r.get("CreationDate") or ""))
        if not matches:
            print(f"{role}: none running")
            continue
        keep = matches[0]
        kept[role] = keep["ProcessId"]
        for extra in matches[1:]:
            subprocess.run(["taskkill", "/F", "/PID", str(extra["ProcessId"])],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
            stopped.append((role, extra["ProcessId"]))
    print("kept:", kept)
    print("stopped:", stopped)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()

