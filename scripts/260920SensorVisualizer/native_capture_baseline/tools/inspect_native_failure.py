import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_baseline')
execution=json.loads((root/'reports/latest_execution.json').read_text());out=Path(execution['directory'])
lines=(out/'engine.log').read_text(errors='replace').splitlines()
matches=[]
for i,line in enumerate(lines):
 if any(s in line for s in ['[Error]','Traceback','Failed to initialize','ErrorException']):
  matches.append('\n'.join(lines[max(0,i-1):i+12]))
print(json.dumps({'errors':matches[:25],'manifest_exists':(out/'sensor_manifest.json').exists()}))
