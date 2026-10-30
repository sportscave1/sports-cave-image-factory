param([string]$Candidate)
$ErrorActionPreference='Stop'
$assembly=[Reflection.Assembly]::LoadFrom((Resolve-Path $Candidate).Path)
$type=$assembly.GetType('LocalFollowupResult')
$prompt=$type.GetMethod('ExpectedPrompt').Invoke($null,@())
$hash=$assembly.GetType('ChatSubmission').GetMethod('Digest').Invoke($null,@($prompt))
$result=@{conversation='6ae2d62d-1338-83ec-8619-6ea3635a7fa0';prompt_sha256=$hash;state='completed';simulated=$true;submissions=1;psd_attached=$false;edition_changes=0;production_jobs=0;business_outcome=('SIMULATED ONLY '+[char]0x2014+' no Shopify product created')}
$verify=$type.GetMethod('ValidResult')
if(-not $verify.Invoke($null,@([string]($result|ConvertTo-Json -Compress),[string]$prompt))){throw 'Valid local outcome rejected'}
foreach($change in @(@('conversation','wrong'),@('prompt_sha256','wrong'),@('state','attempted'),@('simulated',$false),@('submissions',2),@('psd_attached',$true),@('edition_changes',1),@('production_jobs',1),@('business_outcome','Shopify created'))) {
    $bad=$result.Clone();$bad[$change[0]]=$change[1]
    if($verify.Invoke($null,@([string]($bad|ConvertTo-Json -Compress),[string]$prompt))){throw "Invalid outcome accepted: $($change[0])"}
}
Write-Output '10 compiled local follow-up outcome cases passed'
$supports=$type.GetMethod('Supports')
foreach($page in @('http://127.0.0.1:18963/chat','https://chatgpt.com/c/6ae2d62d-1338-83ec-8619-6ea3635a7fa0','http://127.0.0.1:18964/chat','http://127.0.0.1:18963/chat?other=1')) {
    $browser=New-Object 'System.Collections.Generic.Dictionary[string,object]'
    $browser.Add('page',$page);$browser.Add('frame','top');$browser.Add('control','id:send')
    $target=New-Object 'System.Collections.Generic.Dictionary[string,object]'
    $target.Add('control_type','Button');$target.Add('automation_id','send');$target.Add('name','Submit once to local simulator');$target.Add('browser',$browser.PSObject.BaseObject)
    $accepted=$supports.Invoke($null,@($target.PSObject.BaseObject))
    if($accepted -ne ($page -eq 'http://127.0.0.1:18963/chat')){throw "Wrong scope acceptance: $page"}
}
Write-Output '4 compiled local follow-up scope cases passed'
