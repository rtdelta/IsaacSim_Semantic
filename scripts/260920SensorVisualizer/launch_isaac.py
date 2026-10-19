"""Launch the native Kit GUI without a shell script (system Python, Linux)."""
import os
from pathlib import Path
import sys
import resource


def launch():
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    resource.setrlimit(resource.RLIMIT_NOFILE, (min(max(soft, 65536), hard), hard))
    install = Path(os.environ.get('ISAACSIM_PATH', '/root/isaacsim')).resolve()
    kit = install / 'kit/kit'
    experience = install / 'apps/isaacsim.exp.full.kit'
    if not kit.is_file() or not experience.is_file():
        raise SystemExit('Set ISAACSIM_PATH to the Isaac Sim installation directory')
    env = os.environ.copy()
    for key in ('PYTHONHOME', 'PYTHONPATH', 'LD_PRELOAD', 'VIRTUAL_ENV', 'CONDA_PREFIX'):
        env.pop(key, None)
    env.update(RESOURCE_NAME='IsaacSim', ROS_DISTRO='jazzy',
               RMW_IMPLEMENTATION='rmw_fastrtps_cpp', AMENT_PREFIX_PATH='/opt/ros/jazzy')
    paths = [str(p) for pattern in (
        'omni.sensors.nv.common-*/bin/checker_lib/bin', 'omni.sensors.nv.common-*/bin',
        'omni.sensors.nv.lidar-*/bin/model_plugins') for p in (install/'extscache').glob(pattern)]
    paths += [str(install/p) for p in ('exts/isaacsim.ros2.core/bin', 'kit/python/lib',
        'kit', 'kit/kernel/plugins', 'exts/isaacsim.ros2.core/jazzy/lib', 'kit/plugins/rtx')]
    paths.append('/opt/ros/jazzy/lib')
    env['LD_LIBRARY_PATH'] = ':'.join(paths)
    args = [str(kit), str(experience), '--allow-root', '--/renderer/multiGpu/enabled=false',
        '--/persistent/app/newStage/defaultTemplate=empty',
        '--/app/settings/persistent=false',
        '--/app/asyncRendering=false', '--/exts/isaacsim.core.throttling/enable_async=false',
        '--/app/renderer/skipWhileMinimized=false',
        '--/renderer/raytracingMotion/enabled=false', '--/rtx/hydra/supportMultiTickRate=false',
        '--/rtx/rendering/perSensorTickTlas=false', *sys.argv[1:]]
    os.chdir(install)
    os.execve(str(kit), args, env)


if __name__ == '__main__':
    launch()
