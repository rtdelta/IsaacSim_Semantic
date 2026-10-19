"""New isolated causality experiment. Never save or edit referenced source layers."""
import argparse, json, math, time, traceback
from pathlib import Path
from collections import Counter
import sys
# Keep orchestration filenames out of the worker import path (stdlib queue).
sys.path=[x for x in sys.path if Path(x or ".").resolve()!=Path(__file__).resolve().parent]
p=argparse.ArgumentParser()
p.add_argument("--out",type=Path,required=True)
p.add_argument("--geometry",choices=["mesh","gaussian","synthetic"],default="mesh")
p.add_argument("--output",choices=["camera","lidar","both"],default="camera")
p.add_argument("--bvh",type=int,default=0)
p.add_argument("--multi",type=int,default=0)
p.add_argument("--per-sensor",type=int,default=0)
p.add_argument("--instant",type=int,default=0)
p.add_argument("--native-nz3",action="store_true")
p.add_argument("--frames",type=int,default=180)
p.add_argument("--warmup",type=int,default=60)
p.add_argument("--engines",default="all")
p.add_argument("--renderer",default="RealTimePathTracing")
p.add_argument("--motion",choices=["none","sensor","gaussian","both"],default="none")
p.add_argument("--speed",type=float,default=2.)
p.add_argument("--freeze-sensor",type=float,default=0.)
p.add_argument("--freeze-gaussian",type=float,default=0.)
p.add_argument("--source",default="/root/gpufree-data/IsaacSim_Asset/excavator_module_set/Sim_Fangshan_02/3dgs_usd/tooth_01_front.usd")
a,_=p.parse_known_args()
a.out=a.out.resolve()
if a.output!="lidar":raise RuntimeError("Motion worker requires isolated lidar output")
r={"args":{k:str(v) if isinstance(v,Path) else v for k,v in vars(a).items()},
   "status":"starting","events":[],"samples":[],"snapshots":{}}
def save(name,data):
    (a.out/name).write_text(json.dumps(data,indent=2,default=str))
def phase(name,**kw):
    r["phase"]=name
    r["events"].append({"name":name,"wall":time.time(),**kw})
    save("progress.json",r)
    print("CAUSALITY",name,json.dumps(kw,default=str),flush=True)
phase("app_start")
from isaacsim import SimulationApp
flags=["--/app/settings/loadUserConfig=false","--/app/settings/persistent=false",
       "--/app/asyncRendering=false","--/app/file/ignoreUnsavedOnExit=true",
       "--/app/player/useFixedTimeStepping=true","--/app/player/useFastMode=false",
       "--/renderer/raytracingMotion/enabled="+str(bool(a.bvh)).lower(),
       "--/renderer/raytracingMotion/enableHydraEngineMasking="+str(a.engines!="all").lower(),
       "--/rtx/hydra/supportMultiTickRate="+str(bool(a.multi)).lower(),
       "--/rtx/rendering/perSensorTickTlas="+str(bool(a.per_sensor)).lower(),
       "--/log/file="+str(a.out/"kit.log"),"--/log/flushStandardStreamOutput=true"]
if a.engines!="all":
    flags.append("--/renderer/raytracingMotion/enabledForHydraEngines='"+a.engines+"'")
app=SimulationApp({"headless":True,"multi_gpu":False,"fast_shutdown":True,
                   "disable_viewport_updates":True,"width":320,"height":240,
                   "renderer":a.renderer,"limit_cpu_threads":8,"extra_args":flags,
                   "shutdown_watchdog_timeout":20.0})
try:
    import carb.settings, carb.tokens
    import numpy as np
    import omni.usd, omni.timeline, omni.kit.app
    import omni.replicator.core as rep
    from pxr import Gf,Sdf,Usd,UsdGeom,UsdLux,Vt,UsdPhysics,PhysxSchema
    from isaacsim.core.simulation_manager import SimulationManager
    from isaacsim.core.rendering_manager import RenderingManager
    settings=carb.settings.get_settings()
    r["kit_build"]=omni.kit.app.get_app().get_build_version()
    r["tokens"]={k:carb.tokens.get_tokens_interface().resolve("$"+"{"+k+"}") for k in ["cache","data","logs","temp"]}
    RenderingManager.set_dt(1./60.)
    settings.set("/app/player/timeCodesPerSecond",60.)
    context=omni.usd.get_context()
    context.new_stage()
    stage=context.get_stage()
    stage.SetEditTarget(stage.GetRootLayer())
    # Remove the automatically created viewport's render requests in this new stage.
    from omni.kit.viewport.window import get_viewport_window_instances
    r["destroyed_viewports"]=[]
    for w in list(get_viewport_window_instances(None)):
        r["destroyed_viewports"].append(str(w.title))
        w.viewport_api.updates_enabled=False
        w.destroy()
    for prim in list(stage.Traverse()):
        if prim and prim.GetTypeName() in ["RenderProduct","OmniLidar","OmniRadar","OmniGraph"]:
            stage.RemovePrim(prim.GetPath())
    stage.DefinePrim("/World","Xform")
    stage.SetDefaultPrim(stage.GetPrimAtPath("/World"))
    UsdGeom.SetStageMetersPerUnit(stage,1.)
    UsdGeom.SetStageUpAxis(stage,"Z")
    stage.SetTimeCodesPerSecond(60)
    stage.SetFramesPerSecond(60)
    RenderingManager.set_dt(1./60.)
    SimulationManager.setup_simulation(dt=1./60.,device="cpu")
    stage.SetStartTimeCode(0)
    stage.SetEndTimeCode(600)
    def protect():
        r["protected_layers"]=[]
        for layer in stage.GetUsedLayers():
            if not layer.anonymous and layer!=stage.GetRootLayer():
                layer.SetPermissionToEdit(False)
                layer.SetPermissionToSave(False)
                r["protected_layers"].append(layer.identifier)
        stage.SetEditTarget(stage.GetRootLayer())
    def snap(name):
        engines=[]
        for uid in context.get_attached_hydra_engine_uids():
            d=context.get_attached_hydra_engine_description(uid)
            c=d.config
            engines.append({"uid":int(uid),"engine_type_name":d.engine_type_name,"thread_name":d.thread_name,
                "creation_index":c.creation_index,"device_mask":c.device_mask,
                "flags":int(c.flags),"flags_repr":str(c.flags),"tickrate_in_hz":c.tickrate_in_hz})
        products=[];lidars=[];gs=[]
        for prim in stage.Traverse():
            typ=prim.GetTypeName()
            if typ=="RenderProduct":
                products.append({"path":str(prim.GetPath()),
                    "relationships":{x.GetName():[str(t) for t in x.GetTargets()] for x in prim.GetRelationships()},
                    "attributes":{x.GetName():str(x.Get())[:400] for x in prim.GetAttributes() if x.HasAuthoredValueOpinion() or any(k in x.GetName().lower() for k in ["motion","shutter","engine"])}})
            elif typ=="OmniLidar":lidars.append(str(prim.GetPath()))
            elif "ParticleField" in typ:
                gs.append({"path":str(prim.GetPath()),"type":typ,"schemas":list(prim.GetAppliedSchemas())})
        windows=[]
        for w in get_viewport_window_instances(None):
            windows.append({"title":str(w.title),"updates":bool(w.viewport_api.updates_enabled)})
        data={"engines":engines,"render_products":products,"lidars":lidars,"gaussians":gs,"viewports":windows,
              "settings":{key:settings.get(key) for key in [
                "/renderer/raytracingMotion/enabled","/renderer/raytracingMotion/enableHydraEngineMasking",
                "/renderer/raytracingMotion/enabledForHydraEngines","/rtx/hydra/supportMultiTickRate",
                "/rtx/rendering/perSensorTickTlas","/app/useFabricSceneDelegate","/rtx/rendermode"]}}
        r["snapshots"][name]=data
        save("snapshot_"+name+".json",data)
        return data
    if not context.get_attached_hydra_engine_uids():
        r["explicit_engine_uid"]=omni.usd.create_hydra_engine("rtx",context)
        if r["explicit_engine_uid"]==omni.usd.HydraEngineInvalidUniqueId:
            raise RuntimeError("Explicit RTX engine creation failed")
    snap("empty")
    def box(path,center,size):
        cube=UsdGeom.Cube.Define(stage,path);cube.CreateSizeAttr(1.)
        xf=UsdGeom.XformCommonAPI(cube)
        xf.SetTranslate(Gf.Vec3d(*center));xf.SetScale(Gf.Vec3f(*size))
    for axis in range(3):
        for sign in [-1,1]:
            center=[0.]*3;center[axis]=sign*10.1
            size=[20.4]*3;size[axis]=.2
            box(f"/World/Chamber/wall_{axis}_{sign+1}",center,size)
    UsdLux.DomeLight.Define(stage,"/World/Light").CreateIntensityAttr(500)
    fill=UsdLux.SphereLight.Define(stage,"/World/Fill")
    fill.CreateIntensityAttr(3000);fill.CreateExposureAttr(10.);fill.CreateRadiusAttr(.5)
    UsdGeom.XformCommonAPI(fill).SetTranslate(Gf.Vec3d(0,-4,4))
    gaussian_body=UsdGeom.Xform.Define(stage,"/World/GaussianBody").GetPrim()
    UsdGeom.Xformable(gaussian_body).AddTranslateOp().Set(Gf.Vec3d(a.freeze_gaussian,0,0))
    if a.geometry=="gaussian":
        source=Usd.Stage.Open(a.source)
        for layer in source.GetUsedLayers():
            layer.SetPermissionToEdit(False);layer.SetPermissionToSave(False)
        source_root=source.GetDefaultPrim()
        if not source_root:
            roots=list(source.GetPseudoRoot().GetChildren())
            if len(roots)!=1:raise RuntimeError("Ambiguous Gaussian source")
            source_root=roots[0]
        asset=stage.OverridePrim("/World/GaussianBody/Asset")
        if not asset.GetReferences().AddReference(a.source,source_root.GetPath()):raise RuntimeError("Reference failed")
        protect()
        bound=UsdGeom.BBoxCache(Usd.TimeCode.Default(),["default","render","proxy"]).ComputeWorldBound(asset).ComputeAlignedRange()
        r["gaussian_bounds"]={"empty":bound.IsEmpty()}
        if not bound.IsEmpty():
            center=bound.GetMidpoint();extent=bound.GetSize()
            scale=2./max(max(extent),1e-6)
            xf=UsdGeom.Xformable(asset);xf.ClearXformOpOrder()
            op=xf.AddTransformOp()
            matrix=Gf.Matrix4d(1.);matrix.SetScale(scale)
            matrix.SetTranslateOnly(Gf.Vec3d(4,0,0)-center*scale);op.Set(matrix)
            r["gaussian_bounds"].update(center=list(center),extent=list(extent),scale=scale)
        else:op=None
    elif a.geometry=="synthetic":
        asset=stage.DefinePrim("/World/GaussianBody/Asset","ParticleField3DGaussianSplat")
        # Schemas and data attributes mirror the native type observed in the source.
        for schema in ["ParticleFieldPositionAttributeAPI","ParticleFieldPositionBaseAPI",
          "ParticleFieldOrientationAttributeAPI","ParticleFieldScaleAttributeAPI","ParticleFieldOpacityAttributeAPI",
          "ParticleFieldKernelGaussianEllipsoidAPI","ParticleFieldKernelBaseAPI",
          "ParticleFieldSphericalHarmonicsAttributeAPI","ParticleFieldRadianceBaseAPI"]:
            asset.AddAppliedSchema(schema)
        def ga(name,typ,val):
            attr=asset.GetAttribute(name)
            if not attr:attr=asset.CreateAttribute(name,typ)
            if not attr.Set(val):raise RuntimeError("Synthetic Gaussian attribute failed: "+name)
            r.setdefault("synthetic_attributes",[]).append({"name":name,"type":str(attr.GetTypeName()),"value":str(attr.Get())})
        ga("positions",Sdf.ValueTypeNames.Point3fArray,Vt.Vec3fArray([Gf.Vec3f(4,0,0)]))
        ga("scales",Sdf.ValueTypeNames.Float3Array,Vt.Vec3fArray([Gf.Vec3f(.5,.5,.5)]))
        ga("orientations",Sdf.ValueTypeNames.QuatfArray,Vt.QuatfArray([Gf.Quatf(1,0,0,0)]))
        ga("opacities",Sdf.ValueTypeNames.FloatArray,Vt.FloatArray([.99]))
        ga("radiance:sphericalHarmonicsDegree",Sdf.ValueTypeNames.Int,0)
        ga("radiance:sphericalHarmonicsCoefficients",Sdf.ValueTypeNames.Float3Array,Vt.Vec3fArray([Gf.Vec3f(1.5,0,0)]))
        ga("extent",Sdf.ValueTypeNames.Float3Array,Vt.Vec3fArray([Gf.Vec3f(2,-2,-2),Gf.Vec3f(6,2,2)]))
        op=UsdGeom.Xformable(asset).AddTranslateOp();op.Set(Gf.Vec3d(0))
    products=[];annotators=[]
    if a.output in ["lidar","both"]:
        from isaacsim.sensors.experimental.rtx import parse_generic_model_output_data
        sensor=stage.DefinePrim("/World/Sensor","OmniLidar")
        sensor.GetReferences().AddReference("/root/gpufree-data/IsaacSim_Asset/sensor_set/lidar_set/NZ3/config/NZ3_scan.usda")
        protect()
        def sa(name,val):
            attr=sensor.GetAttribute("omni:sensor:Core:"+name)
            if not attr or not attr.Set(val):raise RuntimeError("Invalid sensor attribute "+name)
        if not a.native_nz3:
            for attr in sensor.GetAttributes():
                if ":emitterState:" in attr.GetName():
                    val=attr.Get()
                    if val is not None and hasattr(val,"__len__") and len(val)>8:attr.Set(type(val)(list(val)[:8]))
            overrides={"scanType":"ROTARY","numberOfEmitters":8,"numberOfChannels":8,"numLines":1,
                "numRaysPerLine":[8],"maxReturns":1,"scanRateBaseHz":10,"patternFiringRateHz":1000,
                "emitterState:s001:azimuthDeg":[0.]*8,
                "emitterState:s001:elevationDeg":[-15.,-10.,-5.,0.,3.,5.,10.,15.],
                "emitterState:s001:fireTimeNs":[0]*8,"emitterState:s001:channelId":list(range(1,9)),
                "emitterState:s001:bank":[0]*8}
            for key,val in overrides.items():sa(key,val)
        for key,val in {"instantLidar":bool(a.instant),"accumulateOutputs":True,
            "rangeAccuracyM":0.,"nearRangeM":.1,"farRangeM":100.,"rangeOffsetM":0.,
            "outputFrameOfReference":"SENSOR","outputMotionCompensationState":"NONCOMPENSATED"}.items():sa(key,val)
        sensor.GetAttribute("omni:sensor:tickRate").Set(10.)
        sensor.GetAttribute("_replicator:rendervar:GenericModelOutput:channels").Set(["EXTRA"])
        var=stage.DefinePrim("/Render/Vars/GenericModelOutput","RenderVar")
        var.CreateAttribute("sourceName",Sdf.ValueTypeNames.String).Set("GenericModelOutput")
        var.CreateAttribute("channels",Sdf.ValueTypeNames.StringArray,custom=True).Set(["EXTRA"])
        product=rep.create.render_product("/World/Sensor",(1,1),name="OnlyLidar",render_vars=["GenericModelOutput"])
        annotator=rep.AnnotatorRegistry.get_annotator("GenericModelOutput",device="cpu",do_array_copy=True)
        annotator.attach([product.path]);products.append(product);annotators.append((annotator,product))
        r["sensor_attributes"]={attr.GetName():str(attr.Get())[:200] for attr in sensor.GetAttributes()
           if any(k in attr.GetName() for k in ["instantLidar","scanType","numberOfEmitters","tickRate","scanRate","patternFiring"])}
    if a.output in ["camera","both"]:
        camera=UsdGeom.Camera.Define(stage,"/World/DiagnosticCamera")
        camera.CreateFocalLengthAttr(35.);camera.CreateClippingRangeAttr(Gf.Vec2f(.05,100.))
        UsdGeom.Xformable(camera).AddTransformOp().Set(Gf.Matrix4d().SetLookAt(
            Gf.Vec3d(0,-5,2),Gf.Vec3d(4,0,0),Gf.Vec3d(0,0,1)).GetInverse())
        rgb_product=rep.create.render_product("/World/DiagnosticCamera",(640,480),name="OnlyCamera")
        rgb_annotator=rep.AnnotatorRegistry.get_annotator("rgb",device="cpu")
        rgb_annotator.attach([rgb_product.path]);products.append(rgb_product);annotators.append((rgb_annotator,rgb_product))
    sensor_op=UsdGeom.Xformable(sensor).AddTranslateOp()
    sensor_op.Set(Gf.Vec3d(a.freeze_sensor,0,0))
    for moving in ([sensor] if a.motion=="sensor" else [gaussian_body] if a.motion=="gaussian" else [sensor,gaussian_body] if a.motion=="both" else []):
        body=UsdPhysics.RigidBodyAPI.Apply(moving)
        body.CreateVelocityAttr(Gf.Vec3f(a.speed,0,0))
        mass=UsdPhysics.MassAPI.Apply(moving)
        mass.CreateMassAttr(1.)
        mass.CreateDiagonalInertiaAttr(Gf.Vec3f(1,1,1))
        PhysxSchema.PhysxRigidBodyAPI.Apply(moving).CreateDisableGravityAttr(True)
    protect()
    stage.GetRootLayer().Export(str(a.out/"experiment.usda"))
    created=snap("created")
    expected_lidar=1 if a.output in ["lidar","both"] else 0
    expected_products=2 if a.output=="both" else 1
    r["isolation"]={"expected_lidars":expected_lidar,"expected_render_products":expected_products}
    if len(created["lidars"])!=expected_lidar:raise RuntimeError("Unexpected active lidar")
    if len(created["render_products"])!=expected_products:raise RuntimeError("Unexpected render products")
    if any(w["updates"] for w in created["viewports"]):raise RuntimeError("Unexpected active viewport")
    if a.geometry!="mesh" and not created["gaussians"]:raise RuntimeError("No Gaussian composed")
    phase("scene_ready",engines=created["engines"],products=len(created["render_products"]))
    timeline=omni.timeline.get_timeline_interface()
    timeline.set_target_framerate(60)
    timeline.play()
    r["updates"]=[]
    seen=set()
    for frame in range(a.warmup+a.frames):
        app.update()
        sim_time=timeline.get_current_time()
        poses={}
        for label,prim in [("sensor",sensor),("gaussian",gaussian_body)]:
            mat=np.asarray(UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode(sim_time*60)))
            poses[label]=mat.tolist()
        r["updates"].append({"frame":frame,"timeline_time":sim_time,"physics_time":float(SimulationManager.get_simulation_time()),"poses":poses})
        if frame in [0,a.warmup,a.warmup+a.frames-1]:
            snap("frame_"+str(frame))
        if a.output in ["lidar","both"]:
            raw=annotator.get_data()
            if isinstance(raw,dict):raw=raw.get("data")
            if raw is not None and len(raw):
                g=parse_generic_model_output_data(raw)
                if g.numElements and g.scanComplete and int(g.timestampNs) not in seen:
                    seen.add(int(g.timestampNs))
                    xyz=np.column_stack((g.x,g.y,g.z)).copy()
                    dist=np.linalg.norm(xyz,axis=1)
                    row={"frame":frame,"measurement":frame>=a.warmup,"frame_id":int(g.frameId),
                        "count":int(g.numElements),"scan_complete":int(g.scanComplete),
                        "near_hits_lt8m":int(((dist>0)&(dist<8)).sum()),
                        "range_min":float(dist.min()),"range_max":float(dist.max()),
                        "finite":int(np.isfinite(xyz).all(axis=1).sum()),
                        "timeline_time":timeline.get_current_time(),"physics_time":float(SimulationManager.get_simulation_time())}
                    if frame>=a.warmup:
                        arrays={"xyz":xyz}
                        for field in ["emitterId","channelId","tickId","echoId","timeOffsetNs","scalar","flags","objId","matId"]:
                            try:
                                val=np.asarray(getattr(g,field))
                                if val.size:arrays[field]=val.copy()
                            except Exception as exc:
                                r.setdefault("unavailable_gmo_fields",{})[field]=str(exc)
                        if "gmo_schema" not in r:
                            r["gmo_schema"]={key:{"shape":list(val.shape),"dtype":str(val.dtype)} for key,val in arrays.items()}
                            r["gmo_member_names"]=[key for key in dir(g) if not key.startswith("_")]
                        row["frameOfReference"]=str(g.frameOfReference)
                        row["motionCompensationState"]=str(g.motionCompensationState)
                        row["frameStart"]={"timestampNs":int(g.frameStart.timestampNs),"position":list(g.frameStart.posM),"orientation":list(g.frameStart.orientation)}
                        row["frameEnd"]={"timestampNs":int(g.frameEnd.timestampNs),"position":list(g.frameEnd.posM),"orientation":list(g.frameEnd.orientation)}
                        for field in ["timestampNs","timeStampNs","frameStart","frameEnd","startTimeNs","endTimeNs"]:
                            try:row[field]=int(getattr(g,field))
                            except Exception:pass
                        if "scalar" in arrays:
                            near=(dist>0)&(dist<8)
                            row["near_scalar_mean"]=float(arrays["scalar"][near].mean()) if near.any() else None
                        name=f"cloud_{frame:04d}.npz";np.savez_compressed(a.out/name,**arrays);row["file"]=name
                    r["samples"].append(row)
        if a.output in ["camera","both"] and frame in [a.warmup,a.warmup+a.frames//2,a.warmup+a.frames-1]:
            rgb=rgb_annotator.get_data()
            if isinstance(rgb,dict):rgb=rgb.get("data")
            if rgb is not None and np.asarray(rgb).size:
                from PIL import Image
                rgb=np.asarray(rgb);name=f"rgb_{frame:04d}.png"
                Image.fromarray(rgb).save(a.out/name)
                r.setdefault("images",[]).append({"frame":frame,"file":name,"mean":float(rgb[:,:,:3].mean())})
        if frame%60==0:phase("running",frame=frame)
    final=snap("final")
    r["isolation"]["verified"]=len(final["lidars"])==expected_lidar and len(final["render_products"])==expected_products and not any(w["updates"] for w in final["viewports"])
    r["status"]="collected"
    if a.output in ["lidar","both"] and not any(s["measurement"] for s in r["samples"]):r["status"]="no_lidar_data"
    if a.output in ["camera","both"] and not r.get("images"):r["status"]="no_camera_data"
    r["loaded_native_modules"]=sorted(set(l.split()[-1] for l in Path("/proc/self/maps").read_text().splitlines()
       if any(s in l for s in ["rtx.scenedb","rtx.rtxsensor","rtx.sensors.lidar.core","librtx.hydra"])))
    phase("measurements_complete",status=r["status"])
    timeline.stop()
    for _ in range(4):app.update()
    for ann,prod in annotators:ann.detach([prod.path]);prod.destroy()
    phase("completed")
except BaseException:
    r["status"]="python_error";r["error"]=traceback.format_exc();print(r["error"],flush=True)
finally:
    save("result.json",r)
    app.close(wait_for_replicator=False)


