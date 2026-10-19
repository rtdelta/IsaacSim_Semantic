"""Bounded phase trace. Fabric reads never flush/update world transforms."""
import time
from pathlib import Path
import numpy as np
from .common import ContractError,cjson


class BoundedTrace:
    def __init__(self,directory,max_bytes=128*1024*1024):
        self.directory=Path(directory)
        self.directory.mkdir(parents=True,exist_ok=True)
        self.max_bytes,self.bytes=max_bytes,0
        self.files={}
    def reserve(self,n):
        if self.bytes+n>self.max_bytes:
            raise ContractError('trace_budget','Diagnostic trace exceeded its predeclared byte budget')
        self.bytes+=n
    def event(self,name,kind,data):
        raw=cjson({'schema_version':1,'event_type':kind,'monotonic_ns':str(time.monotonic_ns()),'data':data})+b'\n'
        self.reserve(len(raw))
        if name not in self.files:
            self.files[name]=(self.directory/name).open('xb')
        self.files[name].write(raw)
    def payload(self,name,array):
        raw=array.tobytes()
        self.reserve(len(raw))
        path=self.directory/'payloads'/name
        path.parent.mkdir(exist_ok=True)
        with path.open('xb') as f:f.write(raw)
        return path.relative_to(self.directory).as_posix()
    def close(self):
        for f in self.files.values():f.flush();f.close()
        self.files.clear()


class StateTrace:
    def __init__(self,owner,log):
        self.owner,self.log=owner,log
        self.hierarchy=self.fabric_stage=None
        self.fabric_error=None
        try:
            import usdrt
            import isaacsim.core.experimental.utils.stage as stage_utils
            self.usdrt=usdrt
            self.fabric_stage=stage_utils.get_current_stage(backend='fabric')
            self.hierarchy=usdrt.hierarchy.IFabricHierarchy().get_fabric_hierarchy(
                self.fabric_stage.GetFabricId(),self.fabric_stage.GetStageIdAsStageId())
        except Exception as exc:
            self.fabric_error=type(exc).__name__+': '+str(exc)
    def capture(self,phase,state=None):
        from pxr import Usd,UsdGeom
        o=self.owner
        entries=[e for kind in ('cameras','lidars') for e in o.registry[kind]]
        data={'phase':phase,'physical_step':o.manager.get_num_physics_steps(),
            'simulation_time_ns':str(round(o.manager.get_simulation_time()*1e9)),
            'epoch_id':o.epoch_id,'actual_state':state,
            'usd_world':{e['sensor_id']:np.array(UsdGeom.Xformable(o.stage.GetPrimAtPath(e['prim_path'])).ComputeLocalToWorldTransform(Usd.TimeCode.Default())).tolist() for e in entries},
            'fabric_current_world':{},'fabric_components':{},'fabric_history':'no installed public read interface verified',
            'fabric_read_side_effect':'get_world_xform only; no update_world_xforms or cache creation',
            'fabric_error':self.fabric_error}
        if self.hierarchy:
            try:
                data['fabric_current_world']={e['sensor_id']:np.array(self.hierarchy.get_world_xform(self.usdrt.Sdf.Path(e['prim_path']))).tolist() for e in entries}
                for entry in entries:
                    paths=[entry['prim_path']]
                    if entry.get('render_prim_path'):paths.append(entry['render_prim_path'])
                    for path in paths:
                        prim=self.fabric_stage.GetPrimAtPath(path)
                        components={}
                        for name in ('_worldOrientation','_worldPosition','_worldScale','_localMatrix','omni:fabric:worldMatrix'):
                            attr=prim.GetAttribute(name) if prim else None
                            value=attr.Get() if attr else None
                            if value is None:components[name]=None
                            elif hasattr(value,'GetReal'):
                                components[name]={'real':float(value.GetReal()),'imaginary':list(value.GetImaginary())}
                            else:
                                try:components[name]=np.asarray(value).tolist()
                                except Exception:components[name]=str(value)
                        data['fabric_components'][path]=components
                p=self.fabric_stage.GetPrimAtPath('/ExternalSimulationTime')
                data['fabric_external_simulation_time']=str(p.GetAttribute('omni:time').Get()) if p else None
            except Exception as exc:
                data['fabric_error']=type(exc).__name__+': '+str(exc)
        self.log.event('phase_states.jsonl','state_phase',data)
    def close(self):
        self.hierarchy=self.fabric_stage=None
