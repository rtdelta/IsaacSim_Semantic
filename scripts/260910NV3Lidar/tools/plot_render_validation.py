"""Plot the actual GPU-returned point clouds saved by isaac_demo.py."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]


def main():
    output=ROOT/'reports/isaacsim'
    report=json.loads((output/'validation.json').read_text(encoding='utf-8'))
    if not report['passed']:
        raise RuntimeError('Render verification must pass before plotting')
    base=np.load(output/'chamber_points.npz')
    target=np.load(output/'with_target_points.npz')
    xyz=target['xyz']
    changed=np.abs(base['observed_range_m']-target['observed_range_m'])>.1
    fig=plt.figure(figsize=(15,9),layout='constrained')
    ax=fig.add_subplot(2,2,1,projection='3d')
    selection=(np.arange(len(xyz))%4==0)&~changed
    ax.scatter(*xyz[selection].T,c=target['ring'][selection],s=.7,cmap='turbo',alpha=.45)
    ax.scatter(*xyz[changed].T,c='#d73b31',s=1)
    ax.scatter([0],[0],[0],color='black',s=25)
    ax.set(xlabel='X forward (m)',ylabel='Y left (m)',zlabel='Z up (m)',
           title='Actual RTX point cloud; target returns in red')
    ax.set_box_aspect((1,1,1));ax.view_init(elev=23,azim=-145)
    for index,data,title in [(2,base,'Empty chamber: measured range'),(3,target,'With a target: measured range')]:
        ax=fig.add_subplot(2,2,index)
        im=ax.imshow(data['observed_range_m'].reshape(96,480),origin='lower',aspect='auto',
                     vmin=4,vmax=18,cmap='viridis')
        ax.set(xlabel='Inferred sampling column',ylabel='ring',title=title)
        fig.colorbar(im,ax=ax,label='Range (m)')
    ax=fig.add_subplot(2,2,4)
    im=ax.imshow((base['observed_range_m']-target['observed_range_m']).reshape(96,480),
                 origin='lower',aspect='auto',vmin=0,cmap='magma')
    ax.set(xlabel='Inferred sampling column',ylabel='ring',
           title=f"Scene response: {report['changed_ranges_after_adding_target']:,} rays changed")
    fig.colorbar(im,ax=ax,label='Range reduction (m)')
    fig.suptitle('NZ3 96 x 480 | GPU ray tracing verified against ray-box geometry',fontsize=16)
    path=output/'render_validation.png'
    fig.savefig(path,dpi=160);plt.close(fig)
    print(path)


if __name__=='__main__':
    main()
