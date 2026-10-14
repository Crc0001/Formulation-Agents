# Batch 102 watcher. ASCII only: Windows PowerShell 5.1 reads BOM-less UTF-8 as ANSI,
# so non-ASCII log prose can break parsing.
$root='C:\Users\Administrator\Desktop\Formulation-Agents'
$log="$root/reference/batch-102-resume-20261013/watch.log"
$python="$root/runtime/python/python.exe"
$prev=@{}
# Run metrics come straight from origin.sqlite3: the API events endpoint truncates
# (observed 36 of 92 events), and DB reads avoid embedding SQL quoting in PowerShell.
$probe=@'
import sqlite3,json,sys
con=sqlite3.connect('file:C:/Users/Administrator/Desktop/Formulation-Agents/data/origin.sqlite3?mode=ro',uri=True)
rid=sys.argv[1]
evs=list(con.execute('select kind,created_at,payload from events where run_id=? order by id',(rid,)))
first=[p for k,c,p in evs if k=='model_request']
size=len(json.loads(first[0])['messages'][0]['content']) if first else -1
errs=[(k,c,p) for k,c,p in evs if k in ('runtime_error','model_error','provider_failure','origin_delivery_incomplete')]
out={'events':len(evs),'first_request_chars':size,'last':evs[-1][0] if evs else '-','last_at':evs[-1][1][11:19] if evs else '-','errors':len(errs)}
if errs:
    k,c,p=errs[-1]
    out['last_error_kind']=k
    out['last_error']=str(json.loads(p))[:200]
print(json.dumps(out,ensure_ascii=False))
'@
while($true){
  try{
    $b=Invoke-RestMethod 'http://127.0.0.1:2806/api/origin-registry/batches/102/research' -TimeoutSec 20
    $h=Invoke-RestMethod 'http://127.0.0.1:2806/api/health' -TimeoutSec 20
    $now=Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $queued=$b.total-$b.completed-$b.blocked-$b.current.Count
    "{0} health={1} enabled={2} completed={3} blocked={4} queued={5} current={6}" -f $now,$h.status,$b.enabled,$b.completed,$b.blocked,$queued,$b.current.Count | Add-Content $log -Encoding UTF8
    foreach($c in $b.current){
      try{
        $p=Invoke-RestMethod ('http://127.0.0.1:2806/api/projects/'+$c.project_id) -TimeoutSec 20
        $r=$p.origin.runs | Where-Object { $_.status -eq 'running' -or $_.status -eq 'queued' } | Select-Object -First 1
        if($r){
          $rid=$r.id
          $raw = & $python -c $probe $rid 2>$null
          $j = ($raw | Out-String).Trim() | ConvertFrom-Json
          $delta=0
          if($prev.ContainsKey($rid)){ $delta=$j.events - $prev[$rid] }
          $prev[$rid]=$j.events
          "{0} RUN {1} phase={2} status={3} events={4} (+{5}) first_request_chars={6} last={7}@{8} errors={9}" -f $now,$rid.Substring(0,8),$c.phase,$r.status,$j.events,$delta,$j.first_request_chars,$j.last,$j.last_at,$j.errors | Add-Content $log -Encoding UTF8
          if($j.errors -gt 0){ "{0} ERR {1} kind={2} payload={3}" -f $now,$rid.Substring(0,8),$j.last_error_kind,$j.last_error | Add-Content $log -Encoding UTF8 }
        }
      }catch{ "{0} WARN probe failed for {1}: {2}" -f $now,$c.project_id,$_.Exception.Message | Add-Content $log -Encoding UTF8 }
    }
  }catch{ "{0} WARN batch probe failed: {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'),$_.Exception.Message | Add-Content $log -Encoding UTF8 }
  Start-Sleep -Seconds 60
}
