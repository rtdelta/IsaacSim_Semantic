"""Embed reviewed local helpers for execution through the audited SSH CLI."""
import ast
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
resume = '--verify-existing' in sys.argv
files = {name: (root / name).read_text(encoding='utf-8')
         for name in ['verify_mcap_records.py', 'merge_and_verify.py']}
for source in files.values():
    ast.parse(source)
wrapper = '''import json, subprocess
from pathlib import Path
root = Path('/root/gpufree-data/semantic/scripts/261013Rviz2Viewer/mcap_ops')
root.mkdir(exist_ok=False)
files = FILES
for name, code in files.items():
    (root / name).write_text(code)
response = subprocess.run(['bash', '-c', 'source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 -B "$1"', 'mcap-merge', str(root / 'merge_and_verify.py')], capture_output=True, text=True, timeout=300)
print(json.dumps({'worker_exit_code': response.returncode, 'stdout': response.stdout, 'stderr': response.stderr}))
raise SystemExit(response.returncode)
'''.replace('FILES', repr(files))
ast.parse(wrapper)
if resume:
    wrapper = wrapper.replace('/261013Rviz2Viewer/mcap_ops\'', '/261013Rviz2Viewer/mcap_ops_validation\'')
    wrapper = wrapper.replace("str(root / 'merge_and_verify.py')],", "str(root / 'merge_and_verify.py'), '--verify-existing'],")
    wrapper = wrapper.replace('exec /usr/bin/python3 -B "$1"', 'exec /usr/bin/python3 -B "$@"')
    ast.parse(wrapper)
(root / ('run_verify_remote.py' if resume else 'run_merge_remote.py')).write_text(wrapper, encoding='utf-8')
print('Reviewed wrapper saved')
