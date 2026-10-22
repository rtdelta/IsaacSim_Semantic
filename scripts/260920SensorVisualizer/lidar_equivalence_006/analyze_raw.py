"""Compare owned raw GMO XYZ with formal extractor payload and stable emission keys."""
import json,hashlib,sys
from pathlib import Path
import numpy as np
R=Path(sys.argv[1]);out=R/'raw_analysis';out.mkdir(exist_ok=True)
rows=[];details={}
for family in ('native_dual_retry1','legacy_raw'):
 cap=R/family/'capture'
 for p in sorted((cap/'dual_exit').glob('*/*_raw_header.json')):
  sid=p.name.removesuffix('_raw_header.json');group=int(p.parent.name)
  header=json.loads(p.read_text())
  with np.load(p.with_name(sid+'_raw.npz')) as archive:data={k:archive[k] for k in archive.files}
  raw=np.stack([data[k] for k in ('x','y','z')],axis=1);formal=np.load(cap/'formal_clouds'/p.parent.name/(sid+'.npy'))
  if header['elementsCoordsType']!='CoordsType.CARTESIAN':raise RuntimeError('Handle coordinate conversion explicitly')
  rr=np.linalg.norm(raw.astype(np.float64),axis=1)
  row={'family':family,'group':group,'sensor':sid,'raw_frame':header['frameId'],'raw_stamp_ns':header['timestampNs'],'raw_points':len(raw),'formal_points':len(formal),'raw_formal_equal':np.array_equal(raw,formal),'max_raw_formal_error':float(np.max(np.abs(raw-formal))) if raw.shape==formal.shape else None,'near_1m':int(sum(rr<=1)),'near_2m':int(sum(rr<=2)),'fields':{k:{'shape':list(data[k].shape),'dtype':str(data[k].dtype)} for k in data}}
  fields=[k for k in ('emitterId','channelId','echoId','tickId') if k in data and len(data[k])==len(raw)]
  keys=[tuple(int(data[k][i]) for k in fields) for i in range(len(raw))]
  row['key_fields']=fields;row['unique_key_count']=len(set(keys));row['first_keys']=keys[:3]
  rows.append(row);details[(family,group,sid)]=(raw,keys,fields)
pairs=[]
for (family,group,sid),(a,ka,fa) in details.items():
 if family!='legacy_raw':continue
 b,kb,fb=details[('native_dual_retry1',group,sid)]
 if fa!=fb or len(set(ka))!=len(ka) or len(set(kb))!=len(kb):
  pairs.append({'sensor':sid,'group':group,'pairable':False});continue
 ia={k:i for i,k in enumerate(ka)};ib={k:i for i,k in enumerate(kb)};shared=sorted(ia.keys()&ib.keys())
 ai=np.array([ia[k] for k in shared]);bi=np.array([ib[k] for k in shared]);x=a[ai].astype(float);y=b[bi].astype(float)
 ar=np.linalg.norm(x,axis=1);br=np.linalg.norm(y,axis=1)
 angular=np.degrees(np.arccos(np.clip(np.sum(x*y,axis=1)/np.maximum(ar*br,1e-30),-1,1)))
 pairs.append({'sensor':sid,'group':group,'pairable':True,'shared':len(shared),'legacy_only':len(ka)-len(shared),'native_only':len(kb)-len(shared),'angle_difference_deg_p50_p95_max':np.percentile(angular,[50,95,100]).tolist(),'range_difference_abs_m_p50_p95_max':np.percentile(np.abs(ar-br),[50,95,100]).tolist(),'near_legacy_shared':int(sum(ar<=2)),'near_native_shared':int(sum(br<=2)),'legacy_near_native_far':int(sum((ar<=2)&(br>2))), 'legacy_only_near2':sum(float(np.linalg.norm(a[ia[k]]))<=2 for k in ia.keys()-ib.keys())})
(out/'raw_formal_checks.json').write_text(json.dumps(rows,indent=2));(out/'emission_key_comparisons.json').write_text(json.dumps(pairs,indent=2))
summary={'samples':len(rows),'raw_formal_equal':sum(r['raw_formal_equal'] for r in rows),'all_exact':all(r['raw_formal_equal'] for r in rows),'focus':[r for r in rows if r['sensor']=='MyNZ3_left'],'key_focus':[r for r in pairs if r['sensor']=='MyNZ3_left'],'limit':'Across runs emission keys only identify channel/tick positions; do not assert identical emission times or stochastic state.'}
(out/'summary.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2))
