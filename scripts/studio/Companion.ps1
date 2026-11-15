[CmdletBinding()]
param(
 [ValidateSet('Start','Open','Workspace','Status','EnableStartup','DisableStartup')][string]$Action='Status',
 [Parameter(Mandatory)][string]$Id,
 [Parameter(Mandatory)][string]$Owner,
 [ValidateSet('Default','Chrome','Edge')][string]$Browser='Default',
 [ValidateSet('Default')][string]$BrowserProfile='Default',
 [ValidateSet('Open','Edit','Preview','Changes')][string]$Intent='Edit',
 [string]$OsOrigin='https://sports-cave-image-factory.onrender.com',
 [string]$StudioHome='C:\Dev\SportsCaveWorktrees',
 [string]$Python=(Get-Command python -ErrorAction Stop).Source,
 [switch]$ApproveStartup
)
$ErrorActionPreference='Stop'
$helper=Join-Path $PSScriptRoot 'companion.py'
if ($Id -notmatch '^[a-zA-Z0-9-]+$' -or $Owner -notmatch '^[a-zA-Z0-9/_-]+$') { throw 'Invalid task identity.' }
$taskName='SportsCave-Studio-'+$Id
function Test-OwnedStartup($task) {
 if ($task.Actions.Count -ne 1) { return $false }
 $a=$task.Actions[0]
 if ((Split-Path $a.Execute -Leaf) -ne 'pythonw.exe') { return $false }
 if ($a.Arguments -notmatch '^-B "([^"]+)" watch --home "([^"]+)" --id ([a-zA-Z0-9-]+) --owner ([a-zA-Z0-9/_-]+)$') { return $false }
 $registeredHelper=$Matches[1]; $registeredHome=$Matches[2]; $registeredId=$Matches[3]; $registeredOwner=$Matches[4]
 return ($registeredHelper.Replace('\','/').TrimEnd('/') -eq $helper.Replace('\','/').TrimEnd('/') -and
         $registeredHome.Replace('\','/').TrimEnd('/') -eq $StudioHome.Replace('\','/').TrimEnd('/') -and
         $registeredId -ceq $Id -and $registeredOwner -ceq $Owner -and
         $a.Execute.Replace('\','/').TrimEnd('/') -eq (Join-Path (Split-Path $Python) 'pythonw.exe').Replace('\','/').TrimEnd('/'))
}
$namedTask=Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($namedTask -and -not (Test-OwnedStartup $namedTask)) { throw 'Existing startup belongs to another assignment. Owner approval cannot reassign it; no task changed.' }
$ownedTasks=@(Get-ScheduledTask | Where-Object { $_.TaskName -like 'SportsCave-Studio-*' -and (Test-OwnedStartup $_) })
if ($ownedTasks.Count -gt 1) { throw 'Multiple startup registrations match this assignment. Review their owners before any change.' }
$approvedTask=if ($ownedTasks.Count -eq 1) { $ownedTasks[0] } else { $null }
if ($Action -in @('EnableStartup','DisableStartup')) {
 if (-not $ApproveStartup) { throw 'Windows sign-in startup changes require explicit -ApproveStartup approval.' }
 if ($Action -eq 'DisableStartup') {
  if (-not $approvedTask) { throw 'No startup with this exact helper, home, task and owner was found. Nothing removed.' }
  Unregister-ScheduledTask -TaskName $approvedTask.TaskName -Confirm:$false
  return
 }
 & $Python -B $helper status --home $StudioHome --id $Id --owner $Owner
 if ($LASTEXITCODE -ne 0) { throw 'Task validation failed.' }
 if ($approvedTask) { throw 'Startup already registered for this exact identity, possibly under an older name; no existing task overwritten.' }
 foreach ($value in @($Python,$helper,$StudioHome)) { if ($value.Contains('"')) { throw 'Quotes in paths are unsupported.' } }
 $arguments='-B "'+$helper+'" watch --home "'+$StudioHome+'" --id '+$Id+' --owner '+$Owner
 $pythonw=Join-Path (Split-Path $Python) 'pythonw.exe'
 if (-not (Test-Path -LiteralPath $pythonw)) { throw 'pythonw.exe required for quiet startup.' }
 $actionSpec=New-ScheduledTaskAction -Execute $pythonw -Argument $arguments -WorkingDirectory (Split-Path (Split-Path $PSScriptRoot))
 $user=[System.Security.Principal.WindowsIdentity]::GetCurrent().Name
 $trigger=New-ScheduledTaskTrigger -AtLogOn -User $user
 $recoveryTrigger=New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
 $principal=New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
 $settings=New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
 Register-ScheduledTask -TaskName $taskName -Action $actionSpec -Trigger @($trigger,$recoveryTrigger) -Principal $principal -Settings $settings | Out-Null
 Write-Output 'Opt-in startup registered for this Windows user only. No credentials or elevation stored.'
 return
}
if ($Action -eq 'Start' -and $approvedTask) {
 & $Python -B $helper resume --home $StudioHome --id $Id --owner $Owner
 if ($LASTEXITCODE -ne 0) { throw 'Task validation failed.' }
 Start-ScheduledTask -TaskName $approvedTask.TaskName
 Write-Output 'Starting the approved scheduled companion.'
 return
}
& $Python -B $helper $Action.ToLowerInvariant() --home $StudioHome --id $Id --owner $Owner --browser $Browser.ToLowerInvariant() --profile $BrowserProfile --os-origin $OsOrigin --intent $Intent.ToLowerInvariant()
if ($LASTEXITCODE -ne 0) { throw 'Companion failed; no existing workspace reassigned.' }
