"""Static scientific figures using local, hash-verified experiment evidence."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
R=Path(__file__).resolve().parent;dest=R/'docs/figures';dest.mkdir(exist_ok=True)
fig,axes=plt.subplots(2,2,figsize=(13,9),constrained_layout=True)
g=np.load(R/'results/geometry/visible_meshes.npz');info=json.loads((R/'results/geometry/manifest.json').read_text());xyz=g['vertices'];faces=g['triangles'];owner=g['face_owner'];vehicle_ids=[i for i,x in enumerate(info['meshes']) if '/Excavator/' in x['path'] and '/Visuals/' in x['path']]
body=xyz[faces[np.isin(owner,vehicle_ids)][::70]]
for col,family in enumerate(('legacy','native')):
 a=np.load(R/f'results/geometry_analysis/{family}_MyNZ3_left.npz');points=a['local'];world=a['world'];ranges=a['ranges'];near=ranges<=2
 az=np.degrees(np.arctan2(points[:,1],points[:,0]));el=np.degrees(np.arctan2(points[:,2],np.linalg.norm(points[:,:2],axis=1)))
 ax=axes[0,col];ax.scatter(az,el,c='#b5c2d0',s=.5,rasterized=True);ax.scatter(az[near],el[near],c='#d65f20',s=1,rasterized=True,label=f'<=2m: {sum(near):,}')
 ax.set(xlim=(-130,130),ylim=(-50,50),xlabel='Azimuth (deg, sensor)',ylabel='Elevation (deg, sensor)',title=('Self-built single06' if family=='legacy' else 'Native frozen RT2')+' / MyNZ3_left');ax.legend(loc='upper left',markerscale=5)
 ax=axes[1,col];segments=np.concatenate([body[:,:2,:2],body[:,1:,:2],body[:,[2,0],:2]])
 ax.add_collection(LineCollection(segments,colors='#aab2b9',linewidths=.2,alpha=.25))
 ax.scatter(world[near,0],world[near,1],c='#d65f20',s=2,rasterized=True)
 meta=json.loads((R/f'results/{family}_round_01/formal_clouds/000/MyNZ3_left.json').read_text());m=np.array(meta['world_matrix_row']);ax.scatter(m[3,0],m[3,1],c='#154c79',marker='*',s=150,label='Sensor origin')
 ax.set(xlim=(-5,5),ylim=(-.5,5),xlabel='World X (m)',ylabel='World Y (m)',title='Near returns on excavator mesh / top view');ax.set_aspect('equal');ax.legend(loc='upper right');ax.grid(alpha=.15)
fig.suptitle('NC-006 | Scene18, identical static pose | Baseline round 1, group 0',fontsize=15)
fig.savefig(dest/'NZ3_left_baseline_comparison.png',dpi=180);plt.close(fig)
print(dest/'NZ3_left_baseline_comparison.png')
fig,axes=plt.subplots(1,3,figsize=(15,4.8),constrained_layout=True,sharex=True,sharey=True)
for ax,(label,folder) in zip(axes,[('Self-built / baseline','legacy_round_01'),('Native / auto-update frozen','native_round_01'),('Native / Pause, no raw probe','native_pause_no_probe')]):
    p=np.load(R/'results'/folder/'formal_clouds/000/MyNZ3_left.npy');r=np.linalg.norm(p,axis=1);near=r<=2
    az=np.degrees(np.arctan2(p[:,1],p[:,0]));el=np.degrees(np.arctan2(p[:,2],np.linalg.norm(p[:,:2],axis=1)))
    ax.scatter(az,el,c='#b5c2d0',s=.4,rasterized=True);ax.scatter(az[near],el[near],c='#d65f20',s=.8,rasterized=True)
    ax.set(xlim=(-130,130),ylim=(-45,45),xlabel='Sensor azimuth (deg)',title=f'{label}\nTotal: {len(p):,} | <=2m: {sum(near):,}')
axes[0].set_ylabel('Sensor elevation (deg)')
fig.suptitle('Freeze-policy control | same static USD pose | Pause bag publication FAILED',fontsize=13)
fig.savefig(dest/'NZ3_left_freeze_policy_control.png',dpi=150);plt.close(fig)
