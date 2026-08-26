[CmdletBinding()]
param(
    [switch]$Foreground
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$configPath = Join-Path $PSScriptRoot "gpufree_alist.json"
$rcloneConfigPath = Join-Path $PSScriptRoot "rclone.conf"

if (-not (Test-Path -LiteralPath $configPath)) {
    throw "Configuration file not found: $configPath"
}

if (-not (Test-Path -LiteralPath $rcloneConfigPath)) {
    throw "rclone configuration file not found: $rcloneConfigPath"
}

$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json

function Expand-ConfiguredPath {
    param([Parameter(Mandatory)][string]$Path)
    return [Environment]::ExpandEnvironmentVariables($Path)
}

$identityFile = Expand-ConfiguredPath $config.identity_file
$knownHostsFile = Expand-ConfiguredPath $config.known_hosts_file
$runtimeDirectory = Expand-ConfiguredPath $config.runtime_directory
$logDirectory = Join-Path $runtimeDirectory "logs"
$cacheDirectory = Join-Path $runtimeDirectory "cache"
$managerLog = Join-Path $logDirectory "mount-manager.log"
$sshLog = Join-Path $logDirectory "ssh.log"
$rcloneLog = Join-Path $logDirectory "rclone.log"
$statePath = Join-Path $runtimeDirectory "state.json"

New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
New-Item -ItemType Directory -Path $cacheDirectory -Force | Out-Null

function Write-ManagerLog {
    param(
        [Parameter(Mandatory)][string]$Message,
        [ValidateSet("INFO", "WARN", "ERROR")][string]$Level = "INFO"
    )

    $line = "{0} [{1}] {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Level, $Message
    Add-Content -LiteralPath $managerLog -Value $line -Encoding UTF8
    if ($Foreground) {
        Write-Host $line
    }
}

function Get-RcloneExecutable {
    $command = Get-Command rclone.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $packageRoot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
    $candidate = Get-ChildItem -LiteralPath $packageRoot -Directory -Filter "Rclone.Rclone*" -ErrorAction SilentlyContinue |
        ForEach-Object {
            Get-ChildItem -LiteralPath $_.FullName -Recurse -File -Filter "rclone.exe" -ErrorAction SilentlyContinue
        } |
        Sort-Object FullName -Descending |
        Select-Object -First 1

    if (-not $candidate) {
        throw "rclone.exe was not found. Install it with winget before starting the mount."
    }

    return $candidate.FullName
}

function Get-MatchingProcess {
    param(
        [Parameter(Mandatory)][string]$ExecutableName,
        [Parameter(Mandatory)][string[]]$RequiredText
    )

    $processes = Get-CimInstance Win32_Process -Filter "Name='$ExecutableName'" -ErrorAction SilentlyContinue
    foreach ($process in $processes) {
        $commandLine = [string]$process.CommandLine
        $matches = $true
        foreach ($needle in $RequiredText) {
            if ($commandLine.IndexOf($needle, [StringComparison]::OrdinalIgnoreCase) -lt 0) {
                $matches = $false
                break
            }
        }

        if ($matches) {
            return Get-Process -Id $process.ProcessId -ErrorAction SilentlyContinue
        }
    }

    return $null
}

function Test-LocalTcpPort {
    param([Parameter(Mandatory)][int]$Port)

    $client = [Net.Sockets.TcpClient]::new()
    try {
        $result = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        if (-not $result.AsyncWaitHandle.WaitOne(1000, $false)) {
            return $false
        }
        $client.EndConnect($result)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

function Test-AListHttp {
    $uri = "http://127.0.0.1:$($config.local_forward_port)/"
    try {
        $response = Invoke-WebRequest -Uri $uri -Method Get -TimeoutSec 4 -UseBasicParsing
        return ([int]$response.StatusCode -ge 200 -and [int]$response.StatusCode -lt 500)
    }
    catch {
        return $false
    }
}

function Invoke-RemoteAListStart {
    $target = "$($config.remote_user)@$($config.remote_host)"
    $remoteCommand = "if ! curl -fsS --max-time 3 http://$($config.remote_alist_host):$($config.remote_alist_port)/ >/dev/null 2>&1; then cd $($config.remote_alist_directory) && nohup ./alist server > alist.log 2>&1 </dev/null & fi"
    $arguments = @(
        "-T",
        "-i", $identityFile,
        "-p", [string]$config.remote_ssh_port,
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=10",
        "-o", "StrictHostKeyChecking=yes",
        "-o", "UserKnownHostsFile=$knownHostsFile",
        $target,
        $remoteCommand
    )

    Write-ManagerLog "Checking the remote AList service."
    $output = & "$env:SystemRoot\System32\OpenSSH\ssh.exe" @arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-ManagerLog "Remote AList start check failed: $($output -join ' ')" "WARN"
        return $false
    }

    return $true
}

function Get-TunnelProcess {
    $forwardSpec = "$($config.local_forward_port):$($config.remote_alist_host):$($config.remote_alist_port)"
    $target = "$($config.remote_user)@$($config.remote_host)"
    return Get-MatchingProcess -ExecutableName "ssh.exe" -RequiredText @($forwardSpec, $target)
}

function Start-Tunnel {
    $forwardSpec = "$($config.local_forward_port):$($config.remote_alist_host):$($config.remote_alist_port)"
    $target = "$($config.remote_user)@$($config.remote_host)"
    $arguments = @(
        "-N",
        "-T",
        "-i", $identityFile,
        "-L", $forwardSpec,
        "-p", [string]$config.remote_ssh_port,
        "-o", "BatchMode=yes",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "ConnectTimeout=10",
        "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=3",
        "-o", "StrictHostKeyChecking=yes",
        "-o", "UserKnownHostsFile=$knownHostsFile",
        "-E", $sshLog,
        $target
    )

    Write-ManagerLog "Starting SSH tunnel on local port $($config.local_forward_port)."
    return Start-Process -FilePath "$env:SystemRoot\System32\OpenSSH\ssh.exe" -ArgumentList $arguments -WindowStyle Hidden -PassThru
}

function Get-MountProcess {
    $remoteSpec = "$($config.rclone_remote_name):$($config.rclone_remote_path)"
    return Get-MatchingProcess -ExecutableName "rclone.exe" -RequiredText @("mount", $remoteSpec, [string]$config.mount_point)
}

function Start-RcloneMount {
    $rcloneExecutable = Get-RcloneExecutable
    $remoteSpec = "$($config.rclone_remote_name):$($config.rclone_remote_path)"
    $arguments = @(
        "mount",
        $remoteSpec,
        [string]$config.mount_point,
        "--config", $rcloneConfigPath,
        "--network-mode",
        "--volname", [string]$config.mount_volume_name,
        "--vfs-cache-mode", [string]$config.vfs_cache_mode,
        "--vfs-cache-max-age", [string]$config.vfs_cache_max_age,
        "--dir-cache-time", [string]$config.dir_cache_time,
        "--transfers", [string]$config.transfers,
        "--checkers", [string]$config.checkers,
        "--cache-dir", $cacheDirectory,
        "--log-level", "INFO",
        "--log-file", $rcloneLog
    )

    Write-ManagerLog "Mounting $remoteSpec at $($config.mount_point)."
    return Start-Process -FilePath $rcloneExecutable -ArgumentList $arguments -WindowStyle Hidden -PassThru
}

function Ensure-Shortcut {
    $shortcutPath = [string]$config.shortcut_path
    if (-not $shortcutPath) {
        return
    }

    $parent = Split-Path -Parent $shortcutPath
    if (-not (Test-Path -LiteralPath $parent)) {
        return
    }

    if (Test-Path -LiteralPath $shortcutPath) {
        return
    }

    try {
        $target = ([string]$config.mount_point).TrimEnd(":")
        $shortcutContent = @(
            "[InternetShortcut]",
            "URL=file:///$target`:/",
            "IconFile=$env:SystemRoot\System32\imageres.dll",
            "IconIndex=27"
        )
        [IO.File]::WriteAllLines($shortcutPath, $shortcutContent, [Text.Encoding]::ASCII)
        Write-ManagerLog "Created shortcut: $shortcutPath"
    }
    catch {
        Write-ManagerLog "Could not create shortcut $shortcutPath`: $($_.Exception.Message)" "WARN"
    }
}

function Write-State {
    param(
        $TunnelProcess,
        $MountProcess
    )

    $state = [ordered]@{
        manager_pid = $PID
        tunnel_pid = if ($TunnelProcess) { $TunnelProcess.Id } else { $null }
        mount_pid = if ($MountProcess) { $MountProcess.Id } else { $null }
        mount_point = [string]$config.mount_point
        updated_at = (Get-Date).ToString("o")
    }
    $state | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8
}

if (-not (Test-Path -LiteralPath $identityFile)) {
    throw "SSH identity file not found: $identityFile"
}

if (-not (Test-Path -LiteralPath $knownHostsFile)) {
    throw "SSH known_hosts file not found: $knownHostsFile"
}

$createdNew = $false
$mutex = [Threading.Mutex]::new($true, "Local\GPUFreeAListAutoMount", [ref]$createdNew)
if (-not $createdNew) {
    Write-ManagerLog "Another mount manager instance is already running."
    exit 0
}

$lastRemoteStartAttempt = [DateTime]::MinValue

try {
    Write-ManagerLog "Mount manager started with PID $PID."
    while ($true) {
        $tunnelProcess = Get-TunnelProcess
        if (-not $tunnelProcess) {
            if (((Get-Date) - $lastRemoteStartAttempt).TotalSeconds -ge [int]$config.remote_start_retry_seconds) {
                $null = Invoke-RemoteAListStart
                $lastRemoteStartAttempt = Get-Date
            }
            $tunnelProcess = Start-Tunnel
            Start-Sleep -Seconds 3
            $tunnelProcess.Refresh()
            if ($tunnelProcess.HasExited) {
                Write-ManagerLog "SSH tunnel exited with code $($tunnelProcess.ExitCode)." "WARN"
                $tunnelProcess = $null
            }
        }

        $alistAvailable = (Test-LocalTcpPort -Port ([int]$config.local_forward_port)) -and (Test-AListHttp)
        if (-not $alistAvailable -and ((Get-Date) - $lastRemoteStartAttempt).TotalSeconds -ge [int]$config.remote_start_retry_seconds) {
            $null = Invoke-RemoteAListStart
            $lastRemoteStartAttempt = Get-Date
            Start-Sleep -Seconds 3
            $alistAvailable = (Test-LocalTcpPort -Port ([int]$config.local_forward_port)) -and (Test-AListHttp)
        }

        $mountProcess = Get-MountProcess
        if ($alistAvailable -and -not $mountProcess) {
            if (Test-Path -LiteralPath "$($config.mount_point)\") {
                Write-ManagerLog "Mount point $($config.mount_point) is already occupied; waiting without replacing it." "WARN"
            }
            else {
                $mountProcess = Start-RcloneMount
                Start-Sleep -Seconds 4
                $mountProcess.Refresh()
                if ($mountProcess.HasExited) {
                    Write-ManagerLog "rclone mount exited with code $($mountProcess.ExitCode). See $rcloneLog" "WARN"
                    $mountProcess = $null
                }
            }
        }

        if ($mountProcess -and (Test-Path -LiteralPath "$($config.mount_point)\")) {
            Ensure-Shortcut
        }

        Write-State -TunnelProcess $tunnelProcess -MountProcess $mountProcess
        Start-Sleep -Seconds ([int]$config.poll_seconds)
    }
}
catch {
    Write-ManagerLog "Mount manager stopped by error: $($_.Exception.Message)" "ERROR"
    throw
}
finally {
    if ($createdNew) {
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}
