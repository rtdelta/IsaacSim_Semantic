"""Compare rotary and instantaneous return sensitivity in one isolated chamber."""
import json
from pathlib import Path
from isaacsim import SimulationApp
app=SimulationApp(dict(headless=True,multi_gpu=False,fast_shutdown=True,width=640,height=480,
    extra_args=['--/renderer/raytracingMotion/enabled=false','--/rtx/hydra/supportMultiTickRate=false',
                '--/rtx/rendering/perSensorTickTlas=false']))
import numpy as np
import omni.usd, omni.timeline, omni.replicator.core as rep
from pxr import UsdGeom, Gf, Sdf
from isaacsim.sensors.experimental.rtx import parse_generic_model_output_data
root=Path(__file__).resolve().parents[1]
omni.usd.get_context().new_stage();stage=omni.usd.get_context().get_stage()
stage.DefinePrim('/World','Xform');UsdGeom.SetStageMetersPerUnit(stage,1);UsdGeom.SetStageUpAxis(stage,'Z')
for axis in range(3):
 for sign in (-1,1):
  c=UsdGeom.Cube.Define(stage,f'/World/wall_{axis}_{sign+1}');c.CreateSizeAttr(1)
  p=[0.,0.,0.];p[axis]=sign*2.1;scale=[4.4]*3;scale[axis]=.2
  xf=UsdGeom.XformCommonAPI(c);xf.SetTranslate(Gf.Vec3d(*p));xf.SetScale(Gf.Vec3f(*scale))
cases=[('rotary',None),('original',{'peakPowerW':10.}),
       ('low_threshold',{'peakPowerW':10.,'minReflectance':.000001}),
       ('peak_power',{'peakPowerW':8920.}),('single_return',{'peakPowerW':10.,'maxReturns':1}),
       ('reference_range',{'peakPowerW':10.,'minReflectionRangeM':70.})]
rts=[];P='omni:sensor:Core:'
for name,changes in cases:
 mount=stage.DefinePrim('/World/'+name,'Xform')
 if changes is None:
  sensor=stage.DefinePrim('/World/'+name+'/sensor','OmniLidar')
  sensor.GetReferences().AddReference(str(root/'reference/MyOS0_config.usda'))
 else:
  mount.GetReferences().AddReference(str(root/'assets/MyAiry/MyAiry.usda'))
  sensor=stage.GetPrimAtPath('/World/'+name+'/sensor')
 for k,v in (changes or {}).items():sensor.GetAttribute(P+k).Set(v)
 sensor.CreateAttribute(P+'elementsCoordsType',Sdf.ValueTypeNames.Token).Set('CARTESIAN')
 sensor.CreateAttribute(P+'outputFrameOfReference',Sdf.ValueTypeNames.Token).Set('SENSOR')
 sensor.CreateAttribute('_replicator:rendervar:GenericModelOutput:channels',Sdf.ValueTypeNames.StringArray).Set(['BASIC'])
 product=rep.create.render_product(str(sensor.GetPath()),(1,1),name=name,render_vars=['GenericModelOutput'])
 annot=rep.AnnotatorRegistry.get_annotator('GenericModelOutput',device='cpu',do_array_copy=True);annot.attach([product.path])
 rts.append((name,product,annot))
timeline=omni.timeline.get_timeline_interface();timeline.play();results={};seen={}
for step in range(150):
 app.update()
 if step<50:continue
 for name,product,annot in rts:
  raw=annot.get_data()
  if isinstance(raw,dict):raw=raw.get('data')
  if raw is None or not len(raw):continue
  g=parse_generic_model_output_data(raw)
  if not g.scanComplete or not g.numElements:continue
  xyz=np.column_stack((g.x,g.y,g.z));ids=np.asarray(g.emitterId);d=np.linalg.norm(xyz,axis=1)
  key=int(g.frameId)
  if key in seen.setdefault(name,set()):continue
  seen[name].add(key)
  if name in results and results[name]['points']>=len(ids):continue
  results[name]=dict(points=len(ids),unique_emitters=len(np.unique(ids)),range_quantiles=np.quantile(d,[0,.5,1]).tolist(),
                     echo_counts={str(int(v)):int(n) for v,n in zip(*np.unique(np.asarray(g.echoId),return_counts=True))})
report=dict(results=results,fresh_frames={k:len(v) for k,v in seen.items()})
(root/'reports/sensitivity_probe.json').write_text(json.dumps(report,indent=2))
print('AIRY_SENSITIVITY',json.dumps(report),flush=True)
timeline.stop()
for _,product,annot in rts:annot.detach([product.path]);product.destroy()
app.close()
