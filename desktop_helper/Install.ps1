param(
    [string]$DropboxRoot = "",
    [string]$AppUrl = "https://sports-cave-image-factory.onrender.com/files-window",
    [string[]]$AllowedOrigins = @(
        "https://sports-cave-image-factory.onrender.com",
        "http://127.0.0.1:8501",
        "http://localhost:8501"
    )
)

$ErrorActionPreference = "Stop"
$installRoot = Join-Path $env:LOCALAPPDATA "SportsCaveFilesHelper"
$existingConfigPath = Join-Path $installRoot "config.json"
$bridgePath = Join-Path $installRoot "SportsCaveOSDesktop.exe"
$legacyBridgePath = Join-Path $installRoot "SportsCaveFilesHelper.exe"
$bridgeTempPath = Join-Path $env:TEMP ("SportsCaveOSDesktop-" + [Guid]::NewGuid().ToString("N") + ".exe")
$iconSource = Join-Path $PSScriptRoot "SportsCaveFiles.ico"
$iconPath = Join-Path $installRoot "SportsCaveFiles.ico"
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$runValueName = "SportsCaveFilesHelper"
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

if ([string]::IsNullOrWhiteSpace($DropboxRoot) -and (Test-Path -LiteralPath $existingConfigPath -PathType Leaf)) {
    try {
        $existingConfig = Get-Content -LiteralPath $existingConfigPath -Raw | ConvertFrom-Json
        $existingRoot = [string]$existingConfig.RootPath
        if (-not [string]::IsNullOrWhiteSpace($existingRoot) -and (Test-Path -LiteralPath $existingRoot -PathType Container)) {
            $DropboxRoot = $existingRoot
        }
    } catch {}
}

if (-not [string]::IsNullOrWhiteSpace($DropboxRoot)) {
    $DropboxRoot = [System.IO.Path]::GetFullPath($DropboxRoot).TrimEnd("\")
    if (-not (Test-Path -LiteralPath $DropboxRoot -PathType Container)) {
        throw "The configured Dropbox folder does not exist."
    }
}

New-Item -ItemType Directory -Path $installRoot -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "SportsCaveFilesHelper.ps1") -Destination $installRoot -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "Uninstall.ps1") -Destination $installRoot -Force
if (-not (Test-Path -LiteralPath $iconSource -PathType Leaf)) {
    throw "The Sports Cave Files icon is missing. Download a fresh helper package."
}
Copy-Item -LiteralPath $iconSource -Destination $iconPath -Force

Get-Process -Name "SportsCaveFilesHelper" -ErrorAction SilentlyContinue |
    Where-Object {
        try {
            [System.IO.Path]::GetFullPath($_.Path) -eq [System.IO.Path]::GetFullPath($legacyBridgePath)
        } catch {
            $false
        }
    } |
    Stop-Process -Force -ErrorAction SilentlyContinue
Get-Process -Name "SportsCaveOSDesktop" -ErrorAction SilentlyContinue |
    Where-Object {
        try {
            [System.IO.Path]::GetFullPath($_.Path) -eq [System.IO.Path]::GetFullPath($bridgePath)
        } catch {
            $false
        }
    } |
    Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 150
if (Test-Path -LiteralPath $legacyBridgePath -PathType Leaf) {
    Remove-Item -LiteralPath $legacyBridgePath -Force
}

$legacyLauncherPath = Join-Path $installRoot "Sports Cave Photoshop Launcher.exe"
if (Test-Path -LiteralPath $legacyLauncherPath -PathType Leaf) {
    Remove-Item -LiteralPath $legacyLauncherPath -Force
}

$libSource = Join-Path $PSScriptRoot "lib"
$runtimeSource = Join-Path $PSScriptRoot "runtimes\win-x64\native\WebView2Loader.dll"
if (
    -not (Test-Path -LiteralPath (Join-Path $libSource "Microsoft.Web.WebView2.Core.dll") -PathType Leaf) -or
    -not (Test-Path -LiteralPath (Join-Path $libSource "Microsoft.Web.WebView2.Wpf.dll") -PathType Leaf) -or
    -not (Test-Path -LiteralPath $runtimeSource -PathType Leaf)
) {
    throw "The WebView2 desktop files are missing. Download a fresh helper package."
}
$bridgeSource = Get-Content -LiteralPath (Join-Path $PSScriptRoot "SportsCaveFilesDesktop.cs") -Raw
try {
    Add-Type -AssemblyName PresentationFramework
    Add-Type -AssemblyName PresentationCore
    Add-Type -AssemblyName WindowsBase
    Add-Type -AssemblyName System.Xaml
    $wpfReferences = @(
        [System.Windows.DependencyObject].Assembly.Location,
        [System.Windows.Media.ImageSource].Assembly.Location,
        [System.Windows.Window].Assembly.Location,
        [System.Xaml.XamlReader].Assembly.Location
    ) | Select-Object -Unique
    $compileReferences = @(
        "System.dll",
        "System.Core.dll",
        "System.Net.Http.dll",
        "System.Web.Extensions.dll"
    ) + $wpfReferences + @(
        (Join-Path $libSource "Microsoft.Web.WebView2.Core.dll"),
        (Join-Path $libSource "Microsoft.Web.WebView2.Wpf.dll")
    )
    Add-Type -AssemblyName Microsoft.CSharp
    $compiler = New-Object Microsoft.CSharp.CSharpCodeProvider
    $compilerParameters = New-Object System.CodeDom.Compiler.CompilerParameters
    $compilerParameters.GenerateExecutable = $true
    $compilerParameters.GenerateInMemory = $false
    $compilerParameters.OutputAssembly = $bridgeTempPath
    $compilerParameters.CompilerOptions = "/target:winexe /win32icon:`"$iconPath`""
    foreach ($reference in ($compileReferences | Select-Object -Unique)) {
        [void]$compilerParameters.ReferencedAssemblies.Add($reference)
    }
    $compileResult = $compiler.CompileAssemblyFromSource($compilerParameters, $bridgeSource)
    if ($compileResult.Errors.HasErrors) {
        $messages = @($compileResult.Errors | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine
        throw "The native desktop helper could not be built. $messages"
    }
    if (-not (Test-Path -LiteralPath $bridgeTempPath -PathType Leaf)) {
        throw "The native desktop helper could not be built."
    }
    Move-Item -LiteralPath $bridgeTempPath -Destination $bridgePath -Force
} finally {
    if (Test-Path -LiteralPath $bridgeTempPath) {
        Remove-Item -LiteralPath $bridgeTempPath -Force
    }
}
Copy-Item -LiteralPath (Join-Path $libSource "Microsoft.Web.WebView2.Core.dll") -Destination $installRoot -Force
Copy-Item -LiteralPath (Join-Path $libSource "Microsoft.Web.WebView2.Wpf.dll") -Destination $installRoot -Force
Copy-Item -LiteralPath $runtimeSource -Destination $installRoot -Force

@{
    RootPath = $DropboxRoot
    AppUrl = $AppUrl
    InstalledAt = (Get-Date).ToString("o")
    HelperVersion = 8
    AllowedOrigins = @(
        $AllowedOrigins |
            ForEach-Object { [string]$_ } |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
            ForEach-Object { $_.Trim().TrimEnd("/") } |
            Select-Object -Unique
    )
} |
    ConvertTo-Json |
    Set-Content -LiteralPath (Join-Path $installRoot "config.json") -Encoding UTF8

$filesCommand = '"' + $bridgePath + '" "%1"'
Register-Protocol $filesProtocolKey "Sports Cave Files Protocol" "Sports Cave Files" $filesCommand

$photoshopCommand = '"' + $bridgePath + '" "%1"'
Register-Protocol $photoshopProtocolKey "Open in Photoshop" "Photoshop" $photoshopCommand

New-Item -Path $runKey -Force | Out-Null
New-ItemProperty `
    -Path $runKey `
    -Name $runValueName `
    -Value ('"' + $bridgePath + '" --background') `
    -PropertyType String `
    -Force |
    Out-Null

Start-Process -WindowStyle Hidden -FilePath $bridgePath -ArgumentList "--background"
Start-Sleep -Milliseconds 350

$programs = [Environment]::GetFolderPath("Programs")
$shortcutPath = Join-Path $programs "Sports Cave OS Desktop.lnk"
$shortcutShell = New-Object -ComObject WScript.Shell
$shortcut = $shortcutShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $bridgePath
$shortcut.Arguments = "--app"
$shortcut.WorkingDirectory = $installRoot
$shortcut.Description = "Open Sports Cave Files"
$shortcut.IconLocation = $iconPath
$shortcut.Save()

Write-Host "Sports Cave Files Desktop installed."
Write-Host "Open it from the Start menu for native drag, Copy and image clipboard support."
