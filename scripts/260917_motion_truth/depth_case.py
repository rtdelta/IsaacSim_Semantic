"""Static paired LiDAR depth comparison. All overrides belong to a new root layer."""
import argparse,json,traceback
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--out',type=Path,required=True)
p.add_argument('--link',required=True)
p.add_argument('--geometry',choices=['mesh','gaussian'],required=True)
a,_=p.parse_known_args();a.out.mkdir(parents=True,exist_ok=True)
r={'args':{k:str(v) for k,v in vars(a).items()},'status':'starting','views':[]}
from isaacsim import SimulationApp
app=SimulationApp({'headless':True,'fast_shutdown':True,'multi_gpu':False,'limit_cpu_threads':8,
 'width':320,'height':240,'extra_args':['--/app/settings/loadUserConfig=false','--/app/settings/persistent=false',
 '--/renderer/raytracingMotion/enabled=false','--/rtx/hydra/supportMultiTickRate=false',
 '--/app/asyncRendering=false','--/app/file/ignoreUnsavedOnExit=true',
 '--/app/player/useFixedTimeStepping=true','--/app/player/useFastMode=false','--/log/file='+str(a.out/'kit.log')]})
try:
 import numpy as np
 import omni.usd,omni.timeline,omni.replicator.core as rep
 from pxr import Gf,Sdf,Usd,UsdGeom,UsdLux,UsdPhysics
 from isaacsim.sensors.experimental.rtx import parse_generic_model_output_data
 from isaacsim.core.simulation_manager import SimulationManager
 from isaacsim.core.rendering_manager import RenderingManager
 from PIL import Image
 src='/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_11_origin03.usda'
 RenderingManager.set_dt(1/60)
 ctx=omni.usd.get_context();ctx.new_stage();stage=ctx.get_stage()
 stage.GetRootLayer().subLayerPaths=[src];stage.SetEditTarget(stage.GetRootLayer())
 stage.SetStartTimeCode(0);stage.SetEndTimeCode(600);stage.SetTimeCodesPerSecond(60);stage.SetFramesPerSecond(60)
 robot='/Excavator_Fangshan_05';link=robot+'/'+a.link
 stage.GetPrimAtPath(robot).GetVariantSets().GetVariantSet('visualization').SetVariantSelection('source_mesh')
 for layer in stage.GetUsedLayers():
  if layer!=stage.GetRootLayer() and not layer.anonymous:
   layer.SetPermissionToEdit(False);layer.SetPermissionToSave(False)
 # Capture a COMMON bound from the source mesh, independent of rendering choice.
 bound=UsdGeom.BBoxCache(Usd.TimeCode.Default(),['default','render','proxy']).ComputeWorldBound(
     stage.GetPrimAtPath(link+'/Visuals/Mesh')).ComputeAlignedRange()
 center=np.array(bound.GetMidpoint());radius=float(np.linalg.norm(np.array(bound.GetSize()))/2)
 assert radius>0
 r['center']=center.tolist();r['radius']=radius
 for prim in list(stage.GetPseudoRoot().GetChildren()):
  if str(prim.GetPath())!=robot:
   if str(prim.GetPath()) in ['/Render','/Replicator']:
    pass
   else:prim.SetActive(False)
 stage.OverridePrim('/Render').SetActive(True)
 stage.OverridePrim('/Render/Vars').SetActive(True)
 for child in stage.GetPrimAtPath('/Render/Vars').GetChildren():child.SetActive(False)
 for prim in list(stage.GetPrimAtPath(robot).GetChildren()):
  if str(prim.GetPath())!=link:prim.SetActive(False)
 for prim in list(stage.Traverse()):
  if prim.HasAPI(UsdPhysics.RigidBodyAPI):UsdPhysics.RigidBodyAPI(prim).CreateRigidBodyEnabledAttr(False)
  if prim.HasAPI(UsdPhysics.ArticulationRootAPI):prim.RemoveAPI(UsdPhysics.ArticulationRootAPI)
  if prim.IsA(UsdPhysics.Joint):prim.SetActive(False)
  if prim.GetTypeName() in ['OmniGraph','OmniLidar','OmniRadar','RenderProduct','RenderSettings']:prim.SetActive(False)
 for branch in stage.GetPrimAtPath(link+'/Visuals').GetChildren():
  name=branch.GetName()
  keep=name==('Mesh' if a.geometry=='mesh' else 'GS')
  if not keep:branch.SetActive(False)
  else:
   for prim in Usd.PrimRange(branch):
    if prim.IsA(UsdGeom.Imageable):UsdGeom.Imageable(prim).CreateVisibilityAttr().Set('inherited')
 stage.DefinePrim('/DepthProbe','Xform')
 UsdPhysics.Scene.Define(stage,'/DepthProbe/PhysicsScene')
 SimulationManager.setup_simulation(dt=1/60,device='cpu');RenderingManager.set_dt(1/60)
 UsdLux.DomeLight.Define(stage,'/DepthProbe/Light').CreateIntensityAttr(2000)
 sensor=stage.DefinePrim('/DepthProbe/Sensor','OmniLidar')
 sensor.GetReferences().AddReference('/root/gpufree-data/IsaacSim_Asset/sensor_set/lidar_set/NZ3/config/NZ3_scan.usda')
 n=41*41
 angles=np.linspace(-16,16,41)
 az,el=np.meshgrid(angles,angles);az=az.ravel();el=el.ravel()
 for attr in sensor.GetAttributes():
  if ':emitterState:' in attr.GetName():
   value=attr.Get()
   if value is not None and hasattr(value,'__len__') and len(value)>n:attr.Set(type(value)(list(value)[:n]))
 fields={'scanType':'SOLID_STATE','instantLidar':False,'numberOfEmitters':n,'numberOfChannels':n,
 'numLines':1,'numRaysPerLine':[n],'maxReturns':1,'scanRateBaseHz':10,'patternFiringRateHz':10,
 'accumulateOutputs':True,'rangeAccuracyM':0.,'nearRangeM':.01,'farRangeM':100.,'rangeOffsetM':0.,
 'outputFrameOfReference':'SENSOR','outputMotionCompensationState':'NONCOMPENSATED',
 'emitterState:s001:azimuthDeg':az.tolist(),'emitterState:s001:elevationDeg':el.tolist(),
 'emitterState:s001:fireTimeNs':np.linspace(0,99000000,n).astype(int).tolist(),'emitterState:s001:channelId':list(range(1,n+1)),
 'emitterState:s001:bank':[0]*n}
 for k,v in fields.items():assert sensor.GetAttribute('omni:sensor:Core:'+k).Set(v),k
 sensor.GetAttribute('omni:sensor:tickRate').Set(10.)
 sensor.GetAttribute('_replicator:rendervar:GenericModelOutput:channels').Set(['BASIC'])
 op=UsdGeom.Xformable(sensor).AddTransformOp()
 stage.OverridePrim('/Render/Vars/GenericModelOutput').SetActive(True)
 rv=stage.DefinePrim('/Render/Vars/GenericModelOutput','RenderVar')
 rv.CreateAttribute('sourceName',Sdf.ValueTypeNames.String).Set('GenericModelOutput')
 rv.CreateAttribute('channels',Sdf.ValueTypeNames.StringArray,custom=True).Set(['BASIC'])
 product=rep.create.render_product('/DepthProbe/Sensor',(1,1),name='DepthProbe',render_vars=['GenericModelOutput'])
 annot=rep.AnnotatorRegistry.get_annotator('GenericModelOutput',device='cpu',do_array_copy=True);annot.attach([product.path])
 cam=rep.create.camera(position=tuple(center+np.array([4*radius,0,0])),look_at=tuple(center))
 rp=rep.create.render_product(cam,(320,240))
 rgb=rep.AnnotatorRegistry.get_annotator('rgb');rgb.attach([rp])
 for layer in stage.GetUsedLayers():
  if layer!=stage.GetRootLayer() and not layer.anonymous:
   layer.SetPermissionToEdit(False);layer.SetPermissionToSave(False)
 stage.GetRootLayer().Export(str(a.out/'experiment.usda'))
 timeline=omni.timeline.get_timeline_interface();timeline.play()
 for view,direction in [('x',[1,0,0]),('y',[0,1,0]),('z',[0,0,1])]:
  delta=np.array(direction,float);origin=center+4*radius*delta
  m=Gf.Matrix4d(1);m.SetRotate(Gf.Rotation(Gf.Vec3d(1,0,0),Gf.Vec3d(*(-delta))));m.SetTranslateOnly(Gf.Vec3d(*origin));op.Set(m)
  last=None;debug={}
  for _ in range(90):
   app.update();raw=annot.get_data()
   if isinstance(raw,dict):raw=raw.get('data')
   if raw is None or not len(raw):
    debug['empty']=debug.get('empty',0)+1
    continue
   g=parse_generic_model_output_data(raw)
   key=str((int(g.numElements),int(g.scanComplete)))
   debug[key]=debug.get(key,0)+1
   if not g.scanComplete or not g.numElements:continue
   last={'xyz':np.column_stack([g.x,g.y,g.z]).copy(),'emitterId':np.array(g.emitterId).copy(),
         'flags':np.array(g.flags).copy(),'timeOffsetNs':np.array(g.timeOffsetNs).copy()}
  r['timeline_at_'+view]=timeline.get_current_time()
  r['physics_at_'+view]=SimulationManager.get_simulation_time()
  r['buffers_at_'+view]=debug
  image=np.asarray(rgb.get_data())
  if image.size:Image.fromarray(image.astype('uint8')).save(a.out/(view+'_context.png'))
  if last is None:raise RuntimeError('No returns for '+view)
  np.savez_compressed(a.out/(view+'.npz'),**last)
  r['views'].append({'view':view,'origin':origin.tolist(),'expected_rays':n,'count':len(last['xyz'])})
  image=np.asarray(rgb.get_data())
  if image.size:Image.fromarray(image.astype('uint8')).save(a.out/(view+'_context.png'))
  print(json.dumps(r['views'][-1]),flush=True)
 timeline.stop();annot.detach([product.path]);rgb.detach([rp])
 r['status']='collected'
except BaseException:
 r['status']='python_error';r['error']=traceback.format_exc();print(r['error'],flush=True)
finally:
 (a.out/'result.json').write_text(json.dumps(r,indent=2));app.close(wait_for_replicator=False)
