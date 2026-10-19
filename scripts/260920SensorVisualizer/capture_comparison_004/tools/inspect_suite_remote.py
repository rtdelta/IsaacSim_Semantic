from pathlib import Path
import json
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/capture_comparison_004')
p=root/'reports/suite_supervisor.log';print(p.read_text(errors='replace')[-4000:])
info=json.loads((root/'reports/latest_suite.json').read_text());print(json.dumps({'alive':Path('/proc/'+str(info['pid'])).exists(),'info':info}))
source=Path('/root/gpufree-data/semantic/output/sensor_visualizer/v06/benchmarks/1791604257379431843_v05/input_trajectory')
first=json.loads((source/'states.jsonl').read_text().splitlines()[0]);print(json.dumps({'state_keys':list(first),'metadata_keys':list(json.loads((source/'metadata.json').read_text()))}))
