#!/usr/bin/env bash
set -euo pipefail
tool_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
isaac_root="${AIRY_ISAAC_ROOT:-/root/isaacsim}"
export LD_LIBRARY_PATH="${isaac_root}/kit/python/lib:${isaac_root}/kit:${LD_LIBRARY_PATH:-}"
for plugin_dir in "${isaac_root}"/extscache/omni.sensors.nv.lidar-*/bin/model_plugins "${isaac_root}"/extscache/omni.sensors.nv.common-*/bin/checker_lib/bin; do
    if [[ -d "$plugin_dir" ]]; then export LD_LIBRARY_PATH="${LD_LIBRARY_PATH}:${plugin_dir}"; fi
done
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
"${isaac_root}/python.sh" "$tool_dir/validate_isaac.py" "$@"
# Kit fast_shutdown may exit with code 0 even after a Python assertion.
python3 "$tool_dir/check_report.py" "$@"
