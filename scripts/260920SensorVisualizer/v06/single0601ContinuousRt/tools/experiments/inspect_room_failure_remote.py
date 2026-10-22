import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt/reports/paired_capture_experiments/paired_20261014_e0_room/repeats')
result=[]
for repeat in root.iterdir():
    directory=repeat/'frozen_room'
    result.append({'repeat':repeat.name,'files':[{'path':p.relative_to(directory).as_posix(),'bytes':p.stat().st_size} for p in directory.rglob('*') if p.is_file()],
        'log':(repeat/'frozen_room_launch.log').read_text(errors='replace')[-5000:]})
print(json.dumps(result))
