param([string]$Candidate,[string]$Receipt,[string]$Prompt)
$ErrorActionPreference='Stop'
$assembly=[Reflection.Assembly]::LoadFrom((Resolve-Path $Candidate).Path)
$method=$assembly.GetType('LocalSaveResult').GetMethod('CopyProof',[Reflection.BindingFlags]'Public,Static')
$json=[IO.File]::ReadAllText((Resolve-Path $Receipt).Path)
$body=$json|ConvertFrom-Json
$text=[IO.File]::ReadAllText((Resolve-Path $Prompt).Path)
$cases=@{valid=$text; wrong_action=$text.Replace('Upload to Draft','Upload to Active'); wrong_token=$text.Replace($body.receipt.save_token,'wrong-token'); missing_file=$text.Replace($body.receipt.successes[0].metadata.id,'wrong-id'); empty=''}
foreach($key in $cases.Keys) {
    $ok=$false
    try {$proof=$method.Invoke($null,@([string]$json,[string]$body.source_run,[string]$cases[$key]));$ok=$null -ne $proof}
    catch {if($key -eq 'valid'){throw}}
    if($ok -ne ($key -eq 'valid')){throw "Unexpected acceptance: $key"}
    Write-Output "$key passed"
}
