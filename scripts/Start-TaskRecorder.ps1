[CmdletBinding()]
param([switch]$Setup, [switch]$StopRunner)
$ErrorActionPreference = 'Stop'
$recorderRepo = Split-Path -Parent $PSScriptRoot
$recorderPython = Join-Path $recorderRepo '.venv\Scripts\python.exe'
Push-Location $recorderRepo
try {
    if (-not (Test-Path -LiteralPath $recorderPython)) {
        & python -m venv (Join-Path $recorderRepo '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 or newer is required.' }
        $Setup = $true
    }
    if ($Setup) {
        & $recorderPython -m pip install -r (Join-Path $recorderRepo 'task_recorder\requirements.txt')
        if ($LASTEXITCODE -ne 0) { throw 'Recorder dependency installation failed.' }
        & $recorderPython -m playwright install chromium
        if ($LASTEXITCODE -ne 0) { throw 'Chromium installation failed.' }
    }
    if ($StopRunner) {
        & $recorderPython -m task_recorder.server --shutdown
        if ($LASTEXITCODE -ne 0) { throw 'Could not stop Task Recorder.' }
    } else {
        & $recorderPython -c "import playwright"
        if ($LASTEXITCODE -ne 0) { throw 'Run scripts\Start-TaskRecorder.ps1 -Setup once.' }
        $recorderRuntime = Join-Path $env:LOCALAPPDATA 'SportsCaveOS\TaskRecorderV1'
        New-Item -ItemType Directory -Path $recorderRuntime -Force | Out-Null
        Start-Process -FilePath $recorderPython -ArgumentList @('-m','task_recorder.server','--open') -WorkingDirectory $recorderRepo -WindowStyle Hidden -RedirectStandardOutput (Join-Path $recorderRuntime 'launcher.out.log') -RedirectStandardError (Join-Path $recorderRuntime 'launcher.err.log')
        Write-Host 'Task Recorder is opening. It uses its own browser profile and does not restart the Editions companion.'
    }
} finally { Pop-Location }
