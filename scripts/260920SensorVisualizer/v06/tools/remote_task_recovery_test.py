import json,sys,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06');sys.path.insert(0,str(root))
from sensor_visualizer_v06.capture_supervisor import CaptureSupervisor
track=json.loads((root/'reports/native_owner/soak_task.json').read_text());owner=json.loads((root/'reports/native_owner/owner.json').read_text())
s=CaptureSupervisor(root,'/root/gpufree-data/semantic/output/sensor_visualizer/v06',owner['socket'])
t=next(x for x in s.status() if x['task_id']==track['task_id']);assert t['running'] and not t['exit_code_known']
try:s.start({'mode':'offline','trajectory':json.loads((root/'reports/native_owner/soak_status.json').read_text())['trajectory']})
except ValueError:pass
else:raise AssertionError('Recovered task did not block duplicate capture')
s.control(track['task_id'],'pause');end=time.monotonic()+45
while time.monotonic()<end:
    t=next(x for x in s.status() if x['task_id']==track['task_id'])
    if t['state']=='paused':break
    time.sleep(.1)
else:
    s.control(track['task_id'],'run');raise TimeoutError('Boundary pause timeout')
groups=t['groups'];time.sleep(.5);assert next(x for x in s.status() if x['task_id']==track['task_id'])['groups']==groups
s.control(track['task_id'],'run')
report={'passed':True,'task':track['task_id'],'pause_boundary_group':groups,'recovered_active_task':True,'duplicate_blocked':True}
(root/'reports/native_owner/task_recovery.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
