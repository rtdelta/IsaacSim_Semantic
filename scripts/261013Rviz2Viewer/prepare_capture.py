"""Use the exact earlier 300-row trajectory, with existing sensor mount states."""
import argparse, copy, hashlib, json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
BASE=Path('/root/gpufree-data/semantic/output/lidar_equivalence_006/study_20261013_030531/baseline_pose')
NATIVE=Path('/root/gpufree-data/semantic/output/native_scene18_capture_005/capture_20261012_111643/delivery_300')

def prepare(destination,groups):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=False)
    metadata=json.loads((BASE/'metadata.json').read_text())
    initial=json.loads((BASE/'states.jsonl').read_text().splitlines()[0])
    source=[json.loads(x) for x in (NATIVE/'input_trajectory.jsonl').read_text().splitlines()]
    rows=[]
    for i,target in enumerate(source[:groups]):
        row=copy.deepcopy(initial)
        row.update(seq=i,t_sim_s=target['t_sim_s'],snapshot_id=f'scene18_same_motion_{i:03d}',state_revision=i,transition_kind='continuous')
        for key in ('position_world_m','quaternion_xyzw','joints_deg'):row[key]=copy.deepcopy(target[key])
        rows.append(row)
    assert len(rows)==groups
    metadata.update(recording_complete=True,last_time_s=rows[-1]['t_sim_s'],states=groups,mount_revisions={str(initial['mount_revision']):initial['mounts']},motion_source=str(NATIVE/'input_trajectory.jsonl'),motion_source_sha256=hashlib.sha256((NATIVE/'input_trajectory.jsonl').read_bytes()).hexdigest())
    trajectory=destination/'trajectory';trajectory.mkdir()
    (trajectory/'metadata.json').write_text(json.dumps(metadata,indent=2))
    (trajectory/'states.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in rows))
    spec={'name':'scene18_single06_same_motion','pose':'trajectory','trajectory':str(trajectory),'groups':groups,'timeout_s':7200,'policy':'keepalive','scene':'/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_18_terrain_fisheye_mesh.usda'}
    (destination/'input_spec.json').write_text(json.dumps(spec,indent=2))
    (destination/'motion_parameters.json').write_text(json.dumps({'sample_hz':10,'groups':groups,'logical_time_s':[0,(groups-1)/10],'world_x_speed_m_s':.1,'root_yaw_pitch_roll':{'limits_deg':[-15,15],'speed_deg_s':3,'period_s':20,'phase':'same; start 0 toward positive'},'boom_arm_bucket':{'limits_deg':[-15,15],'speed_deg_s':3},'cab_track':'initial angle held','root_rotation':'R_initial @ Rz(yaw) @ Ry(pitch) @ Rx(roll)'},indent=2))
    print(json.dumps({'spec':str(destination/'input_spec.json'),'output':str(destination/'capture')}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('destination');p.add_argument('--groups',type=int,default=300);a=p.parse_args();prepare(a.destination,a.groups)
