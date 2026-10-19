"""Run one owned Kit test, recording process exit separately from the test result."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from run_capture import launch_spec
from single0602_headless.contracts import write_json

parser = argparse.ArgumentParser()
parser.add_argument('entry')
parser.add_argument('tag')
parser.add_argument('--gui', action='store_true')
parser.add_argument('--timeout', type=float, default=180)
args = parser.parse_args()
entry = (ROOT/args.entry).resolve()
assert entry.is_relative_to(ROOT) and entry.is_file()
assert args.tag.replace('_', '').isalnum()
path = ROOT/'reports'/(args.tag+'_process.json')
if path.exists():
    backup=ROOT/'reports/test_attempts'/(args.tag+'_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    backup.mkdir(parents=True,exist_ok=False)
    for name in (args.tag+'.json',args.tag+'_process.json',args.tag+'.log'):
        source=ROOT/'reports'/name
        if source.is_file():(backup/name).write_bytes(source.read_bytes())
report = {'state': 'starting', 'entry': str(entry)}
write_json(path, report)
process = None
try:
    command, env, cwd = launch_spec(ROOT/'config/interactive.json', args.gui, entry, interactive_clock=True)
    env['S0602_TEST_TAG']=args.tag
    if args.gui:
        env['DISPLAY'] = ':20'
        if Path('/root/.Xauthority').is_file():
            env['XAUTHORITY'] = '/root/.Xauthority'
    with (ROOT/'reports'/(args.tag+'.log')).open('wb') as log:
        process = subprocess.Popen(command, env=env, cwd=cwd, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT)
        report.update(state='running', pid=process.pid)
        write_json(path, report)
        code = process.wait(timeout=args.timeout)
    report.update(state='exited', exit_code=code)
except subprocess.TimeoutExpired:
    process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill(); process.wait(timeout=10)
    report.update(state='timeout', exit_code=process.returncode)
except Exception:
    report.update(state='failed', error=traceback.format_exc())
write_json(path, report)
