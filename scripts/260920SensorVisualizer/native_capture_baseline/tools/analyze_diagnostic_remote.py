import importlib.util,json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_baseline')
spec=importlib.util.spec_from_file_location('native_analysis',root/'tools/analyze_results.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
wave=Path('/root/gpufree-data/semantic/output/native_capture_baseline/wave_diagnostic_20261011_125419')
results={name:module.analyze(wave/name) for name in ['T_trace','F_frozen','M_multitick']}
(root/'reports/diagnostic_analysis.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results))
