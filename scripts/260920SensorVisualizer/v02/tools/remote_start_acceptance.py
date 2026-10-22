from pathlib import Path
import json
import subprocess
import time
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v02')
previous=json.loads((root/'reports/capture_process.json').read_text())
p=Path('/proc')/str(previous['pid'])/'cmdline'
if p.exists() and 'kit_entry.py' in p.read_bytes().decode(errors='replace'): raise RuntimeError('v02 still running')
probe=json.loads((root/'reports/probe_capture.json').read_text())['initial_state']
angles=dict(zip(('swing','boom','arm','bucket'),[v*180/3.141592653589793 for v in probe['positions']]))
x,y,z=probe['root_position']
job={'schema_version':2,'mode':'offline','groups':12,'pipeline':{'segment_groups':5},
 'motion':{'joints':{'boom':{'mode':'direct','target':angles['boom']+1}},'tilt':{'pitch':{'mode':'direct','target':1},'roll':{'mode':'direct','target':-1}},
           'base':{'x':x+.1,'y':y,'z':z+.15,'yaw_deg':5}},
 'events':[{'group':2,'motion':{'joints':{'boom':{'mode':'target','target':angles['boom']+1.5,'speed':2},
   'arm':{'mode':'periodic','lower':angles['arm']-1,'upper':angles['arm']+1,'speed':3}},
   'tilt':{'roll':{'mode':'periodic','lower':-1,'upper':1,'speed':3}},'base':{'speed_m_s':.02,'yaw_rate_deg_s':1}}}]}
jobpath=root/'reports/acceptance_job.json'; jobpath.write_text(json.dumps(job,indent=2))
logpath=root/f'reports/acceptance_{time.time_ns()}.log'
with logpath.open('ab') as log:
    proc=subprocess.Popen(['/usr/bin/python3',str(root/'run_capture.py'),'--job',str(jobpath)],cwd=root,
         stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
row={'pid':proc.pid,'log':str(logpath),'job':str(jobpath)}
(root/'reports/capture_process.json').write_text(json.dumps(row))
print(json.dumps(row))
