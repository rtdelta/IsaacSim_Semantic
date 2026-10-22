import json
from pathlib import Path

root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
latest=json.loads((root/'reports/latest_probe.json').read_text())
directory=Path(latest['directory'])
rows=json.loads((directory/'probe_receipts.json').read_text())
bad=[r for r in rows if r['translation_error_m']>.001 or r['rotation_error_rad']>.0001]
errors=json.loads((directory/'probe_errors.json').read_text())
print(json.dumps({'directory':str(directory),'bad_pose_count':len(bad),
 'worst':sorted(bad,key=lambda r:r['translation_error_m'],reverse=True)[:3],
 'last_error':errors[-2:],'source_ranges':{s:[min(r['source_time_s'] for r in rows if r['sensor_id']==s),max(r['source_time_s'] for r in rows if r['sensor_id']==s)] for s in {r['sensor_id'] for r in rows}}}))
