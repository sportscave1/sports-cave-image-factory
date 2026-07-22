param([string]$DropboxRoot = "")

$ErrorActionPreference = "Stop"
$installRoot = Join-Path $env:LOCALAPPDATA "SportsCaveFilesHelper"
$protocolKey = "HKCU:\Software\Classes\sports-cave-files"

if ([string]::IsNullOrWhiteSpace($DropboxRoot)) {
    $shell = New-Object -ComObject Shell.Application
    $selection = $shell.BrowseForFolder(0, "Select your locally synced Sportscave Team Folder", 0x41, 0)
    if ($null -eq $selection) {
        Write-Host "Installation cancelled."
        exit 1
    }
    $DropboxRoot = [string]$selection.Self.Path
}

$DropboxRoot = [System.IO.Path]::GetFullPath($DropboxRoot).TrimEnd("\")
if (-not (Test-Path -LiteralPath $DropboxRoot -PathType Container)) {
    throw "The selected folder does not exist."
}

New-Item -ItemType Directory -Path $installRoot -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "SportsCaveFilesHelper.ps1") -Destination $installRoot -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "Uninstall.ps1") -Destination $installRoot -Force
@{ RootPath = $DropboxRoot; InstalledAt = (Get-Date).ToString("o") } |
    ConvertTo-Json |
    Set-Content -LiteralPath (Join-Path $installRoot "config.json") -Encoding UTF8

New-Item -Path $protocolKey -Force | Out-Null
Set-Item -Path $protocolKey -Value "URL:Sports Cave Files Protocol"
New-ItemProperty -Path $protocolKey -Name "URL Protocol" -Value "" -PropertyType String -Force | Out-Null
$commandKey = Join-Path $protocolKey "shell\open\command"
New-Item -Path $commandKey -Force | Out-Null
$helperPath = Join-Path $installRoot "SportsCaveFilesHelper.ps1"
$command = '"' + (Join-Path $PSHOME "powershell.exe") + '" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + $helperPath + '" "%1"'
Set-Item -Path $commandKey -Value $command

Write-Host "Sports Cave desktop helper installed."
Write-Host "Approved folder: $DropboxRoot"
Write-Host "Restart your browser before testing Open from Sports Cave OS."
