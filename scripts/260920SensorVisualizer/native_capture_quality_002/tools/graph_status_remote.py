import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_quality_002')
out=Path(json.loads((root/'reports/latest_execution.json').read_text())['directory'])
p=out/'native_pipeline_graph.json'
if p.exists():
 v=json.loads(p.read_text());print(json.dumps({'gates':v['gate_sources'],'rewired_edges':v['rewired_edges'],'nodes':[n for n in v['nodes'] if ('NativeBaseline_front' in n['path'] or 'NativeBaseline_MyAiry_front' in n['path'])]}))
else:print(json.dumps({'graph_dump':False}))
