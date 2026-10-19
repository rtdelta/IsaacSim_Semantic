"""Pure CPU experiment contracts and immutable target tables."""
import math
from pathlib import Path
import numpy as np


def parent_for(project,spec):
    if spec.get('native_instant_baseline'):
        relative=Path(spec['output_relative'])
        if relative.is_absolute() or '..' in relative.parts or relative.parts[:2]!=('reports','native_instant_baseline'):raise ValueError('Invalid independent-suite output')
        return Path(project)/relative
    if spec.get('suite')=='clock_state_v1':
        parts=[spec['experiment_id'],spec['condition'],'repeats',spec['repeat']]
        if any(Path(p).name!=p or p in ('.','..') for p in parts):raise ValueError('Unsafe experiment identifier')
        return project/'reports/clock_state_consistency'/Path(*parts)
    return project/'reports/paired_capture_experiments'/spec['experiment_id']/'repeats'/spec['repeat']


def target_table(spec,start,last):
    """Precomputed semi-implicit motion, identical increments to original room PRE."""
    from single0601_continuous_rt.geometry import matrix_from_pose
    hz=spec['physics_hz'];yaw=math.radians(spec.get('initial_yaw_deg',0));p=np.zeros(3);table={}
    pattern=spec.get('hold_pattern','HOLD0')
    masks={'HOLD0':[True]*6,'HOLD1':[True]*5+[False],'HOLD2':[True]*4+[False]*2,
        'HOLD3':[True]*3+[False]*3,'HOLD_ALT':[True,False]*3}
    if pattern not in masks:raise ValueError('Unknown hold pattern')
    if pattern!='HOLD0' and (hz!=60 or spec['stride']!=6):raise ValueError('Hold schedule is qualified only at 60/60Hz, 10Hz ticks')
    for step in range(start,last+1):
        move=masks[pattern][(step-start)%6]
        if move:
            if spec.get('native_instant_baseline'):yaw=math.radians(spec.get('initial_yaw_deg',0)+(step-start+1)*spec['yaw_rate_deg_s']/hz)
            else:yaw+=math.radians(spec['yaw_rate_deg_s'])/hz
            p[:2]+=spec['speed_m_s']/hz*np.array([math.cos(yaw),math.sin(yaw)])
        if not (-6<p[0]<9 and -10<p[1]<7):raise ValueError('Predeclared path leaves interior room margin')
        q=[0.,0.,math.sin(yaw/2),math.cos(yaw/2)]
        table[step]={'physical_step':step,'motion_step':step-start+1,'relative_time_s':(step-start+1)/hz,
            'position_m':p.tolist(),'orientation_xyzw':q,'matrix':matrix_from_pose(p,q).tolist()}
        if pattern!='HOLD0':table[step].update(hold=not move,hold_pattern=pattern,hold_write_policy=spec.get('hold_write_policy','WRITE_SAME'))
    return table


def safe_value(value):
    if isinstance(value,np.ndarray):return safe_value(value.tolist())
    if isinstance(value,np.generic):return safe_value(value.item())
    if isinstance(value,dict):return {str(k):safe_value(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [safe_value(v) for v in value]
    if isinstance(value,float) and not math.isfinite(value):return {'nonfinite':repr(value)}
    if value is None or isinstance(value,(str,float,int,bool)):return value
    return {'type':type(value).__module__+'.'+type(value).__name__,'repr':repr(value)}


def tri(value):return 'unknown' if value is None else ('pass' if value else 'fail')
