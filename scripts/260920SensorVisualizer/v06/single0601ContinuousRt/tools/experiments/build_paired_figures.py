"""Publication-style plots from independently verified experiment evidence."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from tools.experiments.storage import rows,digest,save
from tools.experiments.compare_paired_outputs import payload
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'reports/remote/reports/paired_analysis_evidence_20261014'
OUT=ROOT/'docs/Experiments/figures';OUT.mkdir(exist_ok=True)
manifest=json.loads((BASE/'analysis_manifest.json').read_text())
for item in manifest['files']:
    p=BASE/item['path']
    if p.stat().st_size!=item['bytes'] or digest(p)!=item['sha256']:raise ValueError('Collected evidence mismatch '+str(p))
save(ROOT/'reports/paired_final_local_verification.json',{'schema_version':1,'verified_files':len(manifest['files']),
    'verified_bytes':sum(x['bytes'] for x in manifest['files']),'manifest_sha256':digest(BASE/'analysis_manifest.json'),
    'scope':'All files in bounded evidence collection, not a full raw room dataset mirror'})
def plain(path):return [json.loads(s) for s in path.read_text().splitlines()]
parent=BASE/'paired_20261014_e2_room_mixed/repeats/r01'
metric=plain(parent/'analysis/paired_metrics.jsonl');geo=plain(parent/'analysis/geometry_metrics.jsonl')
mech=json.loads((parent/'analysis/mechanism_relations.json').read_text())
cg=mech['continuous']['groups'];fg=mech['frozen_room']['groups'];x=np.arange(len(metric))
fig,axes=plt.subplots(3,1,figsize=(12,10),constrained_layout=True)
axes[0].plot(x,np.degrees([m['C_native_rotation_rad'] for m in metric]),'.-',lw=.8,label='C: native pose error')
axes[0].plot(x,np.degrees([abs(g['C']['yaw_fit_rad']) for g in geo]),'.',label='C: independent geometry yaw')
axes[0].plot(x,np.degrees([abs(g['F']['yaw_fit_rad']) for g in geo]),'-',label='F: independent geometry yaw',color='seagreen')
axes[0].axhline(np.degrees(1e-4),color='crimson',ls='--',label='1e-4 rad gate')
axes[0].set(ylabel='Absolute rotation error (deg)',title='Known-room paired run r01: metadata misses 62 / 100 geometry failures')
axes[0].legend(ncol=2,fontsize=9)
axes[1].plot(x,[g['C']['point_plane_m']['0.95']*1000 for g in geo],'.-',lw=.8,label='C: original point cloud')
axes[1].plot(x,[g['F']['point_plane_m']['0.95']*1000 for g in geo],'-',label='F: original point cloud',color='seagreen')
axes[1].axhline(5,color='crimson',ls='--',label='5 mm gate')
axes[1].set(ylabel='Point-to-plane P95 (mm)',title='Independent six-plane geometry; no ICP or corrected payloads');axes[1].legend(fontsize=9)
best=[min([g['nominal_ray_actual_pose_range_residual_m']['0.95']]+[v['0.95'] for k,v in g['candidate_pose_range_residual_m'].items() if k.endswith('_SYNTHETIC')]) for g in cg]
axes[2].semilogy(x,[g['nominal_ray_actual_pose_range_residual_m']['0.95']*1000 for g in cg],'.-',lw=.8,label='C: rays at current actual pose')
axes[2].semilogy(x,np.array(best)*1000,'.-',lw=.8,label='C: best diagnostic rotation candidate')
axes[2].semilogy(x,[g['nominal_ray_actual_pose_range_residual_m']['0.95']*1000 for g in fg],'-',lw=1,label='F: rays at current actual pose',color='seagreen')
axes[2].set(ylabel='Ray-range residual P95 (mm, log)',title='Candidate comparison is explanatory only; all original bytes are retained');axes[2].legend(fontsize=9)
for ax in axes:ax.set_xlabel('Planned target index');ax.grid(alpha=.2)
fig.savefig(OUT/'paired_room_metadata_geometry_range.png',dpi=170);plt.close(fig)
e1=ROOT/'reports/remote/reports/paired_delivery_evidence/paired_20261014_e1_scene18_mixed/repeats'
fig,axes=plt.subplots(3,1,figsize=(12,7),constrained_layout=True,sharex=True)
for ax,repeat in zip(axes,('r01','r02','r03')):
    m=[r for r in plain(e1/repeat/'analysis/paired_metrics.jsonl') if r['kind']=='lidar']
    ax.plot([r['target_index'] for r in m],np.degrees([r['C_native_rotation_rad'] for r in m]),'.-',lw=.8,label='C')
    ax.plot([r['target_index'] for r in m],np.degrees([r['F_native_rotation_rad'] for r in m]),'-',color='seagreen',label='F')
    ax.axhline(np.degrees(1e-4),ls='--',color='crimson');ax.set(ylabel='Error (deg)',title=repeat+': C 31 / 100 fail; F 0 / 100 fail');ax.grid(alpha=.2);ax.legend(fontsize=8)
axes[-1].set_xlabel('Planned target index');fig.savefig(OUT/'paired_scene18_three_repeats.png',dpi=170);plt.close(fig)
old=ROOT/'reports/remote/reports/paired_capture_experiments/paired_20261014_e0_scene18/repeats/r02'
aligned=BASE/'paired_20261014_e0_scene18_lighting/repeats/r01'
fig,axes=plt.subplots(2,3,figsize=(15,6.5),constrained_layout=True)
for axrow,parent,label in zip(axes,(old,aligned),('Original light policies','Aligned single DomeLight')):
    images=[]
    for side in ('continuous','frozen_v06'):
        event=next(r for r in rows(parent/side/'native_events.jsonl') if r['kind']=='camera' and r['target_index']==6)
        images.append(payload(parent/side,event))
    for ax,im,title in zip(axrow[:2],images,('Continuous','v06 frozen')):ax.imshow(im);ax.set_title(label+' / '+title,fontsize=10)
    diff=np.abs(images[0].astype(float)-images[1].astype(float)).mean(axis=2)
    plot=axrow[2].imshow(diff,vmin=0,vmax=30,cmap='magma');axrow[2].set_title('Mean absolute RGB difference (0-30)',fontsize=10)
    fig.colorbar(plot,ax=axrow[2],shrink=.75)
    for ax in axrow:ax.set_axis_off()
fig.savefig(OUT/'paired_lighting_fixed_target6.png',dpi=170);plt.close(fig)
print(json.dumps({'verified_files':len(manifest['files']),'figures':[p.name for p in OUT.glob('paired_*.png')]}))
