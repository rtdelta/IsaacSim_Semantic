import importlib.util,json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_baseline')
spec=importlib.util.spec_from_file_location('native_analysis',root/'tools/analyze_results.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
out=Path('/root/gpufree-data/semantic/output/native_capture_baseline/wave_diagnostic_20261011_125419/T_trace')
result=module.analyze(out)
(root/'reports/trace_analysis.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
