import json
import os
from pathlib import Path
import subprocess

blender = '/opt/blender/blender'
env = dict(os.environ)
for key in ['LD_PRELOAD','LD_LIBRARY_PATH','PYTHONPATH','PYTHONHOME','VIRTUAL_ENV','CONDA_PREFIX']:
    env.pop(key, None)
env['LD_LIBRARY_PATH'] = '/opt/blender/lib'
r = subprocess.run([blender, '--background', '--factory-startup', '--disable-autoexec',
                    '--python-expr', "import bpy,json; print('BLENDER_INFO='+json.dumps({'version':bpy.app.version_string,'usd_export':hasattr(bpy.ops.wm,'usd_export')}))"],
                   capture_output=True, text=True, timeout=25, env=env)
print(json.dumps({'exit_code':r.returncode,'stdout':r.stdout[-3000:],'stderr':r.stderr[-1000:],
                  'bundled_tbb':[str(p) for p in Path('/opt/blender/lib').glob('*tbb*')]}))
