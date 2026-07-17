param(
    [string]$Topic = "/point_cloud",
    [switch]$ReadOneHeader
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\setup_ros2_jazzy_env.ps1"

Set-Location -LiteralPath $RosWorkspace

Write-Host "ROS 2 topics:"
& $PixiExe run ros2 topic list -t

Write-Host ""
Write-Host "Topic info for ${Topic}:"
& $PixiExe run ros2 topic info $Topic -v
$InfoExitCode = $LASTEXITCODE

if ($ReadOneHeader) {
    Write-Host ""
    Write-Host "Waiting for one header from ${Topic}:"
    & $PixiExe run ros2 topic echo $Topic --once --field header
    exit $LASTEXITCODE
}

exit $InfoExitCode
