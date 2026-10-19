"""Standalone scientific figures from verified saved evidence only."""
import argparse,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

def plot(directory,output):
    directory=Path(directory);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    frequency=json.loads((directory/'clock_20261014_v1/frequency_comparison.json').read_text())
    names=['T2_Rplus','T4_B120_3','T4_C120_6','T4_D60_6']
    labels=['A: 60 Hz, 3 deg/s','B: 120 Hz, 3 deg/s','C: 120 Hz, 6 deg/s','D: 60 Hz, 6 deg/s']
    fig,axes=plt.subplots(2,1,figsize=(11,6),sharex=True,constrained_layout=True)
    colors=['#245c9c','#df801e','#268160','#963a83']
    step_values=[];second_values=[];present_labels=[]
    for name,label,color in zip(names,labels,colors):
        runs=[r for r in frequency['conditions'] if r['condition']==name]
        if not runs:continue
        first=sorted(runs,key=lambda r:r['repeat'])[0]
        rows=[r for r in first['per_target'] if r['nominal_yaw_deg']<=30+1e-9 and abs(r['nominal_yaw_deg']/.6-round(r['nominal_yaw_deg']/.6))<1e-8]
        if len(rows)!=50:raise ValueError('Predeclared matched orientation count is not 50')
        step_values.append([r['lag_steps'] for r in rows]);second_values.append([r['lag_s']*1000 if r['lag_s'] is not None else np.nan for r in rows]);present_labels.append(label)
    from matplotlib.colors import ListedColormap,BoundaryNorm
    heat=axes[0].imshow(step_values,aspect='auto',interpolation='nearest',extent=[.3,30.3,len(step_values)-.5,-.5],
        cmap=ListedColormap(['#3a79ad','#e28b35']),norm=BoundaryNorm([.25,.75,1.25],2))
    fig.colorbar(heat,ax=axes[0],ticks=[.5,1.],label='Inferred lag (physics steps)')
    heat=axes[1].imshow(second_values,aspect='auto',interpolation='nearest',extent=[.3,30.3,len(step_values)-.5,-.5],cmap='viridis',vmin=0,vmax=16.6666667)
    fig.colorbar(heat,ax=axes[1],ticks=[4.1666667,8.3333333,16.6666667],label='Inferred lag (ms)')
    axes[0].set_title('Same 50 target orientations: 0.6, 1.2, ..., 30 degrees\nFirst independent run shown; no interpolation of sensor data')
    axes[1].set_xlabel('Target yaw from initial pose (deg)')
    for ax in axes:
        ax.set_yticks(range(len(present_labels)),present_labels);ax.set_xticks([.6,6,12,18,24,30])
    fig.savefig(output/'frequency_rotation_history.png',dpi=160);fig.savefig(output/'frequency_rotation_history.svg');plt.close(fig)
    branch_path=directory/'clock_20261014_v2/branch_comparison.json'
    if branch_path.exists():
        branch=json.loads(branch_path.read_text());runs=[r for r in branch['runs'] if r['targets']==100]
        conditions=['T5_PRE','T5_POST','T6_HOLD2_WRITE','T6_HOLD2_SKIP','T6_ALT_WRITE','T6_ALT_SKIP']
        fig,axes=plt.subplots(1,2,figsize=(12,5),constrained_layout=True)
        for i,c in enumerate(conditions):
            rr=[r for r in runs if r['condition']==c]
            axes[0].scatter([i]*len(rr),[r['geometry_failed'] for r in rr],color=colors[i%4],s=55)
            axes[1].scatter([i]*len(rr),[r['path_m_per_sim_s'] for r in rr],color=colors[i%4],s=55)
        labels=['PRE','POST','HOLD2\nWRITE','HOLD2\nSKIP','ALT\nWRITE','ALT\nSKIP']
        for ax in axes:ax.set_xticks(range(6),labels);ax.grid(axis='y',alpha=.2)
        axes[0].set(ylabel='Geometry failures / 100 planned targets',ylim=(-4,104),title='Independent runs; overlapping markers are identical')
        axes[1].set(ylabel='Measured path advance (m / simulation s)',title='Mechanism controls retain moving-step increments')
        fig.savefig(output/'phase_hold_results.png',dpi=160);fig.savefig(output/'phase_hold_results.svg');plt.close(fig)
    print(json.dumps({'output':str(output),'files':[p.name for p in output.iterdir()]}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory');p.add_argument('output');a=p.parse_args();plot(a.directory,a.output)
