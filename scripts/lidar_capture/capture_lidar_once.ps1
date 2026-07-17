param(
    [string]$Topic = "/point_cloud",
    [string]$OutputDir = "",
    [int]$TimeoutSec = 30,
    [int]$CsvLimit = 5000,
    [int]$MaxPoints = 0,
    [string]$Prefix = "point_cloud",
    [switch]$BestEffort
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\setup_ros2_jazzy_env.ps1"

if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir = Join-Path $ProjectRoot "isaacProject\lidar_exports"
}

$CaptureScript = Join-Path $PSScriptRoot "capture_lidar_once.py"
$Arguments = @(
    "run",
    "python",
    $CaptureScript,
    "--topic",
    $Topic,
    "--output-dir",
    $OutputDir,
    "--timeout-sec",
    "$TimeoutSec",
    "--csv-limit",
    "$CsvLimit",
    "--max-points",
    "$MaxPoints",
    "--prefix",
    $Prefix
)

if ($BestEffort) {
    $Arguments += "--best-effort"
}

Set-Location -LiteralPath $RosWorkspace
& $PixiExe @Arguments
exit $LASTEXITCODE
