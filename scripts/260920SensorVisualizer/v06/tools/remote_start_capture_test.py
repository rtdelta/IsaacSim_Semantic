import json,sys
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06');sys.path.insert(0,str(root))
from sensor_visualizer_v06.capture_supervisor import CaptureSupervisor
owner=json.loads((root/'reports/native_owner/owner.json').read_text())
report=json.loads((root/'reports/native_owner/interaction.json').read_text())
for p in Path('/proc').iterdir():
    if p.name.isdigit():
        try:raw=(p/'cmdline').read_bytes()
        except OSError:continue
        if str(root/'kit_replay_entry.py').encode() in raw:raise RuntimeError('Another capture test is active')
s=CaptureSupervisor(root,'/root/gpufree-data/semantic/output/sensor_visualizer/v06',owner['socket'])
value=s.start({'mode':'offline','trajectory':report['trajectory'],'groups':3,'sample_hz':10,'ros_preview':False})
(root/'reports/native_owner/offline_task.json').write_text(json.dumps(value));print(json.dumps(value))
