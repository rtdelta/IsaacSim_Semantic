"""Launch existing USD Python without Kit or downloaded dependencies."""
import os
import subprocess
from pathlib import Path


def run(source, timeout=120):
    install = Path('/root/isaacsim')
    sdk = sorted((install/'extscache').glob('omni.usd.libs-*/pxr'))[-1].parent
    env = os.environ.copy()
    for key in ('PYTHONHOME','PYTHONPATH','LD_PRELOAD','LD_LIBRARY_PATH','VIRTUAL_ENV','CONDA_PREFIX'):
        env.pop(key, None)
    env['LD_LIBRARY_PATH'] = ':'.join(map(str, (install/'kit/python/lib', install/'kit', sdk/'bin', sdk/'lib')))
    bootstrap = '''import sys
from pathlib import Path
sys.path.insert(0, {sdk!r})
for folder in [Path('/root/isaacsim/kit/python/lib/python3.12/site-packages'), *sorted(Path('/root/isaacsim/extscache').glob('omni.kit.pip_archive-*/pip_prebundle'))]:
    if folder.is_dir():sys.path.append(str(folder))
'''.format(sdk=str(sdk))
    completed = subprocess.run([str(install/'kit/python/bin/python3'), '-I','-S','-B','-'],
                               input=bootstrap+'\n'+source, env=env, text=True,
                               capture_output=True, timeout=timeout)
    return completed

import json,time
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_scene18_capture_005')
out=Path('/root/gpufree-data/semantic/output/native_scene18_capture_005')/('capture_'+time.strftime('%Y%m%d_%H%M%S',time.gmtime()))
source="import runpy,sys\nsys.argv=['prepare.py','--output',OUT]\nrunpy.run_path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_scene18_capture_005/prepare.py',run_name='__main__')\n".replace('OUT',repr(str(out)))
r=run(source,timeout=90)
if r.returncode:print(r.stdout);print(r.stderr);raise SystemExit(r.returncode)
reports=root/'reports';reports.mkdir(exist_ok=True)
with (out/'smoke_supervisor.log').open('xb') as log:
 p=subprocess.Popen(['/usr/bin/python3','-u',str(root/'run.py'),'--config',str(out/'smoke/job.json'),'--output',str(out/'smoke/capture')],cwd=root,stdout=log,stderr=log,stdin=subprocess.DEVNULL,start_new_session=True)
info={'directory':str(out),'smoke_pid':p.pid,'phase':'smoke'}
(reports/'latest.json').write_text(json.dumps(info,indent=2));print(json.dumps({'started':info,'preparation':json.loads(r.stdout)}))
