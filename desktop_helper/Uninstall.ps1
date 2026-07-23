$ErrorActionPreference = "Stop"
$installRoot = Join-Path $env:LOCALAPPDATA "SportsCaveFilesHelper"
$protocolKeys = @(
    "HKCU:\Software\Classes\sports-cave-files",
    "HKCU:\Software\Classes\sports-cave-photoshop"
)

foreach ($protocolKey in $protocolKeys) {
    if (Test-Path -LiteralPath $protocolKey) {
        Remove-Item -LiteralPath $protocolKey -Recurse -Force
    }
}
if (Test-Path -LiteralPath $installRoot) {
    Remove-Item -LiteralPath $installRoot -Recurse -Force
}
Write-Host "Sports Cave desktop helper uninstalled."
