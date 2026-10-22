"""Start only this bounded v02 headless probe; leave existing GUI untouched."""
from pathlib import Path
import json
import os
import subprocess
root = Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v02')
reports = root/'reports'
reports.mkdir(exist_ok=True)
pidfile = reports/'probe_process.json'
if pidfile.exists():
    prior = json.loads(pidfile.read_text())
    proc = Path('/proc')/str(prior['pid'])
    if proc.exists() and 'probe_capture.py' in (proc/'cmdline').read_bytes().decode(errors='replace'):
        raise RuntimeError('Probe already running')
log = (reports/'probe_kit.log').open('ab')
if (reports/'probe_capture.json').exists():
    import time
    (reports/'probe_capture.json').rename(reports/f'probe_capture_{time.time_ns()}.json')
args = ['/usr/bin/python3', str(root.parent/'launch_isaac.py'), '--no-window', '--/app/window/enabled=false',
        '--/app/fastShutdown=true', '--/app/file/ignoreUnsavedOnExit=true',
        '--/app/extensions/registryEnabled=false', '--/app/extensions/syncRegistryOnStartup=false',
        '--exec', str(root/'tools/probe_capture.py')]
env = os.environ.copy()
env['PYTHONUNBUFFERED'] = '1'
process = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                           cwd=str(root), env=env, start_new_session=True)
log.close()
result = {'pid': process.pid, 'log': str(reports/'probe_kit.log'), 'report': str(reports/'probe_capture.json')}
pidfile.write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result))
