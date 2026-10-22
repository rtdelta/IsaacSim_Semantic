"""Confirm native process exit separately from the GUI controller's close report."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from run_capture import launch_spec
from single0602_headless.contracts import write_json
report={'state':'running'};path=ROOT/'reports/gui_shutdown.json';write_json(path,report)
try:
    command,env,cwd=launch_spec(ROOT/'config/interactive.json',True,ROOT/'tools/gui_shutdown_entry.py')
    env['DISPLAY']=':20'
    if Path('/root/.Xauthority').is_file():env['XAUTHORITY']='/root/.Xauthority'
    with (ROOT/'reports/gui_shutdown.log').open('ab') as log:
        process=subprocess.Popen(command,env=env,cwd=cwd,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
        report.update(pid=process.pid);write_json(path,report)
        code=process.wait(timeout=75)
    assert code==0,code
    report.update(state='passed',exit_code=code,process_exited=True,
        socket_closed=not Path('/root/gpufree-data/semantic/output/sensor_visualizer/single0602Headless/runtime/engine.sock').exists())
except Exception:report.update(state='failed',error=traceback.format_exc())
write_json(path,report)
