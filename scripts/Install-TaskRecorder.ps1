[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$recorderSource = if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'task_recorder')) { $PSScriptRoot } else { Split-Path -Parent $PSScriptRoot }
$recorderPython = Join-Path $recorderSource '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $recorderPython)) { $recorderPython = (Get-Command python -ErrorAction Stop).Source }
Push-Location $recorderSource
try {
    & $recorderPython -m task_recorder.install
    if ($LASTEXITCODE -ne 0) { throw 'Task Recorder setup did not complete.' }
} finally { Pop-Location }
