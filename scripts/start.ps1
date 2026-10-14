param([int]$Port=2806,[switch]$NoBrowser)
$ErrorActionPreference='Stop'
$taskRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $taskRoot
$taskRuntime=Get-Content (Join-Path $taskRoot 'runtime.json') -Raw | ConvertFrom-Json
$taskRuntime.python=Join-Path $taskRoot $taskRuntime.python
$env:PYTHONPATH=Join-Path $taskRoot 'apps/api/src'
$env:PYTHONUTF8='1';$env:PYTHONIOENCODING='utf-8';$env:PATH=(Join-Path $taskRoot 'tools')+';'+$env:PATH
$taskListener=Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if($taskListener){
 $taskHealth=Invoke-RestMethod "http://127.0.0.1:$Port/api/health"
 $taskInstance=& $taskRuntime.python -c "import hashlib;from pathlib import Path;print(hashlib.sha256(str(Path.cwd()).encode()).hexdigest()[:12])"
 if($taskHealth.instance -ne $taskInstance){throw '端口由其他目录占用'}
}else{
 $taskProc=Start-Process -FilePath $taskRuntime.python -ArgumentList @('-m','uvicorn','virtual_reactor_api.dual_main:app','--host','127.0.0.1','--port',"$Port") -WorkingDirectory $taskRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $taskRoot 'logs/server.log') -RedirectStandardError (Join-Path $taskRoot 'logs/server-error.log')
 $taskProc.Id | Set-Content (Join-Path $taskRoot 'logs/server.pid')
 for($i=0;$i -lt 30;$i++){try{$null=Invoke-RestMethod "http://127.0.0.1:$Port/api/health";break}catch{Start-Sleep -Seconds 1}}
 $null=Invoke-RestMethod "http://127.0.0.1:$Port/api/health"
}
Write-Output "新双智能体程序：http://127.0.0.1:$Port"
if(-not $NoBrowser){Start-Process "http://127.0.0.1:$Port"}
