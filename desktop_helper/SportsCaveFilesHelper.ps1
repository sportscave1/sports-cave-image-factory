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

function Find-Illustrator {
    $registryPaths = @(
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\App Paths\Illustrator.exe",
        "HKLM:\Software\Microsoft\Windows\CurrentVersion\App Paths\Illustrator.exe"
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
        $candidate = Get-ChildItem -LiteralPath $adobeRoot -Directory -Filter "Adobe Illustrator *" -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending |
            ForEach-Object { Join-Path $_.FullName "Support Files\Contents\Windows\Illustrator.exe" } |
            Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
            Select-Object -First 1
        if ($candidate) { return [System.IO.Path]::GetFullPath($candidate) }
    }
    return $null
}

function Request-FileHydration([string]$Path) {
    $stream = $null
    try {
        $stream = [System.IO.File]::Open(
            $Path,
            [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Read,
            [System.IO.FileShare]::ReadWrite
        )
        $buffer = New-Object byte[] 1
        [void]$stream.Read($buffer, 0, 1)
    } catch {
        throw "This file could not be made available locally. Check Dropbox Desktop sync and try again."
    } finally {
        if ($null -ne $stream) { $stream.Dispose() }
    }
}

function Resolve-SafeTarget([string]$Root, [string]$RelativePath) {
    if ([string]::IsNullOrWhiteSpace($RelativePath) -or [System.IO.Path]::IsPathRooted($RelativePath) -or $RelativePath.Contains(":")) {
        throw "The requested path is not allowed."
    }
    $segments = $RelativePath.Replace("/", "\").Split("\", [System.StringSplitOptions]::RemoveEmptyEntries)
    if (-not $segments.Count -or @($segments | Where-Object { $_ -in @(".", "..") }).Count) {
        throw "The requested path is not allowed."
    }
    $target = [System.IO.Path]::GetFullPath((Join-Path $Root ($segments -join "\")))
    $rootPrefix = $Root + [System.IO.Path]::DirectorySeparatorChar
    if (-not $target.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "The requested path is outside the approved Dropbox folder."
    }
    if (-not (Test-Path -LiteralPath $target)) {
        throw "This file is not available locally yet. Check Dropbox Desktop sync and try again."
    }
    return $target
}

function Set-FilesClipboard([string[]]$Paths, [string]$Effect) {
    Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
    $fileList = New-Object System.Collections.Specialized.StringCollection
    $fileList.AddRange([string[]]$Paths)
    $data = New-Object System.Windows.Forms.DataObject
    $data.SetFileDropList($fileList)
    $effectValue = if ($Effect -eq "move") { [uint32]2 } else { [uint32]1 }
    $effectBytes = [System.BitConverter]::GetBytes($effectValue)
    $effectStream = New-Object System.IO.MemoryStream
    $effectStream.Write($effectBytes, 0, $effectBytes.Length)
    $effectStream.Position = 0
    $data.SetData("Preferred DropEffect", $false, $effectStream)
    [System.Windows.Forms.Clipboard]::SetDataObject($data, $true)
}

try {
    $uri = [System.Uri]$ProtocolUri
    if (-not $uri.IsAbsoluteUri -or
        $uri.Scheme -notin @("sports-cave-files", "sports-cave-photoshop") -or
        $uri.Host -notin @("open", "clipboard") -or
        ($uri.Scheme -eq "sports-cave-photoshop" -and $uri.Host -ne "open")) {
        throw "Unsupported request."
    }
    $query = Read-ProtocolQuery $uri
    if ($uri.Host -eq "open") {
        if (-not $query.ContainsKey("path") -or @($query.Keys | Where-Object { $_ -notin @("path", "kind") }).Count) {
            throw "Unsupported request."
        }
        if ($query.ContainsKey("kind") -and $query.kind -notin @("file", "folder")) {
            throw "Unsupported request."
        }
    } else {
        if (-not $query.ContainsKey("paths") -or @($query.Keys | Where-Object { $_ -notin @("paths", "effect") }).Count) {
            throw "Unsupported request."
        }
        if ($query.ContainsKey("effect") -and $query.effect -notin @("copy", "move")) {
            throw "Unsupported request."
        }
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

    if ($uri.Host -eq "clipboard") {
        try {
            $decodedPaths = ConvertFrom-Json -InputObject ([string]$query.paths)
            $relativePaths = @($decodedPaths)
        } catch {
            throw "The clipboard request is invalid."
        }
        if (-not $relativePaths.Count -or $relativePaths.Count -gt 100) {
            throw "Select between 1 and 100 items for the Windows clipboard."
        }
        $targets = @()
        foreach ($relativePath in $relativePaths) {
            $targetPath = Resolve-SafeTarget $root ([string]$relativePath)
            if (-not (Test-Path -LiteralPath $targetPath -PathType Container)) {
                Request-FileHydration $targetPath
            }
            $targets += $targetPath
        }
        if ($ValidateOnly) {
            $targets | Write-Output
            exit 0
        }
        $clipboardEffect = if ($query.ContainsKey("effect")) { [string]$query.effect } else { "copy" }
        Set-FilesClipboard ([string[]]$targets) $clipboardEffect
        exit 0
    }

    $target = Resolve-SafeTarget $root ([string]$query.path)

    $isFolder = Test-Path -LiteralPath $target -PathType Container
    $extension = ""
    if (-not $isFolder) {
        $extension = [System.IO.Path]::GetExtension($target).ToLowerInvariant()
        if ($blockedExtensions -contains $extension) {
            throw "This file type cannot be opened by the Sports Cave helper."
        }
    }
    if ($uri.Scheme -eq "sports-cave-photoshop" -and ($isFolder -or $extension -notin @(".psd", ".psb"))) {
        throw "The Photoshop action only supports PSD and PSB files."
    }
    if ($ValidateOnly) {
        Write-Output $target
        exit 0
    }

    if ($isFolder) {
        Start-Process -FilePath "explorer.exe" -ArgumentList ('"' + $target + '"') -ErrorAction Stop
        exit 0
    }

    Request-FileHydration $target

    if ($extension -in @(".psd", ".psb")) {
        $photoshop = Find-Photoshop
        if ($photoshop) {
            Start-Process -FilePath $photoshop -ArgumentList ('"' + $target + '"') -ErrorAction Stop
            exit 0
        }
    }
    if ($extension -eq ".ai") {
        $illustrator = Find-Illustrator
        if ($illustrator) {
            Start-Process -FilePath $illustrator -ArgumentList ('"' + $target + '"') -ErrorAction Stop
            exit 0
        }
    }
    Start-Process -FilePath $target -ErrorAction Stop
} catch {
    Show-SafeError ([string]$_.Exception.Message)
}
