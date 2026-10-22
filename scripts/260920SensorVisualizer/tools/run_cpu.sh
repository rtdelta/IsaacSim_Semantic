#!/usr/bin/env bash
set -euo pipefail
tool_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
isaac_root="${SV_ISAAC_ROOT:-/root/isaacsim}"
for usd_dir in "$isaac_root"/extscache/omni.usd.libs-*; do
    export LD_LIBRARY_PATH="$usd_dir/bin:${LD_LIBRARY_PATH:-}"
done
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
python3 "$tool_dir/$1" "${@:2}"
