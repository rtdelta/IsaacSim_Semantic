"""Diagnostic only: isolate parameter causes of empty RTX buffers."""
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from isaacsim import SimulationApp
app=SimulationApp(dict(headless=True,extra_args=['--/renderer/raytracingMotion/enabled=false',
    '--/rtx/hydra/supportMultiTickRate=false','--/rtx/rendering/perSensorTickTlas=false']))
import numpy as np
import omni.usd,omni.timeline
from pxr import UsdGeom,Sdf
from isaac_utils import load_nz3,make_chamber
from isaacsim.sensors.experimental.rtx import parse_generic_model_output_data
from isaacsim.sensors.experimental.rtx.sensor_checker import SensorCheckerUtil,ModelInfo
info=ModelInfo();info.modelName='lidar.core';info.modelVendor='nv';info.modelVersion='1.0';info.schemaVersion='1.0'
checker=SensorCheckerUtil()
print('NZ3_CHECKER_INIT_DEFAULT',checker.init(info),flush=True)
impl=next(Path('/root/isaacsim/extscache').glob('omni.sensors.nv.lidar-*/bin/model_plugins/librtx.sensors.lidar.core.nv.chk.impl.so'))
print('NZ3_CHECKER_INIT_EXPLICIT',checker.init(info,str(impl)),flush=True)
print('NZ3_CHECKER_VALIDATE',checker.validateParams(str(ROOT/'assets/NZ3/config/NZ3_scan.usda'),'/OmniLidar'),flush=True)

stage=omni.usd.get_context().get_stage()
UsdGeom.SetStageMetersPerUnit(stage,1);stage.DefinePrim('/World','Xform')
make_chamber(stage)
variants={
 'baseline':{},
 'keep_invalid':{'skipDroppingInvalidPoints':True},
 'explicit_range':{'rangeCount':1,'rangesMinM':[.2],'rangesMaxM':[115.]},
 'range_precision':{'rangeResolutionM':.004,'rangeAccuracyM':.001},
 'non_instant':{'instantLidar':False},
 'default_threshold':{'minReflectance':.1,'minReflectionRangeM':200.},
}
sensors={};annots={}
for name,attrs in variants.items():
    lidar,sensor=load_nz3('/World/'+name)
    p=stage.GetPrimAtPath('/World/'+name+'/sensor')
    for key,value in attrs.items():p.GetAttribute('omni:sensor:Core:'+key).Set(value)
    if name=='explicit_range':p.GetAttribute('omni:sensor:Core:emitterState:s001:rangeId').Set([0]*46080)
    sensors[name]=(lidar,sensor)
    annots[name]=sensor.attach_annotators('generic-model-output')['generic-model-output']
timeline=omni.timeline.get_timeline_interface();timeline.play()
result={}
for i in range(160):
    app.update()
    if i not in (40,80,159):continue
    for name,annot in annots.items():
        raw=annot.get_data()
        if isinstance(raw,dict):raw=raw.get('data')
        if raw is None or not len(raw):continue
        g=parse_generic_model_output_data(raw)
        info={'frame':int(g.frameId),'elements':int(g.numElements),'scan_complete':int(g.scanComplete)}
        if g.numElements:
            xyz=np.column_stack((g.x,g.y,g.z))
            info.update(finite=int(np.isfinite(xyz).all(axis=1).sum()),
                        first_points=xyz[:3].tolist(),nonzero=int((np.linalg.norm(xyz,axis=1)>0).sum()))
        result[name]=info
    print('NZ3_PROBE',i,json.dumps(result),flush=True)
(ROOT/'reports/isaacsim/parameter_probe.json').write_text(json.dumps(result,indent=2))
timeline.stop();app.close(wait_for_replicator=False,exit_code=0)
