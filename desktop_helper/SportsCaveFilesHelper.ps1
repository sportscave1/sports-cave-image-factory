param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$ProtocolUri,
    [switch]$ValidateOnly,
    [switch]$NoDialog
)

$ErrorActionPreference = "Stop"
$blockedExtensions = @(
    ".appref-ms", ".application", ".bat", ".chm", ".cmd", ".com", ".cpl",
    ".dll", ".exe", ".gadget", ".hta", ".inf", ".ins", ".jar", ".js",
    ".jse", ".lnk", ".msi", ".msp", ".pif", ".ps1", ".py", ".pyw",
    ".reg", ".scr", ".sct", ".shb", ".shs", ".url", ".vbs", ".vbe",
    ".website", ".ws", ".wsc", ".wsf"
)

function Show-SafeError([string]$Message) {
    if ($NoDialog) {
        [Console]::Error.WriteLine($Message)
        exit 1
    }
    try {
        Add-Type -AssemblyName PresentationFramework -ErrorAction Stop
        [System.Windows.MessageBox]::Show(
            $Message,
            "Sports Cave Files",
            [System.Windows.MessageBoxButton]::OK,
            [System.Windows.MessageBoxImage]::Warning
        ) | Out-Null
    } catch {
        Write-Error $Message
    }
    exit 1
}

function Read-ProtocolQuery([System.Uri]$Uri) {
    $values = @{}
    foreach ($pair in $Uri.Query.TrimStart("?").Split("&", [System.StringSplitOptions]::RemoveEmptyEntries)) {
        $parts = $pair.Split("=", 2)
        $key = [System.Uri]::UnescapeDataString($parts[0])
        if ($values.ContainsKey($key)) {
            throw "Duplicate protocol value."
        }
        $value = if ($parts.Count -eq 2) { [System.Uri]::UnescapeDataString($parts[1]) } else { "" }
        $values[$key] = $value
    }
    return $values
}

function Find-Photoshop {
    $registryPaths = @(
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\App Paths\Photoshop.exe",
        "HKLM:\Software\Microsoft\Windows\CurrentVersion\App Paths\Photoshop.exe"
    )
    foreach ($registryPath in $registryPaths) {
        try {
            $candidate = (Get-ItemProperty -LiteralPath $registryPath -ErrorAction Stop)."(default)"
            if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
                return [System.IO.Path]::GetFullPath($candidate)
            }
        } catch {}
    }
    $adobeRoot = Join-Path ${env:ProgramFiles} "Adobe"
    if (Test-Path -LiteralPath $adobeRoot -PathType Container) {
        $candidate = Get-ChildItem -LiteralPath $adobeRoot -Directory -Filter "Adobe Photoshop *" -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending |
            ForEach-Object { Join-Path $_.FullName "Photoshop.exe" } |
            Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
            Select-Object -First 1
        if ($candidate) { return [System.IO.Path]::GetFullPath($candidate) }
    }
    return $null
}

try {
    $uri = [System.Uri]$ProtocolUri
    if (-not $uri.IsAbsoluteUri -or $uri.Scheme -ne "sports-cave-files" -or $uri.Host -ne "open") {
        throw "Unsupported request."
    }
    $query = Read-ProtocolQuery $uri
    if (-not $query.ContainsKey("path") -or @($query.Keys | Where-Object { $_ -notin @("path", "kind") }).Count) {
        throw "Unsupported request."
    }
    if ($query.ContainsKey("kind") -and $query.kind -notin @("file", "folder")) {
        throw "Unsupported request."
    }

    $configPath = Join-Path $PSScriptRoot "config.json"
    if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
        throw "The local Dropbox folder has not been configured. Run Install.ps1 again."
    }
    $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
    $root = [System.IO.Path]::GetFullPath([string]$config.RootPath).TrimEnd("\")
    if (-not (Test-Path -LiteralPath $root -PathType Container)) {
        throw "The configured Sportscave Team Folder is unavailable. Check Dropbox Desktop."
    }

    $relative = [string]$query.path
    if ([string]::IsNullOrWhiteSpace($relative) -or [System.IO.Path]::IsPathRooted($relative) -or $relative.Contains(":")) {
        throw "The requested path is not allowed."
    }
    $segments = $relative.Replace("/", "\").Split("\", [System.StringSplitOptions]::RemoveEmptyEntries)
    if (-not $segments.Count -or @($segments | Where-Object { $_ -in @(".", "..") }).Count) {
        throw "The requested path is not allowed."
    }
    $target = [System.IO.Path]::GetFullPath((Join-Path $root ($segments -join "\")))
    $rootPrefix = $root + [System.IO.Path]::DirectorySeparatorChar
    if (-not $target.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "The requested path is outside the approved Dropbox folder."
    }
    if (-not (Test-Path -LiteralPath $target)) {
        throw "This file is not available locally yet. Check Dropbox Desktop sync and try again."
    }

    $isFolder = Test-Path -LiteralPath $target -PathType Container
    if (-not $isFolder) {
        $extension = [System.IO.Path]::GetExtension($target).ToLowerInvariant()
        if ($blockedExtensions -contains $extension) {
            throw "This file type cannot be opened by the Sports Cave helper."
        }
    }
    if ($ValidateOnly) {
        Write-Output $target
        exit 0
    }

    if ($isFolder) {
        Start-Process -FilePath "explorer.exe" -ArgumentList ('"' + $target + '"') -ErrorAction Stop
        exit 0
    }

    if ($extension -in @(".psd", ".psb")) {
        $photoshop = Find-Photoshop
        if ($photoshop) {
            Start-Process -FilePath $photoshop -ArgumentList ('"' + $target + '"') -ErrorAction Stop
            exit 0
        }
    }
    Start-Process -FilePath $target -ErrorAction Stop
} catch {
    Show-SafeError ([string]$_.Exception.Message)
}
