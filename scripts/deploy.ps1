[CmdletBinding()]
param(
    [string]$Message = "Deploy Sports Cave OS updates",
    [string[]]$Paths = @(),
    [switch]$CheckOnly,
    [switch]$PushExisting
)

# Python owns native exit codes; stderr warnings are not PowerShell exceptions.
# No deploy hook: one Git push uses the existing Render auto-deploy configuration.
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    $python = (Get-Command python -ErrorAction Stop).Source
}
$arguments = @((Join-Path $PSScriptRoot "deploy.py"), "--message", $Message)
if ($CheckOnly) { $arguments += "--check-only" }
if ($PushExisting) { $arguments += "--push-existing" }
foreach ($path in $Paths) { $arguments += @("--path", $path) }
& $python @arguments
exit $LASTEXITCODE
