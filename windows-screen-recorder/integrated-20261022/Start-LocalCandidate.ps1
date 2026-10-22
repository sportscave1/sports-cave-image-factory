$ErrorActionPreference = 'Stop'
$python = Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) '.venv\Scripts\python.exe'
$logs = Join-Path $env:LOCALAPPDATA 'SportsCaveOS\TaskRecorderPhase1-20261022'
New-Item -ItemType Directory -Force -Path $logs | Out-Null
Start-Process -FilePath $python -ArgumentList @('-B', ('"' + (Join-Path $PSScriptRoot 'run_local.py') + '"')) -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs 'launch.out.log') -RedirectStandardError (Join-Path $logs 'launch.err.log')
