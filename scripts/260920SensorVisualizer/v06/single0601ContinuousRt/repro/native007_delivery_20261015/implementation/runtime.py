"""Read-only metadata shared between independent and framework collectors.

No owner/backend, state ledger, geometry or scheduling imports.
"""
import hashlib,json,math,platform,subprocess,sys
from pathlib import Path
from tools.native_rotation_localization.io import save,sha

SETTINGS=['/app/settings/fabricDefaultSimPeriodNumerator','/app/settings/fabricDefaultSimPeriodDenominator',
 '/app/runLoops/main/rateLimitEnabled','/app/runLoops/main/rateLimitFrequency','/app/player/useFixedTimeStepping',
 '/app/player/useFastMode','/app/asyncRendering','/rtx/hydra/supportMultiTickRate','/renderer/raytracingMotion/enabled',
 '/renderer/raytracingMotion/enableHydraEngineMasking','/renderer/raytracingMotion/enabledForHydraEngines',
 '/rtx/rendering/perSensorTickTlas','/rtx/scenedb/maxHistoryTransformCount','/rtx/rendermode','/rtx/post/dlss/execMode',
 '/rtx/post/aa/op','/rtx-transient/dlssg/enabled','/rtx/post/motionblur/enabled','/app/sensors/nv/lidar/outputBufferOnGPU',
 '/rtx/rtxsensor/useHydraTimeAlways']
ANNOTATORS=['IsaacExtractRTXSensorPointCloud','GenericModelOutput','IsaacReadSimulationTime','ReferenceTime']
E_SETTINGS={'/rtx/rendermode':'RealTimePathTracing','/rtx/post/dlss/execMode':2,'/rtx/post/aa/op':3,
 '/rtx-transient/dlssg/enabled':False,'/rtx/post/motionblur/enabled':False,'/rtx/hydra/supportMultiTickRate':True,
 '/rtx/rendering/perSensorTickTlas':True,'/app/asyncRendering':False,'/renderer/raytracingMotion/enabled':True,
 '/rtx/scenedb/maxHistoryTransformCount':64}
WALLS=[{'axis':a,'coordinate_m':c,'center_m':[c+math.copysign(.01,c) if j==a else 0. for j in range(3)],
 'halfsize_m':[.01 if j==a else 20. for j in range(3)]} for a,c in [(0,10.),(0,-7.),(1,8.),(1,-11.),(2,6.),(2,-4.)]]

def safe(v):
    if v is None or isinstance(v,(str,bool,int)):return v
    if isinstance(v,float):return v if math.isfinite(v) else {'nonfinite':str(v)}
    if isinstance(v,dict):return {str(k):safe(x) for k,x in v.items()}
    try:return [safe(x) for x in v]
    except TypeError:return str(v)

def settings(stage):
    import carb.settings,omni.timeline
    from isaacsim.core.rendering_manager import RenderingManager
    s=carb.settings.get_settings();t=omni.timeline.get_timeline_interface();r=RenderingManager._loop_runner
    return {'settings':{k:safe(s.get(k)) for k in SETTINGS},'stage_tcps':stage.GetTimeCodesPerSecond(),
        'timeline_tcps':t.get_time_codes_per_second(),'target_framerate':t.get_target_framerate(),
        'loop_manual_mode':r.get_manual_mode(),'loop_manual_step_size':r.get_manual_step_size(),
        'auto_update':t.get_auto_update() if hasattr(t,'get_auto_update') else {'unavailable':'installed Timeline has no get_auto_update; actual progression checked'},
        'play_every_frame':t.get_play_every_frame() if hasattr(t,'get_play_every_frame') else {'unavailable':'installed API'}}

def capture_settings(directory,stage):
    """Freeze effective settings at the same post-warmup lifecycle point as E."""
    directory=Path(directory)
    fingerprint=json.loads((directory/'configuration_fingerprint.json').read_text())
    save(directory/'configuration_fingerprint_before_warmup.json',fingerprint)
    fingerprint['effective']=settings(stage)
    save(directory/'effective_settings_capture_native.json',fingerprint['effective'])
    save(directory/'configuration_fingerprint.json',fingerprint)

def record(directory,stage,sensor_path,product_path,spec,initialization):
    import omni.kit.app
    from pxr import UsdGeom
    directory=Path(directory);app=omni.kit.app.get_app();em=app.get_extension_manager()
    names=['omni.replicator.core','omni.sensors.nv.common','omni.sensors.nv.lidar','isaacsim.core.simulation_manager','isaacsim.core.rendering_manager','isaacsim.sensors.experimental.rtx','usdrt.scenegraph']
    versions={}
    for name in names:
        ident=em.get_enabled_extension_id(name);versions[name]=em.get_extension_dict(ident).get('package',{}).get('version') if ident else None
    gpu=subprocess.check_output(['nvidia-smi','--query-gpu=uuid,name,driver_version,memory.total','--format=csv,noheader,nounits'],text=True).strip()
    environment={'isaac_sim':Path('/root/isaacsim/VERSION').read_text().strip(),'kit':app.get_build_version(),'extensions':versions,
        'gpu':gpu,'python':platform.python_version(),'startup':'isaacsim.exp.full.kit GUI DISPLAY=:20; registry disabled; same native launch arguments',
        'native_api_availability':{}}
    import isaacsim.sensors.experimental.rtx as rtx
    environment['native_api_availability']={n:hasattr(rtx,n) for n in ('Lidar','LidarSensor','parse_generic_model_output_data')}
    save(directory/'environment.json',environment);save(directory/'effective_settings.json',settings(stage))
    prim=stage.GetPrimAtPath(sensor_path)
    attrs={a.GetName():{'value':safe(a.Get()),'usd_type':str(a.GetTypeName())} for a in prim.GetAttributes()
        if (a.GetName().startswith('omni:sensor:') or a.GetName().startswith('_replicator:')) and a.Get() is not None}
    save(directory/'sensor_manifest.json',{'source_asset':spec['scene_asset'],'source_prim':spec['source_prim'],'attributes':attrs})
    attributes_sha=hashlib.sha256(json.dumps(attrs,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    dependencies=[]
    for p in sorted(set([spec['scene_asset']]+[l.realPath for l in stage.GetUsedLayers() if l.realPath])):
        f=Path(p);dependencies.append({'path':p,'sha256':sha(f) if f.is_file() else None,'bytes':f.stat().st_size if f.is_file() else None})
    save(directory/'scene_manifest.json',{'walls':WALLS,'meters_per_unit':UsdGeom.GetStageMetersPerUnit(stage),'up_axis':str(UsdGeom.GetStageUpAxis(stage)),'dependencies':dependencies})
    rp=stage.GetPrimAtPath(product_path);variables=[]
    for path in rp.GetRelationship('orderedVars').GetTargets():
        v=stage.GetPrimAtPath(path);variables.append({'name':str(path).split('/')[-1],'attributes':{a.GetName():safe(a.Get()) for a in v.GetAttributes() if a.Get() is not None}})
    topo={'product_count':1,'resolution':[300,300],'annotators_in_attach_order':ANNOTATORS,'device':'cpu','do_array_copy':True,
        'render_vars':variables,'sensor_channels':safe(prim.GetAttribute('_replicator:rendervar:GenericModelOutput:channels').Get()),'initialization':initialization}
    save(directory/'topology.json',topo)
    forbidden=[n for n in sys.modules if n=='single0601_continuous_rt' or n.startswith(('single0601_continuous_rt.','sensor_visualizer_v06.','tools.clock_state.','tools.experiments.'))]
    sources=[];project=Path(__file__).resolve().parents[2]
    for name,module in sorted(sys.modules.items()):
        f=getattr(module,'__file__',None)
        if f:
            p=Path(f)
            if p.suffix=='.py' and project in p.parents and p.is_file():sources.append({'module':name,'path':p.relative_to(project).as_posix(),'sha256':sha(p)})
    sources.append({'module':'entry','path':spec['entry'],'sha256':sha(project/spec['entry'])})
    save(directory/'source_manifest.json',{'modules':sources,'forbidden_framework_modules_loaded':forbidden,'minimal_dependency_boundary_passed':not forbidden if spec['group'].startswith('M') else None})
    save(directory/'configuration_fingerprint.json',{'sensor_attributes_sha256':attributes_sha,'environment':environment,'effective':settings(stage),
        'topology':topo,'scene':{'walls':WALLS,'dependencies':dependencies}})
