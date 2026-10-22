"""Fixed-index scientific comparison figure from independently hashed RGB."""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from tools.experiments.storage import rows,verify
from tools.experiments.compare_paired_outputs import payload
ROOT=Path(__file__).resolve().parents[2]
parent=ROOT/'reports/remote/reports/paired_capture_experiments/paired_20261014_e0_scene18/repeats/r02'
out=ROOT/'docs/Experiments/figures';out.mkdir(exist_ok=True)
events={side:rows(parent/side/'native_events.jsonl') for side in ('continuous','frozen_v06')}
for side in events:verify(parent/side)
metrics=[json.loads(line) for line in (parent/'analysis/paired_metrics.jsonl').read_text().splitlines()]
lidars=[r for r in metrics if r['kind']=='lidar'];cameras=[r for r in metrics if r['kind']=='camera']
fig,axes=plt.subplots(1,2,figsize=(11,3.6),constrained_layout=True)
x=[r['target_index'] for r in lidars]
axes[0].plot(x,np.degrees([r['C_native_rotation_rad'] for r in lidars]),'o-',label='Continuous')
axes[0].plot(x,np.degrees([r['F_native_rotation_rad'] for r in lidars]),'.-',label='v06 frozen')
axes[0].axhline(np.degrees(1e-4),color='crimson',ls='--',label='1e-4 rad gate')
axes[0].set(xlabel='Planned target index',ylabel='LiDAR native pose error (deg)',title='E0: same actual input state');axes[0].legend(fontsize=8)
axes[1].plot([r['target_index'] for r in cameras],[r['image_psnr_db'] for r in cameras],'o-',color='darkorange')
axes[1].set(xlabel='Planned target index',ylabel='RGB PSNR (dB)',title='Descriptive image difference; quality not qualified')
for ax in axes:ax.grid(alpha=.2)
fig.savefig(out/'e0_pose_and_image.png',dpi=180);plt.close(fig)
index=6
cr=next(r for r in events['continuous'] if r['kind']=='camera' and r['target_index']==index)
fr=next(r for r in events['frozen_v06'] if r['kind']=='camera' and r['target_index']==index)
c=payload(parent/'continuous',cr);f=payload(parent/'frozen_v06',fr);diff=np.abs(c.astype(float)-f.astype(float)).mean(axis=2)
fig,axes=plt.subplots(1,3,figsize=(15,3.4),constrained_layout=True)
axes[0].imshow(c);axes[0].set_title('Continuous / fixed target 6')
axes[1].imshow(f);axes[1].set_title('v06 frozen / exact same input')
plot=axes[2].imshow(diff,vmin=0,vmax=30,cmap='magma');axes[2].set_title('Mean absolute RGB difference (0-30)')
fig.colorbar(plot,ax=axes[2],shrink=.7)
for ax in axes:ax.set_axis_off()
fig.savefig(out/'e0_fixed_target6_rgb.png',dpi=180);plt.close(fig)
print(str(out))
