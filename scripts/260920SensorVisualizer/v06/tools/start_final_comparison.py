"""Repeat the final default pipeline after native acceptance; preserve prior trials."""
import json,runpy
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06')
assert json.loads((root/'reports/native_owner/acceptance_status.json').read_text())['passed']
baseline=json.loads((root/'reports/baseline_performance_suite.json').read_text())
spec={'version':'v06','groups':8,'interactive_seconds':45,
    'trajectory':str(Path(baseline['directory'])/'input_trajectory'),
    'deployment_manifest':json.loads((root/'deployment_manifest.json').read_text())}
runpy.run_path(str(root/'tools/start_performance_suite.py'),init_globals={'SPEC':spec})
(root/'reports/final_performance_suite.json').write_text((root/'reports/latest_performance_suite.json').read_text())
