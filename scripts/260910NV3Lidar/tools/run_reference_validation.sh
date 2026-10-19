#!/usr/bin/env bash
set -euo pipefail
tool_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
isaac_root="${NZ3_ISAAC_ROOT:-/root/isaacsim}"
# Application dependencies, shared by standard RTX lidar assets on this host.
export LD_LIBRARY_PATH="${isaac_root}/kit/python/lib:${isaac_root}/kit:${LD_LIBRARY_PATH:-}"
for plugin_dir in "${isaac_root}"/extscache/omni.sensors.nv.lidar-*/bin/model_plugins; do
    if [[ -d "$plugin_dir" ]]; then
        export LD_LIBRARY_PATH="${LD_LIBRARY_PATH}:${plugin_dir}"
    fi
done
exec "${isaac_root}/python.sh" "$tool_dir/validate_reference_asset.py" "$@"
