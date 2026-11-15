[CmdletBinding()]
param(
    [ValidateSet('New','Route','Open','List','Categories','Where','Verify','RecordTests','Status','ApproveBase','Preview','NewDraft','SaveDraft','OpenDraft','ListDrafts','RecoverDraft','DraftUI')]
    [string]$Action = 'List',
    [string]$Description,
    [ValidateSet('ADS','EMAIL','PRODUCTS','EDITIONS','CORE','INTEGRATIONS','COMMERCE','GROWTH','RELEASE')]
    [string]$Category,
    [string]$Id,
    [string]$Owner,
    [string]$Status,
    [string]$Evidence,
    [ValidateSet('passed','failed')][string]$Result,
    [string]$Base,
    [string]$Name,
    [string[]]$Files = @(),
    [int]$ExpectedRevision = -1,
    [int]$Revision = -1,
    [string]$StudioHome = $(if ($env:SPORTS_CAVE_STUDIO_HOME) { $env:SPORTS_CAVE_STUDIO_HOME } else { 'C:\Dev\SportsCaveWorktrees' }),
    [switch]$Open,
    [switch]$NonInteractive
)
$ErrorActionPreference = 'Stop'
$python = (Get-Command python -ErrorAction Stop).Source
$helper = Join-Path $PSScriptRoot 'studio.py'
$verb = $Action.ToLowerInvariant()
if ($Action -eq 'DraftUI') { $verb = 'draft-ui' }
if ($Action -eq 'RecordTests') { $verb = 'record-tests' }
if ($Action -eq 'ApproveBase') { $verb = 'approve-base' }
foreach ($item in @('NewDraft','SaveDraft','OpenDraft','ListDrafts','RecoverDraft')) { if ($Action -eq $item) { $verb = $item.Replace('Draft','-Draft').ToLowerInvariant() } }
if ($Action -eq 'New' -and -not $Category) {
    $routing = & $python -B $helper route --description $Description
    if ($LASTEXITCODE -ne 0) { throw 'Routing failed.' }
    $route = ($routing -join [Environment]::NewLine) | ConvertFrom-Json
    if ($route.needs_confirmation) {
        if ($NonInteractive) { throw "Ambiguous routing: $($route.candidates -join ', '). Supply -Category." }
        Write-Host "Routing needs your choice. Candidates: $($route.candidates -join ', ')"
        $Category = (Read-Host 'Category (ADS EMAIL PRODUCTS EDITIONS CORE INTEGRATIONS COMMERCE GROWTH RELEASE)').ToUpperInvariant()
        if ($Category -notin @('ADS','EMAIL','PRODUCTS','EDITIONS','CORE','INTEGRATIONS','COMMERCE','GROWTH','RELEASE')) {
            throw 'No valid category selected; no workspace created.'
        }
    }
}
$argsForStudio = @('-B', $helper, $verb, '--home', $StudioHome, '--repo', (Get-Location).Path)
foreach ($pair in @(
    @('--description',$Description), @('--category',$Category), @('--id',$Id),
    @('--owner',$Owner), @('--status',$Status), @('--evidence',$Evidence),
    @('--result',$Result), @('--base',$Base), @('--name',$Name)
)) { if ($pair[1]) { $argsForStudio += $pair } }
foreach ($file in $Files) { $argsForStudio += @('--file', $file) }
if ($ExpectedRevision -ge 0) { $argsForStudio += @('--expected-revision', [string]$ExpectedRevision) }
if ($Revision -ge 0) { $argsForStudio += @('--revision', [string]$Revision) }
if ($Open) { $argsForStudio += '--open' }
& $python @argsForStudio
if ($LASTEXITCODE -ne 0) { throw "Studio $Action failed; see the precise blocker above." }
