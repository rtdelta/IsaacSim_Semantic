param(
    [string]$Topic = "/point_cloud",
    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\setup_ros2_jazzy_env.ps1"

if ([string]::IsNullOrWhiteSpace($Output)) {
    $Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $Output = Join-Path $ProjectRoot "isaacProject\lidar_bags\point_cloud_$Stamp"
}

$Parent = Split-Path -Parent $Output
New-Item -ItemType Directory -Force -Path $Parent | Out-Null

Set-Location -LiteralPath $RosWorkspace
Write-Host "Recording $Topic to $Output"
Write-Host "Press Ctrl+C to stop recording."
& $PixiExe run ros2 bag record $Topic -o $Output
exit $LASTEXITCODE
