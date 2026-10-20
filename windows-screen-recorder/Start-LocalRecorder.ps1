[CmdletBinding()]
param([switch]$AcceptInjectedTestInput, [string]$DataDirectory)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'native\build.ps1')
& (Join-Path $PSScriptRoot 'Prepare-DevelopmentDependency.ps1')
$env:SPORTS_CAVE_RECORDER_SOURCE = Join-Path $PSScriptRoot '.local-data\reviewed-helper'
$python = Join-Path (Split-Path $PSScriptRoot -Parent) '.venv\Scripts\pythonw.exe'
$data = if ($DataDirectory) { [System.IO.Path]::GetFullPath($DataDirectory) } else { Join-Path $PSScriptRoot '.local-data' }
$arguments = @('-B','-m','desktop_recorder.coordinator','--data',('"' + $data + '"'))
if ($AcceptInjectedTestInput) { $arguments += '--accept-injected-test-input' }
Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
