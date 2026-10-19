#!/usr/bin/env bash
set -euo pipefail
tool_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
isaac_root="${SV_ISAAC_ROOT:-/root/isaacsim}"
export LD_LIBRARY_PATH="$isaac_root/kit/python/lib:$isaac_root/kit:${LD_LIBRARY_PATH:-}"
for plugin_dir in "$isaac_root"/extscache/omni.sensors.nv.lidar-*/bin/model_plugins "$isaac_root"/extscache/omni.sensors.nv.common-*/bin/checker_lib/bin; do
    if [[ -d "$plugin_dir" ]]; then export LD_LIBRARY_PATH="$LD_LIBRARY_PATH:$plugin_dir"; fi
done
# This host has an invalid existing CPython bytecode cache in a Kit extension.
# Compile from source with a private cache namespace; do not alter the install.
export PYTHONPYCACHEPREFIX="$tool_dir/../reports/private_python_cache"
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
"$isaac_root/python.sh" "$tool_dir/validate_isaac.py" "$@"
# Kit fast shutdown can mask a Python exception with exit code zero.
python3 "$tool_dir/check_isaac_result.py"
