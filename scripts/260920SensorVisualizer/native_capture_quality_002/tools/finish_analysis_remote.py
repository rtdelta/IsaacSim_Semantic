import json, subprocess, time
from pathlib import Path

root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_quality_002')
trace=Path(json.loads((root/'reports/latest_execution.json').read_text())['directory'])
result=json.loads((trace/'result.json').read_text())
assert result['state']=='completed' and result['trace'] and result['profile_capture_verified'], result
out=trace.parent/'final_analysis'
out.mkdir(exist_ok=True)
commands=[
 ['/bin/bash','-c','source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 "$@"','nc002',str(root/'tools/compare_reference.py')],
 ['/usr/bin/python3',str(root/'tools/analyze_phases.py'),str(trace)],
]
statuses=[]
for index,command in enumerate(commands):
 with (out/f'analysis_{index}.log').open('w') as log:
  code=subprocess.run(command,stdout=log,stderr=log,timeout=180).returncode
 statuses.append(code)
 if code:
  print((out/f'analysis_{index}.log').read_text()[-3000:])
  raise RuntimeError(f'Analysis {index} failed')
comparison=root/'reports/reference_comparison.json'
(out/'reference_comparison.json').write_bytes(comparison.read_bytes())
(out/'analysis_status.json').write_text(json.dumps({'exit_codes':statuses,'trace_directory':str(trace),'profile_capture_verified':result['profile_capture_verified']},indent=2))
print(json.dumps({'directory':str(out),'status':statuses,'profile_capture_verified':True}))
