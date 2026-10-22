import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
latest=json.loads((root/'reports/latest_recording.json').read_text())
directory=Path(latest['directory'])
rows=json.loads((directory/'capability_probe/receipts.json').read_text())
bad=[r for r in rows if r['translation_error_m']>.001 or r['rotation_error_rad']>.0001 or r['physical_step']!=r['target_step']]
print(json.dumps({'directory':str(directory),'rows':len(rows),'bad':len(bad),'worst':sorted(bad,key=lambda r:r['rotation_error_rad'])[-2:],
                  'capabilities':json.loads((directory/'capabilities.json').read_text())}))
