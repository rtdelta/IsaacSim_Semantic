import json, subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/261013Rviz2Viewer')
latest=json.loads((root/'reports/latest_capture.json').read_text())
capture=Path(latest['directory'])/'capture'
result=json.loads((capture/'result.json').read_text())
session=Path(result['capture']['session'])
value={'result':result,'model_validation':json.loads((capture/'viewer_model_validation.json').read_text())}
for name,path in [('custom_index',session/'viewer_cache/index.audit.json'),('native_index',Path('/root/gpufree-data/semantic/output/261013Rviz2Viewer/native_reference_cache/index.audit.json'))]:
    value[name]=json.loads(path.read_text())
value['summaries']={str(p):json.loads(p.read_text()) for p in (session/'viewer_logs').glob('*/summary.json')}
gui_log=Path(json.loads((root/'reports/gui_process.json').read_text())['log'])
value['gui_stdout']=gui_log.read_text()[-4000:]
rviz_log=sorted((session/'viewer_logs').glob('*/rviz.log'))[-1]
value['rviz_log']=rviz_log.read_text()[-6000:]
value['bag_files']=[{'name':p.name,'bytes':p.stat().st_size} for p in (session/'bag_unified').iterdir() if p.is_file()]
(root/'reports/evidence_summary.json').write_text(json.dumps(value,indent=2))
print(json.dumps(value))
