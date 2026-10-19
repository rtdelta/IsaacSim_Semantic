import json,statistics,collections
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_quality_002');m=json.loads((root/'reports/latest_matrix.json').read_text());out=Path(m['directory'])
rows=json.loads((out/'matrix_progress.json').read_text()) if (out/'matrix_progress.json').exists() else []
result=[]
for row in rows:
 capture=Path(row['directory']);q=capture/'quality_analysis.json'
 if not q.exists():continue
 quality=json.loads(q.read_text());values=collections.defaultdict(lambda:collections.defaultdict(list))
 for im in quality['quality_comparisons']:
  for k in ('rgb_mae','psnr_db','ssim_box7_gray'):
   if im[k] is not None:values[im['case']['name']][k].append(im[k])
 r=json.loads((capture/'result.json').read_text());groups=[json.loads(l) for l in (capture/'groups.jsonl').read_text().splitlines()]
 result.append({'suite':row['suite'],'directory':str(capture),'state':r['state'],'process_wall_s':r['process_wall_s'],
  'capture':r['capture'],'timing':quality['timing'],'quality':{name:{k:{'mean':statistics.mean(v),'min':min(v),'max':max(v),'n':len(v)} for k,v in data.items()} for name,data in values.items()},
  'pose_errors':quality['pose_errors'],'images':len(groups)*4,'mcap_bytes':sum(p.stat().st_size for p in (capture/'bag').glob('*.mcap')),
  'strict':{k:r['group_validation'][k] for k in ('ok','errors')},'resource':json.loads((capture/'analysis.json').read_text()).get('nvml_window') if (capture/'analysis.json').exists() else None})
print(json.dumps(result))
