"""Create an isolated CET200 deployment and fetch its upstream source."""
import json
import subprocess
from pathlib import Path

ROOT = Path('/root/gpufree-data/IsaacSim_Asset/excavator_module_set/CET200')
ROOT.mkdir(exist_ok=False)
for name in ('usd', 'tools', 'reports'):
    (ROOT / name).mkdir()
with (ROOT / 'reports/download.log').open('w') as log:
    proc = subprocess.Popen(
        ['timeout', '300', 'git', 'clone', '--depth', '1',
         'https://github.com/vmc-motion/cet200.git', str(ROOT / 'source')],
        stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
print(json.dumps({'root': str(ROOT), 'download_pid': proc.pid}))
install = Path('/root/isaacsim')
for pattern in ('exts/*urdf*', 'extscache/*urdf*', 'exts/*asset*converter*',
                'kit/exts/*asset*converter*', 'kit/python/bin/python3*'):
    print('INSTALL', pattern, [str(p) for p in install.glob(pattern)])
for name in ('VERSION', 'python.sh', 'setup_python_env.sh'):
    p = install / name
    if p.exists():
        print('FILE', str(p), p.read_text()[:6000])
