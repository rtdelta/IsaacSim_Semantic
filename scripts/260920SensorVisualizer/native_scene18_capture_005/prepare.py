"""Executed with installed USD Python. Creates new task inputs, never edits the scene."""
import argparse,hashlib,json,sys
from pathlib import Path
from pxr import Usd,UsdGeom
sys.path.insert(0,str(Path(__file__).resolve().parent))
from motion import trajectory

root=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args()
out=Path(a.output).resolve();out.mkdir(parents=True,exist_ok=False)
spec=json.loads((root/'config/baseline.json').read_text())
scene=Path(spec['scene']);stage=Usd.Stage.Open(str(scene));m=UsdGeom.Xformable(stage.GetPrimAtPath(spec['robot'])).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
q=m.ExtractRotationQuat().GetNormalized();xyz=list(m.ExtractTranslation());qw=[q.GetReal(),*list(q.GetImaginary())]
dependencies={l.realPath.split('[',1)[0] for l in stage.GetUsedLayers() if l.realPath}
hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in sorted(dependencies)}
for name,indices in [('smoke',[0,50,150]),('production',range(300))]:
    folder=out/name;folder.mkdir();rows=trajectory(xyz,qw,indices)
    (folder/'states.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
    job={**spec,'trajectory':str(folder/'states.jsonl'),'measure_frames':len(rows),'scene_sha256':hashes[str(scene)],
        'timeout_s':600 if name=='smoke' else 7200,'motion_profile':'smoke_extremes' if name=='smoke' else 'requested_300',
        'output_root':str(out),'source_dependencies_sha256':hashes,'initial_root_world_matrix_row':[list(r) for r in m],
        'initial_root_position_world_m':xyz,'initial_root_quaternion_wxyz':qw,
        'trajectory_sha256':hashlib.sha256((folder/'states.jsonl').read_bytes()).hexdigest()}
    (folder/'job.json').write_text(json.dumps(job,indent=2))
(out/'motion_plan.json').write_text(json.dumps({'sample_interval_s':.1,'production_groups':300,'logical_start_s':0.,'logical_end_s':29.9,'root_world_x_speed_mps':.1,'root_world_x_total_offset_m':2.99,'root_rpy_increment_deg':[-15,15],'root_rpy_speed_degps':3.,'root_rpy_initial_deg':[0,0,0],'root_rotation_convention':'R_initial * Rz(delta_yaw) * Ry(delta_pitch) * Rx(delta_roll)','joint_range_deg':[-15,15],'joint_speed_degps':3.,'waveform':'triangle, 20 second period; zero start moving positive','swing':'held initial','root_y_z':'held initial','render':'native frozen RT2 default Helper, resident products, 16 warm + 2 formal','scene_lighting':'unchanged from composed scene18','motion_model':'prescribed poses, not dynamics; zero velocities while frozen'},indent=2))
print(json.dumps({'output':str(out),'scene_hash':hashes[str(scene)],'dependencies':len(hashes),'smoke_groups':3,'production_groups':300,'initial_root_xyz':xyz}))
