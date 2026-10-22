set pagination off
set confirm off
set debuginfod enabled off
set print thread-events off
set startup-with-shell off
set disable-randomization off
set auto-load safe-path /
handle SIGPIPE nostop noprint pass
set environment LD_LIBRARY_PATH /root/isaacsim/extscache/omni.sensors.nv.common-3.0.0+f9bf0dda.lx64.r.cp312/bin/checker_lib/bin:/root/isaacsim/extscache/omni.sensors.nv.common-3.0.0+f9bf0dda.lx64.r.cp312/bin:/root/isaacsim/extscache/omni.sensors.nv.lidar-3.0.0+f9bf0dda.lx64.r.cp312/bin/model_plugins:/root/isaacsim/kit/python/lib:/root/isaacsim/kit:/root/isaacsim/kit/kernel/plugins:/root/isaacsim/kit/plugins/rtx:/root/isaacsim/.:/root/isaacsim/exts/isaacsim.robot.schema/plugins/lib:/root/isaacsim/extsDeprecated/isaacsim.robot_motion.lula/pip_prebundle:/root/isaacsim/exts/isaacsim.robot_motion.cumotion/pip_prebundle:/root/isaacsim/exts/isaacsim.robot_motion.pink/pip_prebundle:/root/isaacsim/exts/isaacsim.asset.exporter.urdf/pip_prebundle:/root/isaacsim/kit:/root/isaacsim/kit/kernel/plugins:/root/isaacsim/kit/libs/iray:/root/isaacsim/kit/plugins:/root/isaacsim/kit/plugins/bindings-python:/root/isaacsim/kit/plugins/carb_gfx:/root/isaacsim/kit/plugins/rtx:/root/isaacsim/kit/plugins/gpu.foundation
set environment LD_PRELOAD /root/isaacsim/kit/libcarb.so
set environment PYTHONPATH :/root/isaacsim/kit/python/lib/python3.12:/root/isaacsim/kit/python/lib/python3.12/site-packages:/root/isaacsim/python_packages:/root/isaacsim/exts/isaacsim.simulation_app:/root/isaacsim/kit/kernel/py:/root/isaacsim/kit/plugins/bindings-python:/root/isaacsim/exts/isaacsim.replicator.episode_recorder/pip_prebundle:/root/isaacsim/exts/isaacsim.replicator.teleop/pip_prebundle:/root/isaacsim/extsDeprecated/isaacsim.robot_motion.lula/pip_prebundle:/root/isaacsim/exts/isaacsim.robot_motion.cumotion/pip_prebundle:/root/isaacsim/exts/isaacsim.robot_motion.pink/pip_prebundle:/root/isaacsim/exts/isaacsim.asset.exporter.urdf/pip_prebundle:/root/isaacsim/extscache/omni.kit.pip_archive-0.0.0+f9bf0dda.lx64.cp312/pip_prebundle:/root/isaacsim/exts/omni.isaac.core_archive/pip_prebundle:/root/isaacsim/exts/omni.pip.compute/pip_prebundle:/root/isaacsim/exts/omni.pip.cloud/pip_prebundle
unset environment PYTHONHOME
source /root/gpufree-data/diagnostics/bvh_local_mode_20260918_0147/cases/freeze_sensor_400000000_1/snapshot_trace_hook.py
run
quit
