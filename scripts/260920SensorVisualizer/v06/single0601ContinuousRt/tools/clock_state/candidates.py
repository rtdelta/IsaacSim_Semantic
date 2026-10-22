"""Declared candidate poses and deterministic complete-link equivalence classes."""
import numpy as np
from single0601_continuous_rt.geometry import rigid_pose,matrix_from_pose
from single0601_continuous_rt.sensor_backend import pose_error

RULES={'schema_version':1,'candidate_ids':['current','previous1','previous2','half_full','p0_rhalf','p0_r1','p0_r2','phalf_r0','p1_r0','p2_r0'],
    'pose_equivalence_position_m':1e-8,'pose_equivalence_rotation_rad':1e-8,'best_p95_max_m':1e-5,
    'second_best_ratio_min':10.,'second_best_gap_min_m':20e-6,'frozen_ray_p95_max_m':1e-5,
    'geometry_plane_p95_m':.005,'geometry_yaw_rad':1e-4,'source_tolerance_ns':2,
    'equivalence_policy':'lexicographic candidate ID; complete-link; first member representative; never residual-selected',
    'formal_continuous_acceptance':False}


def valid(matrix):
    m=np.asarray(matrix,dtype=float)
    if m.shape!=(4,4) or not np.isfinite(m).all() or not np.allclose(m[:,3],[0,0,0,1],rtol=0,atol=1e-10):raise ValueError('Invalid affine pose')
    if not np.allclose(m[:3,:3]@m[:3,:3].T,np.eye(3),rtol=0,atol=1e-8) or abs(np.linalg.det(m[:3,:3])-1)>1e-8:raise ValueError('Non-rigid actual input')
    return m.copy()


def candidates(current,previous1=None,previous2=None):
    current=valid(current);result={'current':{'matrix':current,'p_lag_steps':0.,'r_lag_steps':0.,'synthetic':False}}
    def add(name,p,r,pl,rl,synthetic=True):
        m=np.eye(4);m[3,:3]=p;m[:3,:3]=r;result[name]={'matrix':m,'p_lag_steps':pl,'r_lag_steps':rl,'synthetic':synthetic}
    for lag,old in ((1,previous1),(2,previous2)):
        if old is None:continue
        old=valid(old);add('previous%d'%lag,old[3,:3],old[:3,:3],lag,lag,False)
        add('p0_r%d'%lag,current[3,:3],old[:3,:3],0.,lag);add('p%d_r0'%lag,old[3,:3],current[:3,:3],lag,0.)
        if lag==1:
            a=np.array(rigid_pose(old)[1]);b=np.array(rigid_pose(current)[1]);b=b if a@b>=0 else -b
            # Equal-weight midpoint equals SLERP at 1/2 for unit, shortest-arc quaternions.
            q=a+b;q=q/np.linalg.norm(q);r=matrix_from_pose([0,0,0],q)[:3,:3];p=(old[3,:3]+current[3,:3])/2
            add('half_full',p,r,.5,.5);add('p0_rhalf',current[3,:3],r,0.,.5);add('phalf_r0',p,current[:3,:3],.5,0.)
    return result


def equivalent(a,b,rules=RULES):
    p,r=pose_error(a,b);return p<=rules['pose_equivalence_position_m'] and r<=rules['pose_equivalence_rotation_rad']


def group_candidates(values,rules=RULES):
    groups=[]
    for key in sorted(values):
        matrix=valid(values[key]['matrix'])
        for group in groups:
            if all(equivalent(matrix,values[other]['matrix'],rules) for other in group):group.append(key);break
        else:groups.append([key])
    return groups


def classify(values,residuals,rules=RULES):
    groups=[]
    for members in group_candidates(values,rules):
        errors=[float(residuals[m]) for m in members]
        groups.append({'representative':members[0],'members':members,'member_p95_m':dict(zip(members,errors)),
            'min_p95_m':min(errors),'max_p95_m':max(errors),'p_lag_steps':sorted(set(values[m]['p_lag_steps'] for m in members)),
            'r_lag_steps':sorted(set(values[m]['r_lag_steps'] for m in members))})
    ordered=sorted(groups,key=lambda g:(g['member_p95_m'][g['representative']],g['representative']))
    best=ordered[0];second=min(ordered[1:],key=lambda g:(g['min_p95_m'],g['representative'])) if len(ordered)>1 else None
    missing=sorted(set(rules['candidate_ids'])-set(values))
    separated=bool(second and best['max_p95_m']<=rules['best_p95_max_m'] and
        second['min_p95_m']>=rules['second_best_ratio_min']*best['max_p95_m'] and
        second['min_p95_m']-best['max_p95_m']>=rules['second_best_gap_min_m'])
    status='unobservable' if second is None else ('distinguishable' if separated and not missing else 'ambiguous')
    if missing:status='incomplete_candidates'
    return {'status':status,'groups':groups,'best_representative':best['representative'],'best_members':best['members'],
        'best_p95_max_m':best['max_p95_m'],'second_p95_min_m':second['min_p95_m'] if second else None,'missing_candidates':missing,
        'position_delay_identifiable':status=='distinguishable' and len(best['p_lag_steps'])==1,
        'rotation_delay_identifiable':status=='distinguishable' and len(best['r_lag_steps'])==1,
        'position_lag_steps':best['p_lag_steps'] if status=='distinguishable' else None,
        'rotation_lag_steps':best['r_lag_steps'] if status=='distinguishable' else None}
