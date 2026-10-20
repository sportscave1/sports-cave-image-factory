[CmdletBinding()]
param([switch]$AcceptInjectedTestInput, [string]$DataDirectory, [string]$PythonExecutable)
$ErrorActionPreference = 'Stop'
$repository = Split-Path $PSScriptRoot -Parent
$python = if ($PythonExecutable) { [System.IO.Path]::GetFullPath($PythonExecutable) } else { Join-Path $repository '.venv\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Select an existing Python environment with -PythonExecutable. This development launcher is not an installer.' }
& $python -B -c 'import httpx,playwright'
if ($LASTEXITCODE -ne 0) { throw 'The selected Python environment needs the recorder requirements.' }
& (Join-Path $PSScriptRoot 'native\build.ps1')
$env:SPORTS_CAVE_RECORDER_SOURCE = $repository
$data = if ($DataDirectory) { [System.IO.Path]::GetFullPath($DataDirectory) } else { Join-Path $PSScriptRoot '.local-data' }
$arguments = @('-B','-m','desktop_recorder.coordinator','--data',('"' + $data + '"'))
if ($AcceptInjectedTestInput) { $arguments += '--accept-injected-test-input' }
Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
