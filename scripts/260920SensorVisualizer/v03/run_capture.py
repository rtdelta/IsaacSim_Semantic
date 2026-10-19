"""Run with system Python; all Isaac imports happen inside the launched Kit."""
import argparse
import os
from pathlib import Path


def launch():
    parser = argparse.ArgumentParser()
    parser.add_argument('--job', default=str(Path(__file__).parent/'config/offline.json'))
    parser.add_argument('--gui', action='store_true', help='Open the v03 GUI without starting a job')
    args, extra = parser.parse_known_args()
    root = Path(__file__).resolve().parent
    from sensor_visualizer_v03.contracts import load_job
    job_path = Path(args.job).resolve()
    if not args.gui: load_job(job_path)
    install = Path(os.environ.get('ISAACSIM_PATH','/root/isaacsim')).resolve()
    kit = install/'kit/kit'
    experience = install/'apps/isaacsim.exp.full.kit'
    if not kit.is_file(): raise SystemExit('Set ISAACSIM_PATH to installed Isaac Sim')
    import resource
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    resource.setrlimit(resource.RLIMIT_NOFILE,(min(max(soft,65536),hard),hard))
    env = os.environ.copy()
    for key in ('PYTHONHOME','PYTHONPATH','LD_PRELOAD','VIRTUAL_ENV','CONDA_PREFIX'): env.pop(key,None)
    env.update(RESOURCE_NAME='IsaacSim', ROS_DISTRO='jazzy',RMW_IMPLEMENTATION='rmw_fastrtps_cpp',
               AMENT_PREFIX_PATH='/opt/ros/jazzy',SV03_JOB=str(job_path),PYTHONUNBUFFERED='1')
    paths = [str(p) for pattern in ('omni.sensors.nv.common-*/bin/checker_lib/bin','omni.sensors.nv.common-*/bin',
             'omni.sensors.nv.lidar-*/bin/model_plugins') for p in (install/'extscache').glob(pattern)]
    paths += [str(install/p) for p in ('exts/isaacsim.ros2.core/bin','kit/python/lib','kit',
        'kit/kernel/plugins','exts/isaacsim.ros2.core/jazzy/lib','kit/plugins/rtx')]
    env['LD_LIBRARY_PATH']=':'.join(paths+['/opt/ros/jazzy/lib'])
    command=[str(kit),str(experience),'--allow-root','--/renderer/multiGpu/enabled=false',
        '--/persistent/app/newStage/defaultTemplate=empty','--/app/settings/persistent=false',
        '--/app/extensions/registryEnabled=false','--/app/extensions/syncRegistryOnStartup=false',
        '--/app/asyncRendering=false','--/exts/isaacsim.core.throttling/enable_async=false',
        '--/app/renderer/skipWhileMinimized=false','--/renderer/raytracingMotion/enabled=false',
        '--/rtx/hydra/supportMultiTickRate=false','--/rtx/rendering/perSensorTickTlas=false',
        '--/persistent/app/usd/muteUsdDiagnostics=false',
        '--/exts/omni.services.transport.server.http/http/enabled=false',
        '--/exts/omni.services.transport.server.http/https/enabled=false',
        '--/crashreporter/enabled=false','--/crashreporter/skipOldDumpUpload=true',
        '--/crashreporter/url=','--/telemetry/enableAnonymousData=false',
        '--enable','isaacsim.sensors.rtx.nodes']
    if not args.gui:
        command += ['--no-window','--/app/window/enabled=false','--/app/fastShutdown=true',
                    '--/app/file/ignoreUnsavedOnExit=true','--exec',str(root/'kit_entry.py')]
    os.chdir(install)
    os.execve(str(kit),command+extra,env)


if __name__=='__main__': launch()
