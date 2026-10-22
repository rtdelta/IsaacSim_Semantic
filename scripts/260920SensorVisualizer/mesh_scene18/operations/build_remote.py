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

p=run(Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/mesh_scene18/build_assets.py').read_text(), timeout=180);print(p.stdout);print(p.stderr);raise SystemExit(p.returncode)
