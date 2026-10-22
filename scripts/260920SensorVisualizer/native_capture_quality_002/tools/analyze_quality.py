"""Post-run quality/cost comparisons using installed NumPy and Pillow only."""
import collections,json,math,statistics,sys
from pathlib import Path
import numpy as np
from PIL import Image

def summary(values):
 if not values:return {'n':0}
 return {'n':len(values),'median':statistics.median(values),'min':min(values),'max':max(values),'mean':statistics.mean(values)}

def image_metrics(first,reference):
 a=np.asarray(Image.open(first).convert('RGB'),dtype=np.float64);b=np.asarray(Image.open(reference).convert('RGB'),dtype=np.float64)
 d=a-b;mse=float(np.mean(d*d));mae=float(np.mean(np.abs(d)))
 a=a.mean(axis=2);b=b.mean(axis=2);k=7
 def mean(x):
  t=np.pad(x,((1,0),(1,0))).cumsum(axis=0).cumsum(axis=1)
  return (t[k:,k:]-t[:-k,k:]-t[k:,:-k]+t[:-k,:-k])/(k*k)
 ma=mean(a);mb=mean(b);va=mean(a*a)-ma*ma;vb=mean(b*b)-mb*mb;cov=mean(a*b)-ma*mb
 ssim=((2*ma*mb+6.5025)*(2*cov+58.5225))/((ma*ma+mb*mb+6.5025)*(va+vb+58.5225))
 return {'rgb_mae':mae,'psnr_db':10*math.log10(255**2/mse) if mse>0 else None,'ssim_box7_gray':float(np.mean(ssim)),'identical':mse==0}

def main(directory):
 out=Path(directory);rows=[json.loads(l) for l in (out/'groups.jsonl').read_text().splitlines()];cost=collections.defaultdict(list);quality=[]
 for r in rows:cost[r['case']['name']].append(r)
 for r in rows:
  c=r['case'];ref_name='rt_16' if c['renderer']=='RealTimePathTracing' else 'pt_1024'
  ref=next((v for v in rows if v['case']['name']==ref_name and v['case']['repeat']==c['repeat'] and v['case']['pose']==c['pose']),None)
  if ref is None or ref is r:continue
  for topic,im in r['images'].items():
   m=image_metrics(out/im['image'],out/ref['images'][topic]['image']);quality.append({'group':r['group'],'case':c,'camera_topic':topic,'reference_group':ref['group'],**m})
 result={'timing':{name:{key:summary([r[key] for r in values]) for key in ('ready_scope_s','advance_s','warm_s','formal_s','evidence_s')} for name,values in cost.items()},
  'quality_comparisons':quality,'pose_errors':summary([im['camera_pose_max_abs_error'] for r in rows for im in r['images'].values()]),
  'limits':['PNG evidence read/encode cost is excluded from render timing but included in whole-run time.','SSIM/PSNR compare rendered references, not reality or counterpart 3DGS alignment.','PT settings and SDK nominal subframes do not prove measured hardware sample counts.']}
 (out/'quality_analysis.json').write_text(json.dumps(result,indent=2));print(json.dumps({'groups':len(rows),'timing':result['timing'],'quality_pairs':len(quality),'pose_errors':result['pose_errors']}))
if __name__=='__main__':main(sys.argv[1])
