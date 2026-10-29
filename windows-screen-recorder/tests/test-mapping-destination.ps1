param([string]$Candidate)
$ErrorActionPreference='Stop'
$assembly=[Reflection.Assembly]::LoadFrom((Resolve-Path $Candidate).Path)
$method=$assembly.GetType('BrowserIdentity').GetMethod('MappingDestination',[Reflection.BindingFlags]'Public,Static')
$source='https://sports-cave-image-factory.onrender.com/?page=product_uploads'
$cases=@(
    @($source,'id:map',$true),
    @($source,'label:button:assignmentEdition Ops',$true),
    @($source,'id:save',$false),
    @('https://chatgpt.com/','id:map',$false),
    @('https://sports-cave-image-factory.onrender.com/?page=edition_ops','id:map',$false),
    @('https://sports-cave-image-factory.onrender.com.evil.test/?page=product_uploads','id:map',$false)
)
foreach($case in $cases) {
    $identity=New-Object 'System.Collections.Generic.Dictionary[string,object]'
    $identity.Add('page',$case[0]);$identity.Add('control',$case[1])
    $result=$method.Invoke($null,@($identity.PSObject.BaseObject))
    if(($null -ne $result) -ne $case[2]){throw "Unexpected Mapping classification: $($case[0]) $($case[1])"}
    if($case[2] -and $result -ne 'https://sports-cave-image-factory.onrender.com/?page=edition_ops'){throw 'Wrong destination'}
}
Write-Output '6 compiled Mapping scope cases passed'
