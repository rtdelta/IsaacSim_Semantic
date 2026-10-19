import collections
import json
import os
from pathlib import Path
import shlex
import subprocess

root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
report=root/'reports/tilt_terrain'
validation=json.loads((report/'validation.json').read_text())
if not validation['passed']:raise ValueError('Isaac acceptance did not pass')
env=dict(os.environ)
for key in ['LD_PRELOAD','LD_LIBRARY_PATH','PYTHONPATH','PYTHONHOME','VIRTUAL_ENV','CONDA_PREFIX']:
    env.pop(key,None)
args=['/usr/bin/python3','-B',str(root/'tools/inspect_tilt_recording.py'),validation['recording'],
      '--output',str(report/'recording_check.json')]
r=subprocess.run(['/bin/bash','-c','source /opt/ros/jazzy/setup.bash && exec '+shlex.join(args)],
                 env=env,capture_output=True,text=True,timeout=50)
(report/'recording_check.log').write_text(r.stdout+'\n'+r.stderr)
lines=(report/'kit.log').read_text(errors='replace').splitlines()
errors=[s for s in lines if '[Error]' in s or 'Traceback (most recent call last)' in s]
warnings=collections.Counter()
for line in lines:
    if '[Warning]' in line:warnings[line.split('[Warning]',1)[1].strip()]+=1
summary={'errors':errors[:30],'error_count':len(errors),'warning_count':sum(warnings.values()),
         'warnings':[{'message':m,'count':n} for m,n in warnings.most_common(12)]}
(report/'log_summary.json').write_text(json.dumps(summary,indent=2))
print(json.dumps({'exit_code':r.returncode,'stdout':r.stdout[-15000:],'stderr':r.stderr[-1000:],'logs':summary}))
raise SystemExit(r.returncode)
