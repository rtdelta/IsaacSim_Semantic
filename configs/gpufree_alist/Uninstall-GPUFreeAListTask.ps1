[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$configPath = Join-Path $PSScriptRoot "gpufree_alist.json"
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$taskName = [string]$config.task_name
$stopScript = Join-Path $PSScriptRoot "Stop-GPUFreeAListMount.ps1"

& $stopScript

$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($task) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "Removed scheduled task: $taskName"
}

Remove-ItemProperty `
    -LiteralPath "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" `
    -Name "GPUFreeAListAutoMount" `
    -ErrorAction SilentlyContinue

Write-Host "Startup registration was removed. Configuration and logs were preserved."
