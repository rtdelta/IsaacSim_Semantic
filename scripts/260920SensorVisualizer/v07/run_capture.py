"""Run with system Python; all Isaac imports happen inside the launched Kit."""
import argparse
import os
from pathlib import Path


def launch_spec(job_path, gui=False, entry=None, extra=(), role=None, gpu=None):
    """Sanitize before a profiler injects its own libraries into the direct Kit child."""
    root = Path(__file__).resolve().parent
    from sensor_visualizer_v07.contracts import load_job
    job_path = Path(job_path).resolve()
    job=load_job(job_path)
    role=role or ('interactive' if entry and 'interactive' in str(entry) else 'formal_capture')
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
               AMENT_PREFIX_PATH='/opt/ros/jazzy',SV07_JOB=str(job_path),SV07_ROLE=role,PYTHONUNBUFFERED='1')
    from sensor_visualizer_v07.cpu_budget import launch_budget
    from sensor_visualizer_v07.launch_profiles import renderer_flags
    from sensor_visualizer_v07.device_binding import resolve_device,cuda_inventory,resolve_cuda_ordinal
    import json
    cpu_flags,cpu_env,budget=launch_budget(role,job['runtime']);env.update(cpu_env)
    chosen=resolve_device(gpu or job['runtime']['interactive_gpu' if role=='interactive' else 'capture_gpu'])
    cuda=cuda_inventory();physics_ordinal=resolve_cuda_ordinal(chosen,cuda)
    env['SV07_DEVICE']=json.dumps(chosen);env['SV07_CPU_BUDGET']=json.dumps(budget)
    launch_record={'role':role,'device_requested':chosen,'cuda_roster':cuda,'physics_cuda_ordinal':physics_ordinal,
                   'cpu_budget':budget,'job':str(job_path)}
    from sensor_visualizer_v07.contracts import write_json
    from datetime import datetime
    launch_dir=Path(job['output_directory'])/'launches'
    launch_id=datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+str(os.getpid())
    launch_record['native_log']=str(launch_dir/(launch_id+'.kit.log'))
    import subprocess,sys
    ticks=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]
    monitor_dir=launch_dir/(launch_id+'_resources')
    monitor=subprocess.Popen([sys.executable,str(root/'tools/launch_resource_monitor.py'),
        '--pid',str(os.getpid()),'--ticks',ticks,'--directory',str(monitor_dir),'--role',role],
        stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    launch_record.update(resource_monitor_pid=monitor.pid,resource_monitor_directory=str(monitor_dir))
    write_json(launch_dir/(launch_id+'.json'),launch_record)
    print('SV07 launch '+json.dumps(launch_record),flush=True)
    paths = [str(p) for pattern in ('omni.sensors.nv.common-*/bin/checker_lib/bin','omni.sensors.nv.common-*/bin',
             'omni.sensors.nv.lidar-*/bin/model_plugins') for p in (install/'extscache').glob(pattern)]
    paths += [str(install/p) for p in ('exts/isaacsim.ros2.core/bin','kit/python/lib','kit',
        'kit/kernel/plugins','exts/isaacsim.ros2.core/jazzy/lib','kit/plugins/rtx')]
    env['LD_LIBRARY_PATH']=':'.join(paths+['/opt/ros/jazzy/lib'])
    command=[str(kit),str(experience),'--allow-root','--/renderer/multiGpu/enabled=false',
        '--/persistent/app/newStage/defaultTemplate=empty','--/app/settings/persistent=false',
        '--/app/extensions/registryEnabled=false','--/app/extensions/syncRegistryOnStartup=false',
        '--/app/renderer/skipWhileMinimized=false','--/renderer/raytracingMotion/enabled=false',
        '--/rtx/hydra/supportMultiTickRate=false','--/rtx/rendering/perSensorTickTlas=false',
        '--/persistent/app/usd/muteUsdDiagnostics=false',
        '--/exts/omni.services.transport.server.http/http/enabled=false',
        '--/exts/omni.services.transport.server.http/https/enabled=false',
        '--/crashreporter/enabled=false','--/crashreporter/skipOldDumpUpload=true',
        '--/crashreporter/url=','--/telemetry/enableAnonymousData=false',
        '--enable','isaacsim.sensors.rtx.nodes']
    command+=cpu_flags+renderer_flags(role,job['runtime'])
    command+=['--/log/file='+launch_record['native_log']]
    command+=['--/renderer/activeGpu='+str(chosen['index']),'--/physics/cudaDevice='+str(physics_ordinal)]
    if not gui:
        command += ['--no-window','--/app/window/enabled=false','--/app/fastShutdown=true',
                    '--/app/file/ignoreUnsavedOnExit=true','--exec',str(Path(entry).resolve() if entry else root/'kit_entry.py')]
    elif entry:
        command+=['--exec',str(Path(entry).resolve())]
    return command+list(extra),env,install


def launch():
    parser = argparse.ArgumentParser()
    parser.add_argument('--job', default=str(Path(__file__).parent/'config/offline.json'))
    parser.add_argument('--gui', action='store_true', help='Open the v07 GUI without starting a job')
    parser.add_argument('--entry', help='Task-owned headless experiment entry (advanced)')
    parser.add_argument('--interactive',action='store_true',help='Start the independent interactive owner and viewport')
    parser.add_argument('--headless-owner',action='store_true',help='Owner integration tests without a window')
    parser.add_argument('--gpu',help='Explicit renderer GPU UUID or index; validated with nvidia-smi')
    parser.add_argument('--service',action='store_true',help='Run the resident formal capture service')
    args, extra = parser.parse_known_args()
    if args.interactive or args.headless_owner:
        args.entry=str(Path(__file__).parent/'kit_interactive_entry.py')
        args.gui=not args.headless_owner
    if args.service:args.entry=str(Path(__file__).parent/'kit_service_entry.py')
    role='interactive' if args.interactive or args.headless_owner else 'formal_capture'
    command,env,install=launch_spec(args.job,args.gui,args.entry,extra,role,args.gpu)
    os.chdir(install)
    os.execve(command[0],command,env)


if __name__=='__main__': launch()
