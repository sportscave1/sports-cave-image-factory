[CmdletBinding()]
param([switch]$Setup, [switch]$StopRunner, [switch]$Diagnostics, [switch]$Pair)
$ErrorActionPreference = 'Stop'
$recorderInstall = Join-Path $env:LOCALAPPDATA 'SportsCaveOS\TaskRecorderHelper'
if ($Setup -or -not (Test-Path -LiteralPath (Join-Path $recorderInstall 'Start.vbs'))) {
    & (Join-Path $PSScriptRoot 'Install-TaskRecorder.ps1')
    return
}
if ($StopRunner) { & (Join-Path $recorderInstall 'Stop.cmd') }
elseif ($Diagnostics) { & (Join-Path $recorderInstall 'Diagnostics.cmd') }
elseif ($Pair) { & (Join-Path $recorderInstall 'Connect PC.cmd') }
else { Start-Process -FilePath 'wscript.exe' -ArgumentList ('"' + (Join-Path $recorderInstall 'Start.vbs') + '"') -WindowStyle Hidden }
