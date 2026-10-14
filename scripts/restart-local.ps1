$root='C:\Users\Administrator\Desktop\Formulation-Agents'
Set-Location $root
# 记录 python 进程自身的 PID。若写成 Start-Process 返回对象的 Id（powershell 壳进程），
# 下次"停止旧服务"会停错进程，端口仍被旧代码占用（2026-10-13 实测踩过）。
$old = Get-Content "$root/logs/server.pid" -ErrorAction SilentlyContinue
$cands = @($old) + @(Get-NetTCPConnection -LocalPort 2806 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess)
foreach($cand in ($cands | Where-Object { $_ } | Select-Object -Unique)){
  if(Get-Process -Id $cand -ErrorAction SilentlyContinue){
    Stop-Process -Id $cand -Force -ErrorAction SilentlyContinue
    "stopped pid $cand"
  }
}
Start-Sleep -Seconds 2
$still = Get-NetTCPConnection -LocalPort 2806 -State Listen -ErrorAction SilentlyContinue
if($still){ "ERROR: port 2806 still held by $($still.OwningProcess)"; exit 1 }
$env:PYTHONPATH="$root/apps/api/src"
$env:PYTHONUTF8='1'; $env:PYTHONIOENCODING='utf-8'; $env:PATH="$root/tools;$env:PATH"
$p=Start-Process -FilePath "$root/runtime/python/python.exe" -ArgumentList @('-m','uvicorn','virtual_reactor_api.dual_main:app','--host','127.0.0.1','--port','2806') -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput "$root/logs/server.log" -RedirectStandardError "$root/logs/server-error.log"
Set-Content "$root/logs/server.pid" $p.Id
"started python pid $($p.Id)"
for($i=0;$i -lt 40;$i++){
  try{ $h=Invoke-RestMethod 'http://127.0.0.1:2806/api/health' -TimeoutSec 5; "health=$($h.status) instance=$($h.instance) after $($i)s"; break }catch{ Start-Sleep -Seconds 1 }
}
$owner=(Get-NetTCPConnection -LocalPort 2806 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1).OwningProcess
"port owner pid = $owner"
