#!/usr/bin/env bash
set -euo pipefail
package_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
isaac_root="${NZ3_ISAAC_ROOT:-/root/isaacsim}"
# This host puts system libraries first. Its system libpython 3.12.3 is
# incompatible with Kit's bundled 3.12.13 extension modules. Fix only this process.
export LD_LIBRARY_PATH="${isaac_root}/kit/python/lib:${isaac_root}/kit:${LD_LIBRARY_PATH:-}"
# The lidar core loads its checker implementation by library name.
for nz3_plugin_dir in "${isaac_root}"/extscache/omni.sensors.nv.lidar-*/bin/model_plugins; do
    if [[ -d "$nz3_plugin_dir" ]]; then
        export LD_LIBRARY_PATH="${LD_LIBRARY_PATH}:${nz3_plugin_dir}"
    fi
done
cd -- "$package_dir"
exec "${isaac_root}/python.sh" "$package_dir/isaac_demo.py" "$@"
