"""Publication-style plots of original absolute errors, never bias-subtracted."""
import argparse,json,math
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap,BoundaryNorm
import numpy as np

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def rows(p):return [json.loads(x)['data'] for x in p.read_text(encoding='utf-8').splitlines()]
def plot(root,summary,output):
    root=Path(root);report=read(Path(summary));output=Path(output);output.mkdir(parents=True,exist_ok=True)
    records=[r for r in report['records'] if r['phase'] in ('main','D_main')];data={}
    for r in records:
        p=root/r['path'];data[(r['group'],r['profile'],r['repeat'])]=(read(p/'analysis/target_metrics.json'),read(p/'analysis/adjacent_increments.json'),p)
    colors={'M_E':'#2368ad','P_E':'#dd7b20','M_D':'#24856b'}
    def save(fig,name):
        fig.savefig(output/(name+'.png'),dpi=170);fig.savefig(output/(name+'.svg'));plt.close(fig)
    fig,axes=plt.subplots(1,3,figsize=(12,3.7),constrained_layout=True)
    for ax,g in zip(axes,colors):
        key=(g,'R3P','r01')
        if key not in data:ax.set_visible(False);continue
        m,inc,p=data[key];physical=[r for r in rows(p/'continuous/baseline_physics.jsonl') if r['phase']=='physics_post_actual']
        first=m[0]['physical_step'];t0=int(m[0]['source_time_ns']);ev=read(p/'analysis/target_events.json')
        ax.plot([r['physical_step']-first for r in physical],[(int(r['sim_time_ns'])-t0)/1e9 for r in physical],color='#999999',lw=2,label='Actual physics time')
        ax.scatter([r['physical_step']-first for r in ev if r['physical_step'] is not None],[(int(r['source_time_ns'])-t0)/1e9 for r in ev if r['physical_step'] is not None],s=13,color=colors[g],label='Native source events')
        ax.set(title=g+' R3P / first repeat',xlabel='Physical step relative to first target',ylabel='Time relative to first target (s)');ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Source events matched to actual physics time (all raw events shown)');save(fig,'source_physics_time')
    fig,axes=plt.subplots(3,2,figsize=(12,9),constrained_layout=True)
    for row,profile in enumerate(('R3P','R3N','R6P')):
        left,right=axes[row]
        for g in colors:
            for repeat in ('r01','r02','r03'):
                if (g,profile,repeat) not in data:continue
                m,inc,p=data[(g,profile,repeat)];x=np.arange(1,len(m)+1);alpha=1 if repeat=='r01' else .35
                errors=[math.degrees(v['geometry']['yaw_error_rad']) if v.get('geometry',{}).get('yaw_error_rad') is not None else np.nan for v in m]
                right.plot(x,errors,color=colors[g],alpha=alpha,lw=1,label=g if repeat=='r01' else None)
                if repeat=='r01':
                    left.plot(x,[math.degrees(v['geometry_yaw_rad']) if v.get('geometry_yaw_rad') is not None else np.nan for v in m],color=colors[g],lw=1,label=g+' geometry')
                    if g=='M_E':left.plot(x,[math.degrees(v['actual_yaw_rad']) for v in m],color='#333333',ls='--',lw=1,label='Actual target')
        for threshold in (-1e-4,1e-4):right.axhline(math.degrees(threshold),color='#b73030',ls=':',lw=1)
        left.set(title=profile+' absolute yaw (repeat 1)',ylabel='Yaw in world frame (deg)',xlabel='Target index (1-based)')
        right.set(title=profile+' signed geometric error (all repeats)',ylabel='Geometry - actual yaw (deg)',xlabel='Target index (1-based)')
        for ax in (left,right):ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Absolute orientation and signed error; no first-frame offset removed');save(fig,'absolute_yaw_and_error')
    fig,axes=plt.subplots(3,1,figsize=(12,8),constrained_layout=True)
    for ax,profile in zip(axes,('R3P','R3N','R6P')):
        for g in colors:
            for repeat in ('r01','r02','r03'):
                if (g,profile,repeat) not in data:continue
                m,inc,p=data[(g,profile,repeat)];values=[math.degrees(r['geometry_increment_error_rad']) if r['geometry_increment_error_rad'] is not None else np.nan for r in inc]
                ax.plot(np.arange(1,len(values)+1),values,color=colors[g],alpha=1 if repeat=='r01' else .35,lw=1,label=g if repeat=='r01' else None)
        for threshold in (-1e-4,1e-4):ax.axhline(math.degrees(threshold),color='#b73030',ls=':',lw=1)
        ax.set(title=profile+' / 99 adjacent pairs per run',ylabel='Signed increment error (deg)',xlabel='Adjacent pair index (1-based)');ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Adjacent-scan increment error; gaps remain unknown, never bridged');save(fig,'adjacent_increment_error')
    fig,axes=plt.subplots(3,1,figsize=(12,8),constrained_layout=True)
    cmap=ListedColormap(['#2c996f','#ebbb46','#c75345','#8359a3']);cmap.set_bad('#dddddd');norm=BoundaryNorm([-.25,.25,.75,1.5,2.5],4)
    for ax,profile in zip(axes,('R3P','R3N','R6P')):
        labels=[];heat=[]
        for g in colors:
            for repeat in ('r01','r02','r03'):
                if (g,profile,repeat) not in data:continue
                m,inc,p=data[(g,profile,repeat)];labels.append(g+' '+repeat)
                heat.append([{'current':0.,'half':.5,'previous1':1.,'previous2':2.}.get('|'.join(v.get('candidate',{}).get('best_members',[])),np.nan) if v.get('candidate',{}).get('status')=='distinguishable' else np.nan for v in m])
        if not heat:ax.set_visible(False);continue
        im=ax.imshow(heat,aspect='auto',interpolation='none',cmap=cmap,norm=norm,extent=[.5,100.5,len(labels)-.5,-.5]);ax.set_yticks(range(len(labels)),labels);ax.set(title=profile,xlabel='Target index (1-based)')
    fig.colorbar(im,ax=list(axes),ticks=[0,.5,1,2],label='Distinguishable historical orientation (physics steps)')
    fig.suptitle('Predeclared candidate classification; grey = ambiguous/unobservable');save(fig,'history_candidates')
    common=report['common_orientation_comparison']
    if common:
        fig,axes=plt.subplots(2,1,figsize=(12,5),constrained_layout=True)
        for ax,group in zip(axes,('M_E','P_E')):
            c=next((c for c in common if c['group']==group and c['repeat']=='r01'),None)
            if c is None:ax.set_visible(False);continue
            for rate,col in [('R3P','#2368ad'),('R6P','#dd7b20')]:ax.plot([r['yaw_deg'] for r in c['rows']],[r[rate+'_lag_steps'] for r in c['rows']],'.-',color=col,lw=1,label=rate)
            ax.set(title=group+' / repeat 1, same 50 actual orientations',xlabel='Actual yaw (deg)',ylabel='Equivalent lag\n(physics steps)');ax.legend();ax.grid(alpha=.2)
        save(fig,'common_orientation_speed_control')
    print(json.dumps({'figures':sorted(p.name for p in output.glob('*.png'))}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root');p.add_argument('summary');p.add_argument('output');a=p.parse_args();plot(a.root,a.summary,a.output)
