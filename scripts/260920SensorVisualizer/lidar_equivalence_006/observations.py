"""Read-only observations of owned formal payloads, transforms and effective USD values."""
import hashlib,json
from pathlib import Path
import numpy as np

def norm(value):
    if value is None or isinstance(value,(str,bool,int,float)):return value
    try:return [norm(x) for x in value]
    except TypeError:return str(value)

def save_cloud(out,group,sid,xyz,stamp,matrix,info=None):
    out=Path(out)/'formal_clouds'/f'{group:03d}';out.mkdir(parents=True,exist_ok=True)
    data=np.ascontiguousarray(xyz,dtype='<f4').reshape(-1,3)
    np.save(out/(sid+'.npy'),data,allow_pickle=False)
    meta={'sensor':sid,'group':group,'stamp_ns':round(stamp*1e9),'points':len(data),'sha256_xyz':hashlib.sha256(data.tobytes()).hexdigest(),'world_matrix_row':norm(matrix),'info_keys':sorted(info or {}),'source_frame_id':None,'source_frame_id_note':'Not exposed as a verified per-emission identifier by this observer'}
    (out/(sid+'.json')).write_text(json.dumps(meta,indent=2))
    return meta

def state(stage):
    from pxr import UsdGeom,Usd
    c=UsdGeom.XformCache();rows={};sensors={}
    for p in stage.Traverse():
        if p.GetTypeName()=='OmniLidar':
            sensors[str(p.GetPath())]={a.GetName():norm(a.Get()) for a in p.GetAttributes() if not a.GetName().startswith('outputs:')}
        if p.IsA(UsdGeom.Mesh):
            g=UsdGeom.Mesh(p);pts=np.asarray(g.GetPointsAttr().Get(),dtype=np.float32)
            rows[str(p.GetPath())]={'world_matrix_row':norm(c.GetLocalToWorldTransform(p)),'visibility':str(UsdGeom.Imageable(p).ComputeVisibility()),'purpose':str(UsdGeom.Imageable(p).ComputePurpose()),'points':len(pts),'points_sha256':hashlib.sha256(pts.tobytes()).hexdigest(),'face_indices_sha256':hashlib.sha256(np.asarray(g.GetFaceVertexIndicesAttr().Get(),dtype=np.int32).tobytes()).hexdigest()}
    return {'meshes':rows,'sensor_attributes':sensors,'instanced_geometry_note':'USD Traverse; instance prototype visibility is not a direct RTX hit-geometry observation'}

def save_state(out,group,stage,stamp):
    p=Path(out)/'state_evidence';p.mkdir(exist_ok=True)
    (p/f'{group:03d}.json').write_text(json.dumps({'stamp_ns':round(stamp*1e9),**state(stage)},indent=2))

def install_legacy(out):
    from sensor_visualizer_v06.scene import SceneStepper
    from sensor_visualizer_v06.sensors import SensorDrivers
    original=SceneStepper.capture
    async def capture(self,group,stamp_ns):
        arrays,bundle=await original(self,group,stamp_ns)
        for sid,meta in bundle['lidars'].items():save_cloud(out,group,sid,arrays['lidar/'+sid],stamp_ns/1e9,meta['to_world'])
        save_state(out,group,self.stage,stamp_ns/1e9)
        return arrays,bundle
    SceneStepper.capture=capture
    # Inspect the already-materialized copy. Do not ask the GPU for a second scan.
    original_copy=SensorDrivers._copy_host
    def copy(self,value,sensor):
        result=original_copy(self,value,sensor)
        if sensor.startswith('lidars/'):
            p=Path(out)/'owned_copy_hashes.jsonl'
            with p.open('a') as f:f.write(json.dumps({'sensor':sensor,'points':len(result),'sha256':hashlib.sha256(np.ascontiguousarray(result,dtype='<f4').tobytes()).hexdigest()})+'\n')
        return result
    SensorDrivers._copy_host=copy
