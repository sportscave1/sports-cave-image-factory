$ErrorActionPreference = "Stop"
$installRoot = Join-Path $env:LOCALAPPDATA "SportsCaveFilesHelper"
$bridgePath = Join-Path $installRoot "SportsCaveFilesHelper.exe"
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$runValueName = "SportsCaveFilesHelper"
$protocolKeys = @(
    "HKCU:\Software\Classes\sports-cave-files",
    "HKCU:\Software\Classes\sports-cave-photoshop"
)

Get-Process -Name "SportsCaveFilesHelper" -ErrorAction SilentlyContinue |
    Where-Object {
        try {
            [System.IO.Path]::GetFullPath($_.Path) -eq [System.IO.Path]::GetFullPath($bridgePath)
        } catch {
            $false
        }
    } |
    Stop-Process -Force -ErrorAction SilentlyContinue
Get-Process -Name "SportsCaveOSDesktop" -ErrorAction SilentlyContinue |
    Stop-Process -Force -ErrorAction SilentlyContinue

foreach ($protocolKey in $protocolKeys) {
    if (Test-Path -LiteralPath $protocolKey) {
        Remove-Item -LiteralPath $protocolKey -Recurse -Force
    }
}
if (Test-Path -LiteralPath $runKey) {
Remove-ItemProperty -Path $runKey -Name $runValueName -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path ([Environment]::GetFolderPath("Programs")) "Sports Cave OS Desktop.lnk") -Force -ErrorAction SilentlyContinue
}
if (Test-Path -LiteralPath $installRoot) {
    Remove-Item -LiteralPath $installRoot -Recurse -Force
}
Write-Host "Sports Cave desktop helper uninstalled."
