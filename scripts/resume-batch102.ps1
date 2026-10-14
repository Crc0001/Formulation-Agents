# Batch 102 auto-resume supervisor (queue control only; never touches scientific gates).
# Rule: when queue enabled=False and resumable work remains, retry the failed items and
#       re-activate the queue. At most $maxPerItem requeues per item, then stop retrying it.
# Run status is read straight from origin.sqlite3 (there is no GET /api/origin/runs/{id}).
# Chinese status literals use \u escapes so the file stays ASCII-safe for powershell.exe.
$root = 'C:\Users\Administrator\Desktop\Formulation-Agents'
$folder = "$root/reference/batch-102-resume-20261013"
$python = "$root/runtime/python/python.exe"
$batch = 102
$maxPerItem = 3
$log = "$folder/resume.log"
$attemptsFile = "$folder/resume-attempts.json"

# queue item statuses: queued / in-research / blocked / delivered
$S_QUEUED  = "\u6392\u961f"
$S_RUNNING = "\u7814\u7a76\u4e2d"
$S_BLOCKED = "\u4e2d\u65ad\u5f85\u6838"
$S_DONE    = "\u4e09\u9636\u6bb5\u5df2\u4ea4\u4ed8\uff0c\u5f85\u9010\u9879\u9a8c\u6536"

function Log($msg) { "{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg | Add-Content $log -Encoding UTF8 }

function Get-RunStatuses {
  $out = @{}
  # PowerShell 5.1 strips inner double quotes from -c arguments; keep Python quoting single-quoted
  # and wrap the whole program in a PowerShell double-quoted string.
  $code = "import sqlite3,json;con=sqlite3.connect('file:C:/Users/Administrator/Desktop/Formulation-Agents/data/origin.sqlite3?mode=ro',uri=True);print(json.dumps({r[0]:r[1] for r in con.execute('select id,status from runs')}))"
  try {
    $raw = & $python -c $code 2>$null
    if ($LASTEXITCODE -eq 0 -and $raw) {
      ($raw | Out-String).Trim() | ConvertFrom-Json | ForEach-Object { $_.PSObject.Properties | ForEach-Object { $out[$_.Name] = $_.Value } }
    } else { Log "db probe exit=$LASTEXITCODE" }
  } catch { Log "db probe failed: $($_.Exception.Message)" }
  return $out
}

$attempts = @{}
if (Test-Path $attemptsFile) {
  try { (Get-Content $attemptsFile -Raw -Encoding UTF8 | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $attempts[$_.Name] = [int]$_.Value } } catch { }
}
function Save-Attempts {
  $o = [ordered]@{}; foreach ($k in ($attempts.Keys | Sort-Object)) { $o[$k] = $attempts[$k] }
  ($o | ConvertTo-Json) | Set-Content $attemptsFile -Encoding UTF8
}

while ($true) {
  try {
    $state = Get-Content "$root/data/origin-batch-jobs/$batch.json" -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($state.enabled) { Start-Sleep -Seconds 60; continue }

    $statuses = Get-RunStatuses
    $pending = @(); $toRetry = @()
    foreach ($it in $state.items) {
      $entry = $it.rows[0].entry_number
      if ($it.phases -and $it.phases.Count -gt 0) { $lastRun = $it.phases[-1].run_id } else { $lastRun = $null }
      $runStatus = if ($lastRun -and $statuses.ContainsKey($lastRun)) { $statuses[$lastRun] } else { $null }
      if ($it.status -eq $S_RUNNING -and $runStatus -in @('running', 'queued')) { $pending += $entry; continue }
      if ($it.status -eq $S_QUEUED) { $pending += $entry; continue }
      if ($it.status -eq $S_BLOCKED -or ($it.status -eq $S_RUNNING -and $runStatus -notin @('running', 'queued'))) {
        $toRetry += [pscustomobject]@{ entry = $entry; project = $it.project_id; run = $lastRun; runStatus = $runStatus; itemStatus = $it.status }
      }
    }
    if ($toRetry.Count -eq 0 -and $pending.Count -eq 0) { Start-Sleep -Seconds 60; continue }

    Log "queue stopped: pending=$($pending.Count) retry=$($toRetry.Count)"
    foreach ($x in $toRetry) {
      $n = 0; if ($attempts.ContainsKey($x.entry)) { $n = $attempts[$x.entry] }
      if ($n -ge $maxPerItem) { Log "  $($x.entry) reached requeue cap $maxPerItem, skipped (needs manual handling)"; continue }
      try {
        $r = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:2806/api/origin-registry/batches/$batch/research/retry?project_id=$($x.project)&model_profile=glm" -TimeoutSec 30
        $attempts[$x.entry] = $n + 1
        Log "  retry $($x.entry) attempt $($n + 1) runStatus=$($x.runStatus) enabled=$($r.enabled)"
      } catch {
        Log "  retry $($x.entry) FAILED: $($_.Exception.Message)"
      }
      Start-Sleep -Milliseconds 400
    }
    Save-Attempts
    try {
      $s = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:2806/api/origin-registry/batches/$batch/research?model_profile=glm" -TimeoutSec 30
      Log "  queue reactivated: enabled=$($s.enabled) completed=$($s.completed) blocked=$($s.blocked)"
    } catch { Log "  activate FAILED: $($_.Exception.Message)" }
  } catch {
    Log "supervisor probe error: $($_.Exception.Message)"
  }
  Start-Sleep -Seconds 60
}
