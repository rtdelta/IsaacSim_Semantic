$ErrorActionPreference = "Stop"

$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
$RosWorkspace = Join-Path $Root "ros2_jazzy_pixi"
$RosEnv = Join-Path $RosWorkspace ".pixi\envs\default"
$RosPrefix = Join-Path $RosEnv "Library"
$PixiDefault = Join-Path $env:USERPROFILE "AppData\Local\pixi\bin\pixi.exe"

$env:PIXI_CACHE_DIR = Join-Path $Root ".pixi-cache"
$env:PIXI_HOME = Join-Path $Root ".pixi-home"

$env:ROS_DISTRO = "jazzy"
$env:ROS_DOMAIN_ID = "0"
$env:RMW_IMPLEMENTATION = "rmw_fastrtps_cpp"
$env:AMENT_PREFIX_PATH = $RosPrefix
$env:CMAKE_PREFIX_PATH = $RosPrefix

Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
Remove-Item Env:OLD_PYTHONPATH -ErrorAction SilentlyContinue

$RosBin = Join-Path $RosPrefix "bin"
if (Test-Path -LiteralPath $RosBin) {
    $env:Path = "$RosBin;$env:Path"
}

if (Test-Path -LiteralPath $PixiDefault) {
    $script:PixiExe = $PixiDefault
} else {
    $script:PixiExe = "pixi"
}

$script:ProjectRoot = $Root
$script:RosWorkspace = $RosWorkspace
