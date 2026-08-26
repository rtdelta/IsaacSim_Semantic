[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$configPath = Join-Path $PSScriptRoot "gpufree_alist.json"
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$runtimeDirectory = [Environment]::ExpandEnvironmentVariables([string]$config.runtime_directory)
$statePath = Join-Path $runtimeDirectory "state.json"

function Stop-ExpectedProcess {
    param(
        [AllowNull()]$ProcessId,
        [Parameter(Mandatory)][string]$ExpectedName
    )

    if (-not $ProcessId) {
        return
    }

    $numericProcessId = [int]$ProcessId
    $process = Get-Process -Id $numericProcessId -ErrorAction SilentlyContinue
    if (-not $process -or $process.ProcessName -ne $ExpectedName) {
        return
    }

    Stop-Process -Id $numericProcessId -Force
    Write-Host "Stopped $ExpectedName process $numericProcessId."
}

$state = $null
if (Test-Path -LiteralPath $statePath) {
    $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
}

if ($state) {
    Stop-ExpectedProcess -ProcessId $state.mount_pid -ExpectedName "rclone"
    Start-Sleep -Seconds 2
    Stop-ExpectedProcess -ProcessId $state.tunnel_pid -ExpectedName "ssh"
    Stop-ExpectedProcess -ProcessId $state.manager_pid -ExpectedName "powershell"
    Stop-ExpectedProcess -ProcessId $state.manager_pid -ExpectedName "pwsh"
}

$managerNeedle = "Start-GPUFreeAListMount.ps1"
$remainingManagers = Get-CimInstance Win32_Process -Filter "Name='powershell.exe' OR Name='pwsh.exe'" -ErrorAction SilentlyContinue |
    Where-Object { [string]$_.CommandLine -like "*$managerNeedle*" }
foreach ($manager in $remainingManagers) {
    Stop-Process -Id $manager.ProcessId -Force -ErrorAction SilentlyContinue
}

Write-Host "GPUFree AList automatic mount has been stopped."
