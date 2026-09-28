# Compatibility entry point. All Git checks live in the tracked deploy helper.
# No extra Render deploy hook; an ordinary push triggers the existing services.
[CmdletBinding()]
param(
    [string]$Message = "Deploy Sports Cave OS updates",
    [string[]]$Paths = @(),
    [switch]$CheckOnly,
    [switch]$ValidateOnly,
    [switch]$PushExisting,
    [switch]$AllowDirty
)

if ($AllowDirty) {
    Write-Error "-AllowDirty is retired. Select intended changes with scripts/deploy.ps1 -Paths instead."
    exit 1
}
if ($ValidateOnly) {
    Write-Host "Validation now safely normalizes and stages selected files, without committing or pushing."
}
& (Join-Path $PSScriptRoot "deploy.ps1") -Message $Message -Paths $Paths -CheckOnly:($CheckOnly -or $ValidateOnly) -PushExisting:$PushExisting
exit $LASTEXITCODE
