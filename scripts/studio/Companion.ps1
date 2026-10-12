[CmdletBinding()]
param(
 [ValidateSet('Start','Open','Status','EnableStartup','DisableStartup')][string]$Action='Status',
 [Parameter(Mandatory)][string]$Id,
 [Parameter(Mandatory)][string]$Owner,
 [ValidateSet('Default','Chrome','Edge')][string]$Browser='Default',
 [string]$StudioHome='C:\Dev\SportsCaveWorktrees',
 [string]$Python=(Get-Command python -ErrorAction Stop).Source,
 [switch]$ApproveStartup
)
$ErrorActionPreference='Stop'
$helper=Join-Path $PSScriptRoot 'companion.py'
if ($Id -notmatch '^[a-zA-Z0-9-]+$' -or $Owner -notmatch '^[a-zA-Z0-9/_-]+$') { throw 'Invalid task identity.' }
$taskName='SportsCave-Studio-'+$Id
if ($Action -in @('EnableStartup','DisableStartup')) {
 if (-not $ApproveStartup) { throw 'Windows sign-in startup changes require explicit -ApproveStartup approval.' }
 if ($Action -eq 'DisableStartup') {
  Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
  return
 }
 & $Python -B $helper status --home $StudioHome --id $Id --owner $Owner
 if ($LASTEXITCODE -ne 0) { throw 'Task validation failed.' }
 if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) { throw 'Startup already registered; no existing task overwritten.' }
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
if ($Action -eq 'Start' -and (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue)) {
 & $Python -B $helper resume --home $StudioHome --id $Id --owner $Owner
 if ($LASTEXITCODE -ne 0) { throw 'Task validation failed.' }
 Start-ScheduledTask -TaskName $taskName
 Write-Output 'Starting the approved scheduled companion.'
 return
}
& $Python -B $helper $Action.ToLowerInvariant() --home $StudioHome --id $Id --owner $Owner --browser $Browser.ToLowerInvariant()
if ($LASTEXITCODE -ne 0) { throw 'Companion failed; no existing workspace reassigned.' }
