#!/usr/bin/env bash
set -euo pipefail
tool_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
isaac_root="${SV_ISAAC_ROOT:-/root/isaacsim}"
export LD_LIBRARY_PATH="$isaac_root/kit/python/lib:$isaac_root/kit:${LD_LIBRARY_PATH:-}"
for plugin_dir in "$isaac_root"/extscache/omni.sensors.nv.lidar-*/bin/model_plugins "$isaac_root"/extscache/omni.sensors.nv.common-*/bin/checker_lib/bin; do
    if [[ -d "$plugin_dir" ]]; then export LD_LIBRARY_PATH="$LD_LIBRARY_PATH:$plugin_dir"; fi
done
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
# Thirteen RTX sensors need many CUDA/Vulkan file descriptors. Process-local only.
if (( $(ulimit -Sn) < 16384 )); then ulimit -Sn 16384; fi
set +e
"$isaac_root/python.sh" "$tool_dir/validate_combine_stage.py" "$@"
process_status=$?
set -e
# Both assertions and process exit must pass; cleanup failures count as failures.
python3 -c 'import json,sys; p=sys.argv[1]; r=json.load(open(p)); r["checks_passed"]=r.get("passed") is True; r["process_exit_code"]=int(sys.argv[2]); r["passed"]=r["checks_passed"] and r["process_exit_code"]==0; open(p,"w").write(json.dumps(r,indent=2)+"\n"); print("RUNTIME_PASSED",r["passed"]); sys.exit(0 if r["passed"] else 1)' "$tool_dir/../reports/combine_stage/runtime.json" "$process_status"
