[CmdletBinding()]
param(
    [string]$Message = "Deploy Sports Cave OS updates",
    [string[]]$Paths = @(),
    [switch]$CheckOnly,
    [switch]$PushExisting
)

# Compatibility entry point; use the manifest-based helper for all future releases.
$ErrorActionPreference = "Stop"
if ($Paths.Count) {
    Write-Error 'Prepare a reviewed manifest with deploy-sports-cave.ps1 -Prepare -Paths ... -Tests ..., then run deploy-sports-cave.ps1. No implicit selection is allowed.'
    exit 1
}
& (Join-Path $PSScriptRoot 'deploy-sports-cave.ps1') -DryRun:$CheckOnly
exit $LASTEXITCODE
