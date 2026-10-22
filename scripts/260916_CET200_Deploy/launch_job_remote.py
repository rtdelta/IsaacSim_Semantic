"""Receive job payloads through a generated wrapper; start a bounded native Kit job."""
import json
import os
from pathlib import Path
import subprocess

ROOT = Path('/root/gpufree-data/IsaacSim_Asset/excavator_module_set/CET200')
JOB_NAME = os.environ.get('CET200_JOB', 'build_cet200')
LAUNCHER = Path('/root/gpufree-data/semantic/scripts/260907LidarVisualizer/launch_isaac.py')
log_path = ROOT / 'reports' / (JOB_NAME + '.log')
with log_path.open('w') as log:
    proc = subprocess.Popen([
        'timeout', '--signal=TERM', '--kill-after=15', '300', 'python3', str(LAUNCHER),
        '--no-window', '--/app/window/enabled=false', '--/app/viewport/defaults/visible=true',
        '--/app/settings/persistent=false', '--/app/file/ignoreUnsavedStage=true',
        '--/log/file=' + str(ROOT / 'reports' / (JOB_NAME + '_kit.log')),
        '--exec', str(ROOT / 'tools' / (JOB_NAME + '.py'))],
        cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
print(json.dumps({'job': JOB_NAME, 'pid': proc.pid, 'log': str(log_path)}))
