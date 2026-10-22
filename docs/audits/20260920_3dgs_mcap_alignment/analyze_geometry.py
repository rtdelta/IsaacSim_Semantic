"""Compare supplied raw PLY coordinates against sampled production USD coordinates."""
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation

HERE = Path(__file__).resolve().parent
PLY = Path(r'D:\learning\IntelligentDepartment\CodesSet\Self\260907LidarVisualizer\Materials\3dgs')
remote = json.loads((HERE / 'remote_geometry_samples.json').read_text())
kin = json.loads((HERE.parent / '20260916_origin03_horizontal/kinematics_origin03.json').read_text())
R = Rotation.from_euler('xyz', [-103.98993, -5.69811, 61.29154], degrees=True).as_matrix()
DOC = np.eye(4); DOC[:3,:3] = R * 2.4; DOC[:3,3] = [3.20352, -.34217, 2.04934]
bind_q = [0, 37.1667, -85, -5.8742]

def xyz_from_ply(path):
    with path.open('rb') as f:
        props = []; count = None
        while True:
            line = f.readline().decode('ascii').strip()
            if line.startswith('element vertex '): count = int(line.split()[-1])
            if line.startswith('property '):
                _, ty, name = line.split(); assert ty == 'float'; props.append((name, '<f4'))
            if line == 'end_header': break
        data = np.fromfile(f, dtype=np.dtype(props), count=count)
    return np.column_stack([data[k] for k in ['x','y','z']]).astype(float)

def transform(m, pts): return pts @ m[:3,:3].T + m[:3,3]

def fit(a, b):
    ac = a - a.mean(0); bc = b - b.mean(0)
    u, s, vt = np.linalg.svd(ac.T @ bc)
    sign = np.eye(3); sign[2,2] = np.linalg.det(vt.T @ u.T)
    rot = vt.T @ sign @ u.T
    scale = (s * np.diag(sign)).sum() / (ac*ac).sum()
    mat = np.eye(4); mat[:3,:3] = scale * rot; mat[:3,3] = b.mean(0) - scale * rot @ a.mean(0)
    err = np.linalg.norm(transform(mat, a)-b, axis=1)
    return mat, {'scale':scale, 'rms_m':float(np.sqrt((err*err).mean())), 'max_m':float(err.max())}

def fk(qdeg):
    out = {'track':np.eye(4)}; cur = np.eye(4)
    for j,q,part in zip(kin['joints'],qdeg,['cab','boom','arm','bucket']):
        rz=np.eye(4);rz[:3,:3]=Rotation.from_euler('z',q,degrees=True).as_matrix()
        cur=cur @ np.array(j['T_parent_from_joint']) @ rz; out[part]=cur
    return out

result={'doc_bind_angles_deg':bind_q,'parts':{},'fk_doc_bind':{k:v.tolist() for k,v in fk(bind_q).items()},'lengths':{}}
samples={}; matrices={}
for rawname,src in remote['sources'].items():
    part = 'bucket' if rawname=='bucket_without_teeth' else rawname
    f=PLY/(rawname+'.ply'); pts=xyz_from_ply(f); sampled=pts[src['indices']]
    m,stats=fit(sampled,np.array(src['positions']))
    gs=np.array(remote['assets']['Excavator_Fangshan_05_origin03.usda']['parts'][part]['gs_local_column_matrix'])
    current=fk(bind_q)[part] @ gs @ m
    docpts=transform(DOC,sampled); actual=transform(current,sampled)
    delta=np.linalg.norm(docpts-actual,axis=1)
    rel=current @ np.linalg.inv(DOC)
    result['parts'][part]={'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'count':len(pts),'raw_to_usd_fit':stats,'raw_to_usd_column_matrix':m.tolist(),'raw_to_sim_base_at_doc_bind':current.tolist(),'doc_to_sim_at_doc_bind':rel.tolist(),'doc_vs_sim_rms_m':float(np.sqrt((delta*delta).mean())),'doc_vs_sim_centroid_delta_m':(actual.mean(0)-docpts.mean(0)).tolist(),'doc_vs_sim_rotation_deg':float(np.linalg.norm(Rotation.from_matrix(rel[:3,:3]).as_rotvec())*180/np.pi)}
    samples[part]=(docpts,actual);matrices[part]=current

# Put both models in exactly the same track frame, removing any global base convention.
basealign=matrices['track'] @ np.linalg.inv(DOC)
for part,(docpts,actual) in samples.items():
    aligned=transform(basealign,docpts);e=np.linalg.norm(actual-aligned,axis=1)
    result['parts'][part]['rms_after_exact_track_alignment_m']=float(np.sqrt((e*e).mean()))
    samples[part]=(aligned,actual)
result['doc_base_to_sim_base_via_track']=basealign.tolist()
calibration={'purpose':'Diagnostic candidate calibration, not deployed or a modification of the supplied contract', 'convention':'4x4 column-vector matrices; p_sim_base = FK_native(q) @ raw_to_native_link @ p_raw', 'length_unit':'metre','q_unit':'radian','native_joint_order':kin['joint_order'],'native_joints':kin['joints'],'source_geometry_scale':2.4,'parts':{}}
for part, data in result['parts'].items():
    gs=np.array(remote['assets']['Excavator_Fangshan_05_origin03.usda']['parts'][part]['gs_local_column_matrix'])
    calibration['parts'][part]={'raw_to_native_link':(gs @ np.array(data['raw_to_usd_column_matrix'])).tolist(),'ply_sha256':data['sha256'],'fit_scope':'512 ordered corresponding Gaussian centers, source conversion only','fit_error':data['raw_to_usd_fit']}
(HERE/'diagnostic_raw_to_native_links.json').write_text(json.dumps(calibration,indent=2),encoding='utf-8')
for key, v, sim in [('boom_axis_spacing',[4.550,-.066,3.198],kin['joints'][2]['origin_xyz_m'][0]),('arm_axis_spacing',[1.226,-.093,-2.662],kin['joints'][3]['origin_xyz_m'][0])]:
    result['lengths'][key]={'doc_m':float(np.linalg.norm(v)),'usd_m':sim,'difference_m':float(np.linalg.norm(v)-sim)}
(HERE/'geometry_comparison.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({'parts':{k:{a:b for a,b in v.items() if 'matrix' not in a and not isinstance(b,list)} for k,v in result['parts'].items()},'lengths':result['lengths'],'basealign':basealign.tolist()},indent=2))

if __name__=='__main__':
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axs=plt.subplots(1,2,figsize=(14,6))
    colors={'track':'#666666','cab':'#db9332','boom':'#d64b43','arm':'#3276bb','bucket':'#8e5ebc'}
    for ax,(i,j,label) in zip(axs,[(0,2,'Side view (X / Z)'),(0,1,'Top view (X / Y)')]):
        for part,(a,b) in samples.items():
            ax.scatter(a[:,i],a[:,j],s=4,c=colors[part],alpha=.5,label=part+' / colleague')
            ax.scatter(b[:,i],b[:,j],s=6,facecolors='none',edgecolors=colors[part],linewidths=.45,label=part+' / USD')
        ax.set_title(label);ax.set_aspect('equal');ax.set_xlabel('X (m)');ax.set_ylabel(('Z' if j==2 else 'Y')+' (m)');ax.grid(alpha=.2)
    axs[1].legend(loc='upper left',bbox_to_anchor=(1,1),fontsize=8)
    fig.suptitle('Same raw Gaussian centers; exact track alignment\nSolid: colleague bind model / Outlined: production USD at documented bag_2 joint angles')
    fig.tight_layout();fig.savefig(HERE/'binding_geometry_comparison.png',dpi=160)
