import importlib.util,json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_baseline')
spec=importlib.util.spec_from_file_location('native_analysis',root/'tools/analyze_results.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
wave=Path('/root/gpufree-data/semantic/output/native_capture_baseline/wave_final_20261011_130446')
results={name:module.analyze(wave/name) for name in ['E_final_record','A_trace_render']}
(root/'reports/final_analysis.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results))
