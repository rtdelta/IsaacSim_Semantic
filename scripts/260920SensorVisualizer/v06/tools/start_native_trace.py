"""Use the existing nsys; sanitize before it injects its process-local profiler."""
import json,os,subprocess,sys,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06');sys.path.insert(0,str(root))
from run_capture import launch_spec
from sensor_visualizer_v06.contracts import load_job,write_json
baseline=json.loads((root/'reports/baseline_performance_suite.json').read_text());source=Path(baseline['directory'])/'input_trajectory'
for p in Path('/proc').glob('[0-9]*/cmdline'):
    try:raw=p.read_bytes()
    except OSError:continue
    if b'/kit/kit' in raw:raise RuntimeError('Wait for isolated benchmark before native tracing')
out=Path('/root/gpufree-data/semantic/output/sensor_visualizer/v06/native_trace')/str(time.time_ns());out.mkdir(parents=True)
job=load_job(overrides={'groups':3,'output_directory':str(out/'captures'),
    'diagnostics':{'level':'diagnostic','native_profiler':'nvtx','detail_group_range':[1,1],'export_trace_on_stop':True},
    'replay':{'mode':'offline','trajectory':str(source),'socket':'unused','control_path':str(out/'control.json'),'status_path':str(out/'status.json')}})
write_json(out/'job.json',job);write_json(out/'control.json',{'action':'run'})
command,env,cwd=launch_spec(out/'job.json',entry=root/'tools/native_capture_entry.py');env['NSYS_NVTX_PROFILER_REGISTER_ONLY']='0'
nsys='/opt/nvidia/nsight-compute/2025.1.1/host/target-linux-x64/nsys'
command=[nsys,'profile','--trace=vulkan,cuda,nvtx,osrt','--vulkan-gpu-workload=batch','--sample=process-tree',
    '--cpuctxsw=process-tree','--backtrace=lbr','--capture-range=nvtx','--nvtx-capture=SV06_PROFILE',
    '--capture-range-end=stop','--export=sqlite','--output='+str(out/'native')]+command
(out/'launch.json').write_text(json.dumps({'command':command,'cwd':str(cwd),'project':str(root)}))
os.chmod(out/'launch.json',0o600)
log=(out/'supervisor.log').open('ab');p=subprocess.Popen(['/usr/bin/python3',str(root/'tools/native_trace_supervisor.py'),str(out)],cwd=root,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);log.close()
row={'pid':p.pid,'directory':str(out),'start_ticks':Path('/proc',str(p.pid),'stat').read_text().rsplit(')',1)[1].split()[19]}
(root/'reports/latest_native_trace.json').write_text(json.dumps(row));print(json.dumps({k:v for k,v in row.items() if k!='command'}))
