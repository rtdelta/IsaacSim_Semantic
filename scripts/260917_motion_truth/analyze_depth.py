"""Compare identical firing patterns and viewpoints, keeping unmatched returns explicit."""
from pathlib import Path
import json,numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
p=Path(__file__).resolve().parent
parts=['track_prim','cab_prim','boom_prim','arm_prim','bucket_prim']
names=['Track','Cab','Boom','Arm','Bucket']
rows=[]
fig,axs=plt.subplots(5,3,figsize=(11,14),sharex=True,sharey=True)
def summary(d):
 return {'n':int(len(d)),'median_m':float(np.median(d)),'p95_m':float(np.quantile(d,.95)),'max_m':float(d.max())} if len(d) else {'n':0}
for pi,link in enumerate(parts):
 dirs={k:p/'cases'/('depth_'+link+'_'+k+'_v6') for k in ['mesh','gaussian']}
 rec={k:json.loads((d/'result.json').read_text()) for k,d in dirs.items()}
 assert all(x['status']=='collected' for x in rec.values()),link
 np.testing.assert_allclose(rec['mesh']['center'],rec['gaussian']['center'],atol=1e-12,rtol=0)
 assert rec['mesh']['radius']==rec['gaussian']['radius']
 pair={'link':link,'views':[]};all_delta=[]
 for vi,view in enumerate(['x','y','z']):
  ranges={};directions={}
  np.testing.assert_allclose(rec['mesh']['views'][vi]['origin'],rec['gaussian']['views'][vi]['origin'],rtol=0,atol=1e-12)
  for kind,directory in dirs.items():
   data=np.load(directory/(view+'.npz'))
   distance=np.linalg.norm(data['xyz'],axis=1)
   valid=((data['flags']&64)!=0)&np.isfinite(distance)&(distance>.01)
   ids=data['emitterId'][valid].astype(int)
   assert len(ids)==len(set(ids.tolist())),'duplicate emitter in single-scan output'
   rr=np.full(1681,np.nan);rr[ids]=distance[valid];ranges[kind]=rr
   dd=np.full((1681,3),np.nan);dd[ids]=data['xyz'][valid]/distance[valid,None];directions[kind]=dd
  mr,gr=ranges['mesh'],ranges['gaussian']
  both=np.isfinite(mr)&np.isfinite(gr);mo=np.isfinite(mr)&~np.isfinite(gr);go=np.isfinite(gr)&~np.isfinite(mr)
  delta=gr[both]-mr[both];all_delta.append(np.abs(delta))
  da,db=directions['mesh'][both],directions['gaussian'][both]
  angle=np.degrees(np.arctan2(np.linalg.norm(np.cross(da,db),axis=1),np.sum(da*db,axis=1)))
  assert angle.max()<.001,'Matched emitter IDs must have the same ray direction'
  row={'view':view,'pattern_rays':1681,'mesh_returns':int(np.isfinite(mr).sum()),
       'gaussian_returns':int(np.isfinite(gr).sum()),'both':int(both.sum()),
       'mesh_only':int(mo.sum()),'gaussian_only':int(go.sum()),
       'paired_direction_max_degrees':float(angle.max()),
       'absolute_depth_difference':summary(np.abs(delta)),
       'signed_median_gs_minus_mesh_m':float(np.median(delta)) if len(delta) else None}
  pair['views'].append(row)
  np.savez_compressed(p/('depth_compare_'+link+'_'+view+'.npz'),mesh_ranges=mr,gaussian_ranges=gr)
  grid=np.full(1681,np.nan);grid[both]=np.abs(delta)*1000
  im=axs[pi,vi].imshow(grid.reshape(41,41),origin='lower',extent=[-16,16,-16,16],vmin=0,vmax=2000,cmap='magma')
  axs[pi,vi].set_title(names[pi]+' / '+view.upper()+' view; paired '+str(both.sum()))
  if vi==0:axs[pi,vi].set_ylabel('Elevation (deg)')
  if pi==4:axs[pi,vi].set_xlabel('Azimuth (deg)')
 pair['pooled_absolute_depth_difference']=summary(np.concatenate(all_delta))
 pair['coverage']={k:sum(v[k] for v in pair['views']) for k in ['mesh_returns','gaussian_returns','both','mesh_only','gaussian_only']}
 rows.append(pair)
fig.suptitle('Gaussian vs source Mesh: absolute paired LiDAR depth difference',fontsize=15)
fig.subplots_adjust(top=.945,bottom=.06,left=.09,right=.86,hspace=.32,wspace=.18)
bar=fig.colorbar(im,ax=axs.ravel().tolist(),cax=fig.add_axes([.90,.2,.022,.60]),extend='max')
bar.set_label('Absolute difference (mm); white = no paired return')
fig.text(.09,.02,'Same 41 x 41 firing grid per view; one final complete scan per geometry/view. Ray origins are identical. No registration fit.',fontsize=10)
fig.savefig(p/'depth_comparison.png',dpi=140)
(p/'depth_analysis.json').write_text(json.dumps(rows,indent=2))
lines=['# Mesh / Gaussian 同视角静态测距对照','',
'在新覆盖层中分别只保留对应 link 的 source Mesh 或 Gaussian，停用其他部件和业务图。两者都关闭 Motion BVH，以静态状态排除运动因素。每个部件分别从 +X、+Y、+Z 三个方向测量，每视角采用相同的 41×41 发射网格（±16°）。传感器距共同的 Mesh 包围盒中心 4 倍包围球半径，原始尺寸未缩放。','',
'每个几何/视角预热推进 90 次更新，比较最后一个完整扫描中相同 emitterId 的距离。各射线在一圈内分布发射，场景和传感器在该视角采样期间静止。这是三视角单圈抽查，未建立多圈重复统计或真实 LiDAR 的材质标定。','',
'“仅 Mesh / 仅 Gaussian”表示同一发射射线在另一种几何中没有对应的非零返回，可能与表面、遮挡、透明度、材质或检测阈值有关，不能直接解释成调度丢帧。两种几何都未返回的射线可能只是射出目标轮廓，不能计为故障。','',
'| 部件 | 配对回波数 | 仅 Mesh | 仅 Gaussian | 深度差中位数 | 深度差 P95 | 最大差 |','|---|---:|---:|---:|---:|---:|---:|']
for name,row in zip(['履带','驾驶室','大臂','小臂','铲斗及牙齿'],rows):
 s=row['pooled_absolute_depth_difference'];c=row['coverage']
 lines.append(f"| {name} | {c['both']} | {c['mesh_only']} | {c['gaussian_only']} | {s.get('median_m',float('nan'))*1000:.2f} mm | {s.get('p95_m',float('nan'))*1000:.2f} mm | {s.get('max_m',float('nan'))*1000:.2f} mm |")
lines+=['','上述差值没有把任一几何当作实物真值；它量化“换成 Mesh 后测量会改变多少”。配对点统计也不包含仅一方有返回的射线，所以必须结合覆盖计数阅读。','',
'![三视角深度差](depth_comparison.png)','',
'证据：depth_analysis.json、depth_compare_*.npz、cases/depth_*_v6 的 USD、运行快照、日志、原始 NPZ。*_context.png 的相机固定在 +X 方向，仅用于确认目标几何可见，不代表 Y/Z 测距视角。']
(p/'DEPTH_REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
print(json.dumps(rows,indent=2))
