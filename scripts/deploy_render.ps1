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
    Write-Error "-AllowDirty is retired. Prepare reviewed paths/tests with scripts/deploy-sports-cave.ps1 -Prepare, then run that helper."
    exit 1
}
if ($ValidateOnly) {
    Write-Host "Dry-run validates the selected candidate without changing the real index or working files."
}
& (Join-Path $PSScriptRoot "deploy.ps1") -Message $Message -Paths $Paths -CheckOnly:($CheckOnly -or $ValidateOnly) -PushExisting:$PushExisting
exit $LASTEXITCODE
