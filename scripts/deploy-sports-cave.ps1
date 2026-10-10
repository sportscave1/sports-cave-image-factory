[CmdletBinding()]
param(
    [ValidateSet('Normal', 'Full')][string]$Mode = 'Normal',
    [string]$Manifest = '',
    [switch]$DryRun,
    [switch]$Prepare,
    [string[]]$Paths = @(),
    [string[]]$Tests = @(),
    [string[]]$Imports = @(),
    [string]$Message = 'Deploy approved Sports Cave OS updates',
    [switch]$VerifyOnly,
    [switch]$IncludeCompletedInbox,
    [switch]$PushWithoutRenderVerification
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { $python = (Get-Command python -ErrorAction Stop).Source }
$arguments = @((Join-Path $PSScriptRoot 'sports_cave_deploy.py'), '--mode', $Mode.ToLowerInvariant(), '--message', $Message)
if ($Manifest) { $arguments += @('--manifest', $Manifest) }
if ($DryRun) { $arguments += '--dry-run' }
if ($Prepare) { $arguments += '--prepare' }
if ($VerifyOnly) { $arguments += '--verify-only' }
if ($IncludeCompletedInbox) { $arguments += '--include-completed-inbox' }
if ($PushWithoutRenderVerification) { $arguments += '--push-without-render-verification' }
foreach ($item in $Paths) { $arguments += @('--path', $item) }
foreach ($item in $Tests) { $arguments += @('--test', $item) }
foreach ($item in $Imports) { $arguments += @('--import-module', $item) }
Push-Location -LiteralPath $repoRoot
try {
    & $python @arguments
    $result = $LASTEXITCODE
} finally { Pop-Location }
exit $result
