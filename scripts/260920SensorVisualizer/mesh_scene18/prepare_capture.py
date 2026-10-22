"""Generate a three-pose trajectory from scene18's own sensor mounts."""
import hashlib,json,os,sys
from pathlib import Path
from pxr import Gf,Usd,UsdGeom
BASE=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
FROZEN=BASE/'single06_lab/frozen_runtime'
sys.path.insert(0,str(FROZEN))
from sensor_visualizer_v06.robot.discovery import discover_sensors
from sensor_visualizer_v06.robot.sensor_pose import SensorPoses
from sensor_visualizer_v06.contracts import load_job

case=Path(CASE_OUTPUT)
case.mkdir(parents=True,exist_ok=False)
scene=Path('/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_18_terrain_fisheye_mesh.usda')
stage=Usd.Stage.Open(str(scene))
sensors=discover_sensors(stage,robot_path='/World/Excavator')
for cid,name in [('front','Front'),('back','Rear'),('left','Left'),('right','Right')]:
    sensors.append({'id':'camera_'+cid,'prim_path':'/World/Excavator/swing_link/Fisheye'+name})
poses=SensorPoses(stage,sensors,str(case),lambda:0.)
mounts=poses.snapshot();poses.close()
base=UsdGeom.Xformable(stage.GetPrimAtPath('/World/Excavator')).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
traj=case/'input_trajectory';traj.mkdir()
rows=[]
for group,(sign,xyz,rpy) in enumerate([(0,(0,0,0),(0,0,0)),(1,(.2,-.1,.1),(3,-4,10)),(-1,(-.2,.1,.05),(-3,4,-10))]):
    m=Gf.Matrix4d(base)
    rotate=Gf.Rotation(Gf.Vec3d(1,0,0),rpy[0])*Gf.Rotation(Gf.Vec3d(0,1,0),rpy[1])*Gf.Rotation(Gf.Vec3d(0,0,1),rpy[2])
    m=Gf.Matrix4d().SetRotate(rotate)*m
    m.SetTranslateOnly(base.ExtractTranslation()+Gf.Vec3d(*xyz));q=m.ExtractRotationQuat().GetNormalized()
    rows.append({'schema_version':1,'session_id':'scene18_validation','snapshot_id':f'scene18_pose_{group}','seq':group,'state_revision':group,'mount_revision':0,'t_sim_s':group/10,'position_world_m':list(m.ExtractTranslation()),'quaternion_xyzw':[*q.GetImaginary(),q.GetReal()],'joints_deg':{n:sign*15. for n in ('boom','arm','bucket')},'transition_kind':'step'})
metadata={'schema_version':1,'recording_complete':True,'joint_names':['boom','arm','bucket'],'mount_revisions':{'0':mounts},'initial_mounts':mounts,'asset_manifest':{'root_sha256':hashlib.sha256(scene.read_bytes()).hexdigest()},'last_time_s':.2,'rows':3}
(traj/'metadata.json').write_text(json.dumps(metadata,indent=2))
(traj/'states.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
job=load_job(overrides={'scene':str(scene),'groups':3,'output_directory':str(case/'captures'),'capture':{'resource_policy':'keepalive'},'diagnostics':{'level':'diagnostic'},'replay':{'mode':'offline','trajectory':str(traj),'control_path':str(case/'control.json'),'status_path':str(case/'capture_status.json'),'socket':str(case/'engine.sock')}})
(case/'job.json').write_text(json.dumps(job,indent=2))
(case/'config.json').write_text(json.dumps({'family':'v06','requested_groups':3,'id':'scene18_mesh_motion_smoke'}))
print(json.dumps({'case':str(case),'job':str(case/'job.json'),'poses':3,'mounts':len(mounts)}))
