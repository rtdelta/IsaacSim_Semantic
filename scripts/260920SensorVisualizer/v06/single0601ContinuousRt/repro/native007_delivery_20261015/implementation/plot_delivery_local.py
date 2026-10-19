"""Scientific figures of absolute errors and complete target denominators."""
import json,math
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap,BoundaryNorm
import numpy as np
ROOT=Path(__file__).resolve().parents[2];BASE=ROOT/'reports/native007_delivery_20261015';DATA=BASE/'evidence';OUT=BASE/'figures';OUT.mkdir(exist_ok=True)
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def metrics(c,p,r,run):return read(DATA/c/p/r/run/'analysis/target_metrics.json')
def save(fig,name):
 fig.savefig(OUT/(name+'.png'),dpi=180);fig.savefig(OUT/(name+'.svg'));plt.close(fig)
COLORS={'A0':'#2463a6','B1':'#cc7925','B2':'#27866f','B3':'#8a62aa','C1':'#8c5f45','C2':'#bf4051'}
fig,axes=plt.subplots(2,3,figsize=(13,7),constrained_layout=True)
for i,(profile,run) in enumerate((('R6P','m02'),('R3P','sm01'))):
 for j,c in enumerate(('A0','B1','B2')):
  ax=axes[i,j]
  for r in ('r01','r02','r03'):
   m=metrics(c,profile,r,run);y=[math.degrees(x['geometry']['yaw_error_rad']) for x in m]
   ax.plot(range(1,len(m)+1),y,color=COLORS[c],alpha=1 if r=='r01' else .35,lw=1.1,label=r)
  for value in (-1e-4,1e-4):ax.axhline(math.degrees(value),color='#555555',ls=':',lw=.8)
  ax.set(title=f'{c} / {profile}: 100 targets x 3',xlabel='Target index',ylabel='Signed geometric yaw correction (deg)');ax.grid(alpha=.2);ax.legend(fontsize=8)
fig.suptitle('Absolute yaw residual; no first-frame offset or fitted lag removed');save(fig,'absolute_yaw_residuals')
fig,axes=plt.subplots(2,1,figsize=(13,7),constrained_layout=True)
cmap=ListedColormap(['#38986e','#e5b64f','#c8504b','#8460a2']);cmap.set_bad('#dddddd');norm=BoundaryNorm([-.25,.25,.75,1.5,2.5],4)
for ax,(profile,run) in zip(axes,(('R6P','m02'),('R3P','sm01'))):
 labels=[];values=[]
 for c in ('A0','B1','B2'):
  for r in ('r01','r02','r03'):
   labels.append(c+' '+r);m=metrics(c,profile,r,run)
   values.append([{'current':0.,'half':.5,'previous1':1.,'previous2':2.}.get('|'.join(x['candidate']['best_members']),np.nan) if x['candidate']['status']=='distinguishable' else np.nan for x in m])
 im=ax.imshow(values,aspect='auto',interpolation='none',cmap=cmap,norm=norm,extent=[.5,100.5,len(labels)-.5,-.5]);ax.set_yticks(range(len(labels)),labels);ax.set(title=profile,xlabel='Target index')
fig.colorbar(im,ax=list(axes),ticks=[0,.5,1,2],label='Diagnostic history candidate (physics steps)');save(fig,'distance_history_candidates')
common=read(DATA/'stage_analysis/speed/common_orientations.json');fig,axes=plt.subplots(1,3,figsize=(13,3.8),constrained_layout=True)
for ax,c in zip(axes,('A0','B1','B2')):
 for repeat in ('r01','r02','r03'):
  d=next(x for x in common if x['condition']==c and x['repeat']==repeat)
  for key,col in [('R3P','#2463a6'),('R6P','#cc7925')]:
   y=[{'current':0,'half':.5,'previous1':1,'previous2':2}.get('|'.join(v[key+'_candidate']),np.nan) for v in d['rows']]
   ax.plot([v['yaw_deg'] for v in d['rows']],y,'.-',lw=.8,color=col,alpha=1 if repeat=='r01' else .3,label=key if repeat=='r01' else None)
 ax.set(title=c+' / fixed 50 common orientations',xlabel='Actual yaw (deg)',ylabel='History candidate (steps)');ax.grid(alpha=.2);ax.legend()
save(fig,'common_orientation_speed_comparison')
fig,axes=plt.subplots(2,1,figsize=(13,7),constrained_layout=True)
for ax,(profile,run) in zip(axes,(('R6P','m02'),('R3P','sm01'))):
 for c in ('A0','B1','B2'):
  for r in ('r01','r02','r03'):
   p=DATA/c/profile/r/run/'analysis/adjacent_increments.json';d=read(p)
   ax.plot(range(1,len(d)+1),[math.degrees(x['geometry_increment_error_rad']) for x in d],color=COLORS[c],lw=.9,alpha=1 if r=='r01' else .3,label=c if r=='r01' else None)
 for v in (-1e-4,1e-4):ax.axhline(math.degrees(v),color='#555555',ls=':',lw=.8)
 ax.set(title=profile+' / 99 adjacent pairs per run',xlabel='Adjacent pair index',ylabel='Signed yaw increment error (deg)');ax.grid(alpha=.2);ax.legend()
save(fig,'adjacent_increment_errors')
coded=DATA/'stage_analysis/coded'
if (DATA/'C2/R6P/r01/cm01/analysis/target_metrics.json').is_file():
 fig,axes=plt.subplots(2,1,figsize=(13,6),constrained_layout=True)
 for c in ('A0','C2'):
  for r in ('r01','r02','r03'):
   m=metrics(c,'R6P',r,'cm01');x=np.arange(1,len(m)+1);alpha=1 if r=='r01' else .3
   axes[0].plot(x,[z['ray_residual_m']['0.95']*1e3 for z in m],color=COLORS[c],alpha=alpha,label=c if r=='r01' else None)
   axes[1].plot(x,[math.degrees(z['native_rotation_error_rad']) for z in m],color=COLORS[c],alpha=alpha,label=c if r=='r01' else None)
 axes[0].set(ylabel='Current-pose radial residual P95 (mm)',xlabel='Target index');axes[1].set(ylabel='Native pose rotation error (deg)',xlabel='Target index')
 for ax in axes:ax.grid(alpha=.2);ax.legend()
 fig.suptitle('Motion BVH intervention: full retained outputs; strict return-set pairing differs');save(fig,'motion_bvh_full_output_confirmation')
if coded.is_dir():
 files=sorted(coded.glob('header_*.json'));fig,axes=plt.subplots(2,1,figsize=(13,6),constrained_layout=True)
 for p in files:
  d=read(p);label=Path(d['run']).parts[-4:];c,profile,r,run=label
  if r!='r01':continue
  x=np.arange(1,len(d['targets'])+1)
  axes[0].plot(x,[math.degrees(z['physical_increment_rad']) for z in d['targets']],'.-',label=c+' actual increment',lw=.8)
  axes[1].plot(x,[z['header_midpoint_distance_p95_m']*1e6 for z in d['targets']],label=c,linewidth=.9)
 axes[0].set(ylabel='Target-step increment (deg)',xlabel='Target index');axes[1].set(ylabel='Header midpoint radial P95 (um)',xlabel='Target index',yscale='log');axes[1].axhline(10,color='#555555',ls=':')
 for ax in axes:ax.grid(alpha=.2);ax.legend()
 fig.suptitle('Coded input: fixed reported-endpoint prediction; no fitted parameters');save(fig,'coded_header_prediction')
print(json.dumps({'figures':sorted(p.name for p in OUT.glob('*.png'))}))
