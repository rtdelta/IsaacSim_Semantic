#!/usr/bin/env bash
set -euo pipefail
tool_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export SV_COMBINE_SCENE="${1:-/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_15_surround_fisheye.usda}"
[[ -f "$SV_COMBINE_SCENE" ]] || { echo "Scene not found: $SV_COMBINE_SCENE" >&2; exit 1; }
exec /usr/bin/python3 "$tool_dir/../launch_isaac.py" --exec "$tool_dir/open_scene_in_isaac.py"
