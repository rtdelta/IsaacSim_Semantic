"""Run with system Python; all Isaac imports happen inside the launched Kit."""
import argparse
import os
from pathlib import Path


def launch_spec(job_path, gui=False, entry=None, extra=(), interactive_clock=False):
    """Sanitize before a profiler injects its own libraries into the direct Kit child."""
    root = Path(__file__).resolve().parent
    from single0602_headless.contracts import load_job
    job_path = Path(job_path).resolve()
    if not gui: load_job(job_path)
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
               AMENT_PREFIX_PATH='/opt/ros/jazzy',S0602_JOB=str(job_path),PYTHONUNBUFFERED='1')
    paths = [str(p) for pattern in ('omni.sensors.nv.common-*/bin/checker_lib/bin','omni.sensors.nv.common-*/bin',
             'omni.sensors.nv.lidar-*/bin/model_plugins') for p in (install/'extscache').glob(pattern)]
    paths += [str(install/p) for p in ('exts/isaacsim.ros2.core/bin','kit/python/lib','kit',
        'kit/kernel/plugins','exts/isaacsim.ros2.core/jazzy/lib','kit/plugins/rtx')]
    env['LD_LIBRARY_PATH']=':'.join(paths+['/opt/ros/jazzy/lib'])
    command=[str(kit),str(experience),'--allow-root','--/renderer/multiGpu/enabled=false',
        '--/persistent/app/newStage/defaultTemplate=empty','--/app/settings/persistent=false',
        '--/app/fastShutdown=true','--/app/file/ignoreUnsavedOnExit=true',
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
    if interactive_clock:
        command+=['--/app/runLoops/main/manualModeEnabled=false','--/app/player/useFixedTimeStepping=false',
                  '--/exts/isaacsim.core.throttling/enable_manualmode=false']
    if not gui:
        command += ['--no-window','--/app/window/enabled=false','--/app/fastShutdown=true',
                    '--/app/file/ignoreUnsavedOnExit=true','--exec',str(Path(entry).resolve() if entry else root/'kit_replay_entry.py')]
    elif entry:
        command+=['--exec',str(Path(entry).resolve())]
    return command+list(extra),env,install


def launch():
    parser = argparse.ArgumentParser()
    parser.add_argument('--trajectory',help='Launch independent offline capture from a completed trajectory')
    parser.add_argument('--output',default='/root/gpufree-data/semantic/output/sensor_visualizer/single0602Headless')
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument('--groups',type=int,help='Maximum capture groups (legacy default: 100)')
    scope.add_argument('--all-trajectory',action='store_true',help='Capture every valid sample grid in the completed trajectory')
    parser.add_argument('--sample-hz',type=float,default=10)
    parser.add_argument('--job', default=str(Path(__file__).parent/'config/offline.json'))
    parser.add_argument('--gui', action='store_true', help='Open the v06 GUI without starting a job')
    parser.add_argument('--entry', help='Task-owned headless experiment entry (advanced)')
    parser.add_argument('--interactive',action='store_true',help='Start the independent interactive owner and viewport')
    parser.add_argument('--headless-owner',action='store_true',help='Owner integration tests without a window')
    parser.add_argument('--gpu',help='Explicit renderer GPU UUID or index; validated with nvidia-smi')
    args, extra = parser.parse_known_args()
    if args.trajectory:
        import json
        from single0602_headless.capture_supervisor import CaptureSupervisor
        payload={'mode':'offline','trajectory':args.trajectory,'sample_hz':args.sample_hz,'gpu':args.gpu,
                 'capture_scope':'full_trajectory' if args.all_trajectory else 'group_limit'}
        if not args.all_trajectory:payload['groups']=args.groups if args.groups is not None else 100
        result=CaptureSupervisor(Path(__file__).parent,args.output,Path(args.output)/'runtime/engine.sock').start(payload)
        print(json.dumps(result,indent=2));return
    if args.all_trajectory:parser.error('--all-trajectory requires --trajectory')
    if not (args.gui or args.interactive or args.headless_owner):
        from single0602_headless.contracts import load_job
        if not load_job(args.job).get('replay'):
            raise SystemExit('Provide --trajectory <completed directory>, or a snapshotted task --job file')
    if args.gpu:
        from single0602_headless.gpu_config import resolve_gpu
        device=resolve_gpu(args.gpu)
        extra+=['--/renderer/activeGpu='+str(device['index']),'--/physics/cudaDevice='+str(device['index'])]
        print('S0602 requested GPU: '+str(device),flush=True)
    if args.interactive or args.headless_owner:
        args.entry=str(Path(__file__).parent/'kit_interactive_entry.py')
        args.gui=not args.headless_owner
    command,env,install=launch_spec(args.job,args.gui,args.entry,extra,interactive_clock=args.interactive or args.headless_owner)
    os.chdir(install)
    os.execve(command[0],command,env)


if __name__=='__main__': launch()
