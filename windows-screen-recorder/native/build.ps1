param([string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$framework = "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319"
$output = if ($OutputDirectory) { $OutputDirectory } else { Join-Path $PSScriptRoot 'bin' }
New-Item -ItemType Directory -Force $output | Out-Null
$refs = @('PresentationFramework','PresentationCore','WindowsBase','UIAutomationClient','UIAutomationTypes') | ForEach-Object { "/reference:$framework\WPF\$_.dll" }
& "$framework\csc.exe" /nologo /target:winexe /platform:x64 /optimize+ "/out:$output\DesktopRecorder.exe" /reference:System.Web.Extensions.dll /reference:System.Core.dll /reference:System.Xaml.dll @refs "$PSScriptRoot\Host.cs" "$PSScriptRoot\Playback.cs" "$PSScriptRoot\WindowIdentity.cs" "$PSScriptRoot\PendingEditorClick.cs" "$PSScriptRoot\TaskList.cs" "$PSScriptRoot\ScrollTargetSearch.cs" "$PSScriptRoot\ProductCopyResult.cs" "$PSScriptRoot\ProductGenerationResult.cs" "$PSScriptRoot\NativeMetrics.cs" "$PSScriptRoot\ToolbarPresentation.cs"
if ($LASTEXITCODE -ne 0) { throw 'Native build failed' }
