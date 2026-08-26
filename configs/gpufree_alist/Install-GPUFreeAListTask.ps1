[CmdletBinding()]
param(
    [switch]$DoNotStart
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$configPath = Join-Path $PSScriptRoot "gpufree_alist.json"
$startScript = Join-Path $PSScriptRoot "Start-GPUFreeAListMount.ps1"
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$taskName = [string]$config.task_name
$currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$powershellPath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$actionArguments = "-NoLogo -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$startScript`""

$action = New-ScheduledTaskAction -Execute $powershellPath -Argument $actionArguments
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited

$registrationMode = "ScheduledTask"
try {
    Register-ScheduledTask `
        -TaskName $taskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description "Automatically starts the GPUFree AList SSH tunnel and rclone mount." `
        -Force | Out-Null
    Write-Host "Registered scheduled task: $taskName"
}
catch {
    $registrationMode = "HKCU_Run"
    $runCommand = "`"$powershellPath`" $actionArguments"
    New-ItemProperty `
        -LiteralPath "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" `
        -Name "GPUFreeAListAutoMount" `
        -Value $runCommand `
        -PropertyType String `
        -Force | Out-Null
    Write-Warning "Scheduled task registration failed. Configured HKCU startup fallback instead: $($_.Exception.Message)"
}

$status = [ordered]@{
    installed_at = (Get-Date).ToString("o")
    registration_mode = $registrationMode
    task_name = $taskName
    user = $currentUser
    start_script = $startScript
}
$status | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot "installation_status.json") -Encoding UTF8

if (-not $DoNotStart) {
    Start-Process -FilePath $powershellPath -ArgumentList $actionArguments -WindowStyle Hidden
    Write-Host "Started the GPUFree AList mount manager."
}
