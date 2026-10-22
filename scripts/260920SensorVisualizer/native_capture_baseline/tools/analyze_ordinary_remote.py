import importlib.util,json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_baseline')
spec=importlib.util.spec_from_file_location('native_analysis',root/'tools/analyze_results.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
wave=Path('/root/gpufree-data/semantic/output/native_capture_baseline/wave_ordinary_20261011_124852')
results={name:module.analyze(wave/name) for name in ['A_render','B_publish','C_record','D_moving']}
(root/'reports/ordinary_analysis.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results))
