import json,subprocess,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06')
spec=globals().get('SPEC',{'version':'v05','groups':8,'interactive_seconds':45})
for p in Path('/proc').glob('[0-9]*/cmdline'):
    try:raw=p.read_bytes()
    except OSError:continue
    if b'/kit/kit' in raw:raise RuntimeError('Preserve existing Kit; postpone controlled benchmark')
out=Path('/root/gpufree-data/semantic/output/sensor_visualizer/v06/benchmarks')/(str(time.time_ns())+'_'+spec['version'])
out.mkdir(parents=True);spec['directory']=str(out);(out/'spec.json').write_text(json.dumps(spec,indent=2))
log=(out/'supervisor.log').open('ab')
p=subprocess.Popen(['/usr/bin/python3',str(root/'tools/performance_suite.py'),str(out/'spec.json')],cwd=root,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);log.close()
report={'pid':p.pid,'directory':str(out),'version':spec['version']}
(root/'reports').mkdir(exist_ok=True);(root/'reports/latest_performance_suite.json').write_text(json.dumps(report))
print(json.dumps(report))
