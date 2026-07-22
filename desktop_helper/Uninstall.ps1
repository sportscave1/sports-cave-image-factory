$ErrorActionPreference = "Stop"
$installRoot = Join-Path $env:LOCALAPPDATA "SportsCaveFilesHelper"
$protocolKey = "HKCU:\Software\Classes\sports-cave-files"

if (Test-Path -LiteralPath $protocolKey) {
    Remove-Item -LiteralPath $protocolKey -Recurse -Force
}
if (Test-Path -LiteralPath $installRoot) {
    Remove-Item -LiteralPath $installRoot -Recurse -Force
}
Write-Host "Sports Cave desktop helper uninstalled."
