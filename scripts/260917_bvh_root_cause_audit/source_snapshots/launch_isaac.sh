#!/usr/bin/env bash
# Start the GUI with the cloned instance's required runtime libraries.
set -eo pipefail
source /opt/ros/jazzy/setup.bash
export LD_LIBRARY_PATH="/root/isaacsim/kit/python/lib:/root/isaacsim/exts/isaacsim.ros2.core/bin:${LD_LIBRARY_PATH:-}"
# RTX model implementations are loaded by basename on this pre-release build.
for lib_dir in /root/isaacsim/extscache/omni.sensors.nv.lidar-*/bin/model_plugins \
               /root/isaacsim/extscache/omni.sensors.nv.common-*/bin/checker_lib/bin; do
  if [[ -d "$lib_dir" ]]; then
    export LD_LIBRARY_PATH="$lib_dir:$LD_LIBRARY_PATH"
  fi
done
# This pre-release renderer cannot combine moving Gaussians with Motion BVH.
exec /root/isaacsim/isaac-sim.sh --/renderer/raytracingMotion/enabled=false \
  --/rtx/hydra/supportMultiTickRate=false --/rtx/rendering/perSensorTickTlas=false "$@"


