"""Render-only LiDAR prims driven one-way by actual post-physics mount poses."""
import numpy as np
from .common import ContractError,digest
from .sensor_registry import attributes


class RenderPoseRig:
    def __init__(self,stage,layer,registry):
        from pxr import Usd,UsdGeom,UsdPhysics
        self.stage,self.layer=stage,layer
        self.ops={};self.metadata=[]
        namespace='/Single0601ContinuousRtRenderRig'
        if stage.GetPrimAtPath(namespace):
            raise ContractError('rig_namespace','Render rig namespace already exists outside this owner')
        with Usd.EditContext(stage,layer):
            UsdGeom.Xform.Define(stage,namespace)
            for entry in registry['lidars']:
                source=entry['prim_path']
                path=namespace+'/'+entry['id']
                prim=stage.DefinePrim(path,'OmniLidar')
                prim.GetReferences().AddInternalReference(source)
                if prim.HasAPI(UsdPhysics.RigidBodyAPI) or prim.HasAPI(UsdPhysics.ArticulationRootAPI):
                    raise ContractError('rig_physics','Render-only sensor must not introduce another physics actor')
                before=attributes(stage.GetPrimAtPath(source))
                after=attributes(prim)
                if digest(before)!=digest(after):
                    raise ContractError('rig_parameters','Referenced render sensor differs from original native parameters')
                self.ops[entry['sensor_id']]=UsdGeom.Xformable(prim).MakeMatrixXform()
                entry.update(render_prim_path=path,render_pose_mode='usd_rig',
                    render_pose_source='immutable actual sensor world matrix in PHYSICS_POST_STEP; no prediction or timestamp change')
                self.metadata.append({'sensor_id':entry['sensor_id'],'source_prim_path':source,
                    'render_prim_path':path,'native_parameters_sha256':digest(before),
                    'parameters_identical':True,'scope':'same engine render-only sensor; original physical mount retained'})
    def update(self,actual_matrices):
        from pxr import Usd,Gf
        with Usd.EditContext(self.stage,self.layer):
            for sid,op in self.ops.items():
                matrix=np.asarray(actual_matrices[sid],dtype=float)
                if matrix.shape!=(4,4) or not np.isfinite(matrix).all():
                    raise ContractError('rig_actual_pose','Actual render rig input must be a finite world matrix')
                op.Set(Gf.Matrix4d(matrix.tolist()))
    def close(self):
        self.ops.clear();self.stage=self.layer=None
