"""Fit diagnostic yaw residual from known room planes, without altering XYZ.

Plane assignments must have a fixed 50 mm margin from the second closest
surface. This is a one-axis diagnostic of the specified room trajectory,
not a general pose solver, time correction, or formal adapter.
"""
import argparse,json,math,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from single0601_continuous_rt.common import file_hash,save_json
from tools.analyze_room_geometry import p95


def analyze(directory):
    directory=Path(directory).resolve()
    walls=json.loads((directory/'render_profile.json').read_text())['room_geometry']
    axes=np.array([w['axis'] for w in walls]);coordinates=np.array([w['coordinate_m'] for w in walls])
    rows=[json.loads(line)['data'] for line in (directory/'native_events.jsonl').read_text().splitlines()]
    groups=[]
    for row in rows:
        if row['kind']!='lidar':continue
        path=(directory/row['payload_path']).resolve()
        if directory not in path.parents or file_hash(path)!=row['payload_sha256']:raise ValueError('Frozen XYZ identity mismatch')
        xyz=np.frombuffer(path.read_bytes(),dtype='<f4').reshape(row['shape']).astype(float)
        matrix=np.array(row['historical_to_world']);base=xyz @ matrix[:3,:3];origin=matrix[3,:3]
        world=base+origin
        distances=np.abs(world[:,axes]-coordinates)
        order=np.argsort(distances,axis=1)
        keep=(distances[np.arange(len(xyz)),order[:,1]]-distances[np.arange(len(xyz)),order[:,0]])>=.05
        keep &= axes[order[:,0]]<2
        chosen=order[keep,0];axis=axes[chosen];target=coordinates[chosen]
        vectors=base[keep];delta=0.
        for _ in range(4):
            c,s=math.cos(delta),math.sin(delta)
            rotated=np.column_stack((c*vectors[:,0]-s*vectors[:,1],s*vectors[:,0]+c*vectors[:,1]))
            derivative=np.column_stack((-rotated[:,1],rotated[:,0]))
            residual=rotated[np.arange(len(axis)),axis]+origin[axis]-target
            jac=derivative[np.arange(len(axis)),axis]
            denom=float(jac@jac)
            if denom<=1e-12:raise ValueError('Yaw unobservable under the declared plane-assignment rule')
            delta-=float(jac@residual)/denom
        if abs(delta)>math.radians(.2):raise ValueError('Diagnostic fit left the predeclared small-angle domain')
        c,s=math.cos(delta),math.sin(delta)
        rotated=np.column_stack((c*vectors[:,0]-s*vectors[:,1],s*vectors[:,0]+c*vectors[:,1]))
        residual=rotated[np.arange(len(axis)),axis]+origin[axis]-target
        native=np.array(row['rendered_to_world'])
        native_delta=math.atan2(native[0,1],native[0,0])-math.atan2(matrix[0,1],matrix[0,0])
        groups.append({'physical_step':row['physical_step'],'payload_sha256':row['payload_sha256'],'points':len(xyz),
            'yaw_fit_points':int(keep.sum()),'excluded_points':int((~keep).sum()),'fitted_yaw_delta_rad':delta,
            'native_yaw_delta_rad':native_delta,'fitted_plane_p95_m':p95(np.abs(residual)),
            'scope':'One-axis geometric diagnostic only; no data or timestamps changed'})
    return {'schema_version':1,'scope':'Independent known-plane yaw residual fit, not formal correction',
        'analyzer_sha256':file_hash(Path(__file__)),'plane_assignment_margin_m':.05,'groups':groups,
        'max_fitted_plane_p95_m':max(g['fitted_plane_p95_m'] for g in groups)}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory');parser.add_argument('--report',required=True)
    args=parser.parse_args();result=analyze(args.directory);save_json(args.report,result)
    print(json.dumps({'groups':len(result['groups']),'max_fitted_plane_p95_m':result['max_fitted_plane_p95_m'],
        'first_groups':result['groups'][:10]},indent=2))
