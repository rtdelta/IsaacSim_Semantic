"""Independent frozen XYZ vs known room surfaces, including real previous step."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from single0601_continuous_rt.common import save_json,file_hash


def p95(values):
    values=np.sort(values)
    return float(values[max(0,math.ceil(.95*len(values))-1)]) if len(values) else None


def analyze(directory):
    directory=Path(directory).resolve()
    render=json.loads((directory/'render_profile.json').read_text())
    walls=render['room_geometry']
    frames=[json.loads(line)['data'] for line in (directory/'native_events.jsonl').read_text().splitlines()]
    states={s['physical_step']:s['actual_state'] for s in (json.loads(line)['data'] for line in (directory/'phase_states.jsonl').read_text().splitlines()) if s['actual_state'] is not None}
    groups=[];hashes=[]
    def error(points,matrix):
        world=np.column_stack((points,np.ones(len(points)))) @ np.array(matrix)
        distances=np.column_stack([np.abs(world[:,wall['axis']]-wall['coordinate_m']) for wall in walls])
        return p95(distances.min(axis=1))
    for frame in frames:
        if frame['kind']!='lidar':continue
        path=(directory/frame['payload_path']).resolve()
        if directory not in path.parents:raise ValueError('XYZ escaped diagnostic scope')
        raw=path.read_bytes()
        if len(raw)!=frame['raw_nbytes'] or hashlib.sha256(raw).hexdigest()!=frame['payload_sha256']:
            raise ValueError('Frozen raw XYZ hash/layout mismatch')
        points=np.frombuffer(raw,dtype='<f4').reshape(frame['shape'])
        if not len(points) or not np.isfinite(points).all():raise ValueError('Known room requires finite nonempty points')
        current=error(points,frame['historical_to_world'])
        native=error(points,frame['rendered_to_world'])
        previous=states.get(frame['physical_step']-1)
        old=error(points,previous['sensor_world_matrices_usd'][frame['sensor_id']]) if previous else None
        groups.append({'physical_step':frame['physical_step'],'source_time_ns':frame['source_time_ns'],'points':len(points),
            'actual_pose_point_plane_p95_m':current,'native_pose_point_plane_p95_m':native,
            'previous_actual_pose_point_plane_p95_m':old,'extractor_rotation_error_rad':frame['rotation_error_rad'],
            'actual_passes_5mm':current<=.005,'native_passes_5mm':native<=.005})
        hashes.append({'path':frame['payload_path'],'sha256':hashlib.sha256(raw).hexdigest()})
    result={'schema_version':1,'scope':'Independent XYZ/known surfaces; diagnostic geometry only',
        'analyzer_sha256':file_hash(Path(__file__)),'input_native_events_sha256':file_hash(directory/'native_events.jsonl'),
        'groups':groups,'input_xyz':hashes,'groups_seen':len(groups),
        'actual_pose_all_groups_pass_5mm':bool(groups) and all(g['actual_passes_5mm'] for g in groups),
        'native_pose_all_groups_pass_5mm':bool(groups) and all(g['native_passes_5mm'] for g in groups),
        'actual_pose_max_group_p95_m':max((g['actual_pose_point_plane_p95_m'] for g in groups),default=None),
        'native_pose_max_group_p95_m':max((g['native_pose_point_plane_p95_m'] for g in groups),default=None),
        'previous_step_negative_groups':sum(g['previous_actual_pose_point_plane_p95_m'] is not None and g['previous_actual_pose_point_plane_p95_m']>.005 for g in groups)}
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory');p.add_argument('--report',required=True)
    args=p.parse_args();result=analyze(args.directory);save_json(args.report,result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('groups','input_xyz')},indent=2))
