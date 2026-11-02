param([Parameter(Mandatory=$true)][string]$ExtensionId)
$ErrorActionPreference='Stop'
$RecorderBootstrap=(Get-Command python -ErrorAction Stop).Source
Push-Location $PSScriptRoot
try {
 & $RecorderBootstrap -B -m task_recorder.install --extension-id $ExtensionId
 if ($LASTEXITCODE -ne 0) { throw 'Task Recorder installation failed; preserve the previous release and inspect diagnostics.' }
} finally { Pop-Location }
