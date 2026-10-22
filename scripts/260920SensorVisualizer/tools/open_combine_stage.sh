#!/usr/bin/env bash
# Run from a terminal in the remote desktop, so DISPLAY/XAUTHORITY are inherited.
set -euo pipefail
isaac_root="${SV_ISAAC_ROOT:-/root/isaacsim}"
tool_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
scene="${1:-/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_13_3dgs_contract.usda}"
[[ -f "$scene" ]] || { echo "Scene not found: $scene" >&2; exit 1; }
# This affects this shell and its child Isaac process, never system limits.
if (( $(ulimit -Sn) < 16384 )); then ulimit -Sn 16384; fi
export SV_COMBINE_SCENE="$scene"
export ISAACSIM_PATH="$isaac_root"
# Use the deployed publisher's launch environment, including core/bin and Jazzy
# libraries. The generic Isaac launcher alone can leave the ROS factory unloaded.
publisher_launcher="/root/gpufree-data/semantic/scripts/260907LidarVisualizer/launch_isaac.py"
[[ -f "$publisher_launcher" ]] || { echo "Missing publisher launcher: $publisher_launcher" >&2; exit 1; }
exec /usr/bin/python3 "$publisher_launcher" \
    --exec "$tool_dir/open_scene_in_isaac.py"
