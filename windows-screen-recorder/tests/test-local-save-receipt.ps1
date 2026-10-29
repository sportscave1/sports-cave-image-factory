param([Parameter(Mandatory=$true)][string]$Candidate)
$ErrorActionPreference='Stop'
$assembly=[Reflection.Assembly]::LoadFrom((Resolve-Path -LiteralPath $Candidate).Path)
$method=$assembly.GetType('LocalSaveResult').GetMethod('Complete',[Reflection.BindingFlags]'Public,Static')
$passed=0
foreach($case in @('valid','partial','duplicate','short','source','hash','size','cancelled')) {
    $items=@(1..8 | ForEach-Object { @{relative_path="WEBP/image-$_.webp";metadata=@{size=100;content_hash=('a'*64)}} })
    $body=@{source_run='isolated-source';receipt=@{successes=$items;failures=@();cancelled=$false}}
    switch($case) {
        'partial' {$body.receipt.failures=@(@{error='test'})}
        'duplicate' {$items[1].relative_path=$items[0].relative_path}
        'short' {$body.receipt.successes=@($items[0])}
        'source' {$body.source_run='other-source'}
        'hash' {$items[0].metadata.content_hash='bad'}
        'size' {$items[0].metadata.size=0}
        'cancelled' {$body.receipt.cancelled=$true}
    }
    $accepted=$false
    try {$accepted=$method.Invoke($null,@([string]($body|ConvertTo-Json -Depth 8 -Compress),[string]'isolated-source'))}
    catch {if($case -eq 'valid'){throw}}
    if([bool]$accepted -ne ($case -eq 'valid')){throw "Unexpected receipt acceptance: $case"}
    $passed++
}
Write-Output "$passed native receipt cases passed. No UI or replay invoked."


