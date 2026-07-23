param([string]$DropboxRoot = "")

$ErrorActionPreference = "Stop"
$installRoot = Join-Path $env:LOCALAPPDATA "SportsCaveFilesHelper"
$filesProtocolKey = "HKCU:\Software\Classes\sports-cave-files"
$photoshopProtocolKey = "HKCU:\Software\Classes\sports-cave-photoshop"

function Register-Protocol(
    [string]$ProtocolKey,
    [string]$Description,
    [string]$ApplicationName,
    [string]$Command
) {
    New-Item -Path $ProtocolKey -Force | Out-Null
    Set-Item -Path $ProtocolKey -Value ("URL:" + $Description)
    New-ItemProperty -Path $ProtocolKey -Name "URL Protocol" -Value "" -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $ProtocolKey -Name "FriendlyTypeName" -Value $Description -PropertyType String -Force | Out-Null

    $applicationKey = Join-Path $ProtocolKey "Application"
    New-Item -Path $applicationKey -Force | Out-Null
    New-ItemProperty -Path $applicationKey -Name "ApplicationName" -Value $ApplicationName -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $applicationKey -Name "ApplicationDescription" -Value $Description -PropertyType String -Force | Out-Null

    $commandKey = Join-Path $ProtocolKey "shell\open\command"
    New-Item -Path $commandKey -Force | Out-Null
    Set-Item -Path $commandKey -Value $Command
}

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

$helperPath = Join-Path $installRoot "SportsCaveFilesHelper.ps1"
$filesCommand = '"' + (Join-Path $PSHOME "powershell.exe") + '" -Sta -WindowStyle Hidden -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + $helperPath + '" "%1"'
Register-Protocol $filesProtocolKey "Sports Cave Files Protocol" "Sports Cave Files" $filesCommand

$launcherPath = Join-Path $installRoot "Sports Cave Photoshop Launcher.exe"
if (Test-Path -LiteralPath $launcherPath) {
    Remove-Item -LiteralPath $launcherPath -Force
}
$launcherSource = Get-Content -LiteralPath (Join-Path $PSScriptRoot "PhotoshopProtocolLauncher.cs") -Raw
Add-Type -TypeDefinition $launcherSource -Language CSharp -OutputAssembly $launcherPath -OutputType WindowsApplication
if (-not (Test-Path -LiteralPath $launcherPath -PathType Leaf)) {
    throw "The Photoshop protocol launcher could not be installed."
}
$photoshopCommand = '"' + $launcherPath + '" "%1"'
Register-Protocol $photoshopProtocolKey "Open in Photoshop" "Photoshop" $photoshopCommand

Write-Host "Sports Cave desktop helper installed."
Write-Host "Approved folder: $DropboxRoot"
Write-Host "Restart your browser before testing Open from Sports Cave OS."
