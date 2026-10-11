param([Parameter(Mandatory=$true)][string]$Id, [Parameter(Mandatory=$true)][string]$Owner)
& (Join-Path $PSScriptRoot 'Studio.ps1') -Action Verify -Id $Id -Owner $Owner
