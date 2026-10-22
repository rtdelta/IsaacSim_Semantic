"""Real repeat-task Pause/Resume/Stop/Drain validation, bounded to this project."""
import json
from pathlib import Path
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from single0602_headless.capture_supervisor import CaptureSupervisor
from single0602_headless.contracts import write_json

report_path=ROOT/'reports/capture_lifecycle.json'
report={'state':'starting','observations':[]}
output=Path('/root/gpufree-data/semantic/output/sensor_visualizer/single0602Headless')
supervisor=CaptureSupervisor(ROOT,output,output/'runtime/engine.sock')
task=None

def observe(predicate,timeout=150):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        row=next(x for x in supervisor.status() if x['task_id']==task['task_id'])
        if row['state']=='failed':raise RuntimeError(row)
        if predicate(row):return row
        time.sleep(.1)
    raise TimeoutError('Task lifecycle condition did not arrive')

try:
    previous=ROOT/'reports/capture_lifecycle.json'
    if previous.exists():
        history=ROOT/'reports/history';history.mkdir(exist_ok=True)
        (history/('capture_lifecycle_'+str(time.time_ns())+'.json')).write_bytes(previous.read_bytes())
    gui=json.loads((ROOT/'reports/gui_input.json').read_text());assert gui['state']=='passed'
    gui_process=json.loads((ROOT/'reports/gui_process.json').read_text())
    cmdline=Path('/proc',str(gui_process['pid']),'cmdline')
    assert not cmdline.exists() or gui_process['entry'].encode() not in cmdline.read_bytes()
    trajectory=gui['trajectory'];report['source_gui_exited']=True
    task=supervisor.start({'mode':'offline','trajectory':trajectory,'groups':5,'sample_hz':10,'ros_preview':False})
    report.update(state='running',task=task);write_json(report_path,report)
    first=observe(lambda row:row.get('groups',0)>=1)
    supervisor.control(task['task_id'],'pause')
    paused=observe(lambda row:row['state']=='paused')
    time.sleep(.6)
    stable=next(x for x in supervisor.status() if x['task_id']==task['task_id'])
    assert stable['groups']==paused['groups'] and stable['state']=='paused'
    report['observations'].append({'action':'pause','groups':stable['groups'],'stable_wall_s':.6})
    supervisor.control(task['task_id'],'run')
    resumed=observe(lambda row:row['groups']>paused['groups'])
    report['observations'].append({'action':'resume','groups':resumed['groups']})
    supervisor.control(task['task_id'],'stop')
    stopped=observe(lambda row:row['process_exited'] and row['resource_lock_released'])
    assert stopped['stopped'] and stopped['record_drain_complete'] and stopped['groups']>=2
    report.update(state='passed',terminal=stopped)
except Exception:
    report.update(state='failed',error=traceback.format_exc());traceback.print_exc()
finally:
    write_json(report_path,report)
