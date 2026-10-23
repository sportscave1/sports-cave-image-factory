param([string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$framework = "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319"
$output = if ($OutputDirectory) { $OutputDirectory } else { Join-Path $PSScriptRoot 'bin' }
New-Item -ItemType Directory -Force $output | Out-Null
$refs = @('PresentationFramework','PresentationCore','WindowsBase','UIAutomationClient','UIAutomationTypes') | ForEach-Object { "/reference:$framework\WPF\$_.dll" }
& "$framework\csc.exe" /nologo /target:winexe /platform:x64 /optimize+ "/out:$output\DesktopRecorder.exe" /reference:System.Web.Extensions.dll /reference:System.Web.dll /reference:System.Core.dll /reference:System.Xaml.dll @refs "$PSScriptRoot\Host.cs" "$PSScriptRoot\InvocationSubscriptions.cs" "$PSScriptRoot\Playback.cs" "$PSScriptRoot\WindowIdentity.cs" "$PSScriptRoot\PendingEditorClick.cs" "$PSScriptRoot\TaskList.cs" "$PSScriptRoot\ScrollTargetSearch.cs" "$PSScriptRoot\ProductCopyResult.cs" "$PSScriptRoot\ProductGenerationResult.cs" "$PSScriptRoot\NativeMetrics.cs" "$PSScriptRoot\ToolbarPresentation.cs" "$PSScriptRoot\ProductPickerResult.cs" "$PSScriptRoot\DropdownSelection.cs" "$PSScriptRoot\ScrollAccess.cs" "$PSScriptRoot\DialogResult.cs" "$PSScriptRoot\EdgeDropdownAdapter.cs" "$PSScriptRoot\DesktopSession.cs" "$PSScriptRoot\CopyText.cs" "$PSScriptRoot\RecordingIndicator.cs" "$PSScriptRoot\BrowserTabs.cs" "$PSScriptRoot\KeyboardIntent.cs" "$PSScriptRoot\BrowserIdentity.cs" "$PSScriptRoot\ProductPromptProof.cs" "$PSScriptRoot\RunTransfer.cs" "$PSScriptRoot\BrowserDownload.cs"
if ($LASTEXITCODE -ne 0) { throw 'Native build failed' }
$sourceHashes = [ordered]@{}
Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*.cs' | Sort-Object Name | ForEach-Object {
    $sourceHashes[$_.Name] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
}
$sourceHashes['build.ps1'] = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
$manifest = [ordered]@{
    built_utc = [DateTime]::UtcNow.ToString('o')
    source_directory = $PSScriptRoot
    executable_sha256 = (Get-FileHash -LiteralPath (Join-Path $output 'DesktopRecorder.exe') -Algorithm SHA256).Hash.ToLowerInvariant()
    sources = $sourceHashes
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $output 'build-manifest.json') -Encoding UTF8
