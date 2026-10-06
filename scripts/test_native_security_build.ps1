$ErrorActionPreference = 'Stop'
$securityRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$securityOutput = Join-Path $securityRoot 'output/security-native-test.exe'
Add-Type -AssemblyName PresentationFramework
Add-Type -AssemblyName PresentationCore
Add-Type -AssemblyName WindowsBase
Add-Type -AssemblyName System.Xaml
Add-Type -AssemblyName Microsoft.CSharp
$securityCompiler = New-Object Microsoft.CSharp.CSharpCodeProvider
$securityParameters = New-Object System.CodeDom.Compiler.CompilerParameters
$securityParameters.GenerateExecutable = $true
$securityParameters.OutputAssembly = $securityOutput
$securityParameters.CompilerOptions = '/target:winexe'
$securityReferences = @('System.dll','System.Core.dll','System.Net.Http.dll','System.Web.Extensions.dll') + @(
    [System.Windows.DependencyObject].Assembly.Location,
    [System.Windows.Media.ImageSource].Assembly.Location,
    [System.Windows.Window].Assembly.Location,
    [System.Xaml.XamlReader].Assembly.Location,
    (Join-Path $securityRoot 'desktop_helper/lib/Microsoft.Web.WebView2.Core.dll'),
    (Join-Path $securityRoot 'desktop_helper/lib/Microsoft.Web.WebView2.Wpf.dll')
)
foreach ($securityReference in ($securityReferences | Select-Object -Unique)) {
    [void]$securityParameters.ReferencedAssemblies.Add($securityReference)
}
$securitySource=Get-Content -LiteralPath (Join-Path $securityRoot 'desktop_helper/SportsCaveFilesDesktop.cs') -Raw
$securityResult=$securityCompiler.CompileAssemblyFromSource($securityParameters,$securitySource)
if ($securityResult.Errors.HasErrors) {throw (($securityResult.Errors | ForEach-Object {$_.ToString()}) -join "`n")}
Write-Output 'Native Windows package compilation passed; capture/login/navigation runtime verification remains separate.'
