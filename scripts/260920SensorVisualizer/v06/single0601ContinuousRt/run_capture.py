"""Launch the single project-owned Isaac GUI using existing offline dependencies."""
import argparse
import os
from pathlib import Path
import resource
import time


def launch_spec(job, entry, headless=False, extra=()):
    install = Path(os.environ.get('ISAACSIM_PATH', '/root/isaacsim'))
    env = os.environ.copy()
    env['S0601_LAUNCH_MONOTONIC_NS']=str(time.monotonic_ns())
    for key in ('PYTHONHOME', 'PYTHONPATH', 'LD_PRELOAD', 'VIRTUAL_ENV', 'CONDA_PREFIX'):
        env.pop(key, None)
    env.update(RESOURCE_NAME='IsaacSim', ROS_DISTRO='jazzy', RMW_IMPLEMENTATION='rmw_fastrtps_cpp',
               AMENT_PREFIX_PATH='/opt/ros/jazzy', S0601_JOB=str(Path(job).resolve()), PYTHONUNBUFFERED='1')
    from single0601_continuous_rt.config import load
    barrier=os.environ.get('S0601_FORCE_BARRIER')=='1' or load(job)['capture']['backend']=='barrier'
    paths = [str(p) for pattern in ('omni.sensors.nv.common-*/bin/checker_lib/bin', 'omni.sensors.nv.common-*/bin',
             'omni.sensors.nv.lidar-*/bin/model_plugins') for p in (install/'extscache').glob(pattern)]
    paths += [str(install/p) for p in ('exts/isaacsim.ros2.core/bin', 'kit/python/lib', 'kit', 'kit/kernel/plugins',
             'exts/isaacsim.ros2.core/jazzy/lib', 'kit/plugins/rtx')]
    env['LD_LIBRARY_PATH'] = ':'.join(paths + ['/opt/ros/jazzy/lib'])
    command = [str(install/'kit/kit'), str(install/'apps/isaacsim.exp.full.kit'), '--allow-root',
        '--/renderer/multiGpu/enabled=false', '--/persistent/app/newStage/defaultTemplate=empty',
        '--/app/settings/persistent=false', '--/app/extensions/registryEnabled=false',
        '--/app/extensions/syncRegistryOnStartup=false', '--/app/asyncRendering=false',
        '--/exts/isaacsim.core.throttling/enable_async=false', '--/app/renderer/skipWhileMinimized=false',
        '--/rtx/hydra/supportMultiTickRate='+str(not barrier).lower(), '--/rtx/rendering/perSensorTickTlas='+str(not barrier).lower(),
        '--/renderer/raytracingMotion/enabled='+str(not barrier).lower(), '--/rtx/scenedb/maxHistoryTransformCount=64', '--/crashreporter/enabled=false',
        '--/crashreporter/skipOldDumpUpload=true', '--/crashreporter/url=',
        '--/telemetry/enableAnonymousData=false', '--/exts/omni.services.transport.server.http/http/enabled=false',
        '--enable', 'isaacsim.sensors.rtx.nodes', '--enable', 'isaacsim.core.rendering_manager',
        '--exec', str(Path(entry).resolve())]
    if Path(entry).name=='probe_native_events.py':
        motion_history=os.environ.get('S0601_NATIVE_MOTION_HISTORY','default')
        if motion_history not in ('default','off'):raise ValueError('Unknown native diagnostic motion history mode')
        if motion_history=='off':command+=['--/renderer/raytracingMotion/enabled=false']
        tlas=os.environ.get('S0601_NATIVE_TLAS','sensor')
        if tlas not in ('sensor','frame'):raise ValueError('Unknown native diagnostic TLAS mode')
        if tlas=='frame':command+=['--/rtx/rendering/perSensorTickTlas=false']
        sync=os.environ.get('S0601_RECOVERY_SYNC','default')
        if sync not in ('default','zero_delay'):
            raise ValueError('Unknown native diagnostic completion profile')
        if sync=='zero_delay':
            command+=['--/app/hydraEngine/waitIdle=true','--/app/updateOrder/checkForHydraRenderComplete=1000']
    if headless:
        command += ['--no-window', '--/app/window/enabled=false']
    return command + list(extra), env, install


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--job', default=str(Path(__file__).parent/'config/strict_scene18.json'))
    parser.add_argument('--probe', action='store_true')
    parser.add_argument('--barrier-probe', action='store_true')
    parser.add_argument('--native-probe', action='store_true', help='Bounded C1/C2 event trace, no formal READY')
    parser.add_argument('--headless', action='store_true', help='Explicit diagnostic run; GUI acceptance is separate')
    args, extra = parser.parse_known_args()
    from single0601_continuous_rt.config import load
    load(args.job)
    entry = Path(__file__).parent / ('tools/probe_native_events.py' if args.native_probe else ('tools/probe_barrier.py' if args.barrier_probe else ('tools/probe_capabilities.py' if args.probe else 'run_in_isaac.py')))
    command, env, install = launch_spec(args.job, entry, args.headless, extra)
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    resource.setrlimit(resource.RLIMIT_NOFILE, (min(max(soft, 65536), hard), hard))
    os.chdir(install)
    os.execve(command[0], command, env)
