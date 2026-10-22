"""Edit LABEL/VERSION/NATIVE per reviewed experiment; no other projects touched."""
from pathlib import Path
import datetime,json,os,subprocess
ROOT=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v04')
LABEL=globals().get('LABEL','baseline_v03');VERSION=globals().get('VERSION','v03')
NATIVE=globals().get('NATIVE',False);GROUPS=globals().get('GROUPS',8)
for p in Path('/proc').glob('[0-9]*/cmdline'):
    try:
        args=p.read_bytes().split(b'\0')
        if args and (args[0].endswith(b'/kit/kit') or any(b'record_worker.py' in a or b'/experiments/supervise.py' in a for a in args)):
            raise RuntimeError('Existing application PID '+p.parent.name)
    except OSError:pass
out=Path('/root/gpufree-data/semantic/output/sensor_visualizer/v04/experiments')/(datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+LABEL)
out.mkdir(parents=True,exist_ok=False)
job={'schema_version':3,'mode':'offline','groups':GROUPS,'output_directory':str(out/'captures'),
     'motion':{'joints':{'boom':{'mode':'target','target':4,'speed':2}},
               'tilt':{'roll':{'mode':'target','target':2,'speed':2}},'base':{'speed_m_s':.05,'yaw_rate_deg_s':1}},
     'diagnostics':{'level':'diagnostic','export_trace_on_stop':True}}
(out/'job.json').write_text(json.dumps(job,indent=2))
spec={'out':str(out),'job':str(out/'job.json'),'version':VERSION,'native':NATIVE,'profile_first':1,'profile_last':3,'timeout_s':600,'label':LABEL}
spec.update(globals().get('SPEC_EXTRA',{}))
job.update(globals().get('JOB_EXTRA',{}))
(out/'job.json').write_text(json.dumps(job,indent=2))
(out/'spec.json').write_text(json.dumps(spec,indent=2))
with (out/'supervisor.log').open('wb') as log:
    child=subprocess.Popen(['/usr/bin/python3','-I','-S','-B',str(ROOT/'experiments/supervise.py'),str(out/'spec.json')],cwd=ROOT,
        stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
(ROOT/'reports').mkdir(exist_ok=True)
(ROOT/'reports/latest_experiment.json').write_text(json.dumps({'directory':str(out),'supervisor_pid':child.pid,'label':LABEL},indent=2))
print(json.dumps({'directory':str(out),'supervisor_pid':child.pid,'label':LABEL}))
