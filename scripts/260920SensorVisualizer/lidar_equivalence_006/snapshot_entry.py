"""Capture actual initialized baseline pose and complete mounts; no capture or movement commands."""
import asyncio,json,math,os,sys,traceback,uuid,threading
from pathlib import Path
R=Path(__file__).resolve().parent
sys.path[:0]=[str(R/'legacy/frozen_runtime'),str(R)]

async def main():
    import omni.kit.app
    from sensor_visualizer_v06.contracts import load_job
    from sensor_visualizer_v06.scene import SceneStepper
    from sensor_visualizer_v06.diagnostics import RunDiagnostics
    from observations import state
    from pxr import Usd,UsdGeom
    import hashlib
    job=load_job(os.environ['SV06_JOB']);out=Path(job['output_directory']);out.mkdir(parents=True,exist_ok=True)
    diag=RunDiagnostics(out,job['diagnostics'],R/'legacy/frozen_runtime');scene=None;code=1
    try:
        scene=SceneStepper(R/'legacy/frozen_runtime',job,diag)
        await scene.initialize(sensor_products=False)
        snap=scene.motion.snapshot(scene.native_time());names={j['name'] for j in scene.motion.config['joints']}
        base={'schema_version':1,'snapshot_id':uuid.uuid4().hex,'state_revision':0,'mount_revision':scene.poses.revision,'position_world_m':list(snap['root_position']),'quaternion_xyzw':list(snap['root_xyzw']),'joints_deg':{n:math.degrees(v) for n,v in zip(snap['names'],snap['positions']) if n in names},'mounts':scene.poses.snapshot(),'transition_kind':'direct'}
        rows=[dict(base,t_sim_s=i*.1,seq=i) for i in range(3)]
        (out/'states.jsonl').write_text(''.join(json.dumps(v)+'\n' for v in rows))
        (out/'metadata.json').write_text(json.dumps({'schema_version':1,'recording_complete':True,'joint_names':list(base['joints_deg']),'initial_mounts':base['mounts'],'mount_revisions':{str(base['mount_revision']):base['mounts']},'asset_manifest':scene.asset_manifest},indent=2))
        (out/'baseline_state.json').write_text(json.dumps(state(scene.stage),indent=2))
        paths={l.realPath.split('[',1)[0] for l in scene.stage.GetUsedLayers() if l.realPath}
        (out/'dependencies.json').write_text(json.dumps({p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths if Path(p).is_file()},indent=2))
        (out/'ready.json').write_text(json.dumps({'ready':True,'root':base['position_world_m'],'joints':base['joints_deg'],'mounts':len(base['mounts'])},indent=2));code=0
    except BaseException:
        (out/'failure.txt').write_text(traceback.format_exc());traceback.print_exc()
    finally:
        if scene:
            try:await scene.close()
            except Exception:traceback.print_exc()
        diag.close()
        timer=threading.Timer(20,lambda:os._exit(code));timer.daemon=True;timer.start()
        omni.kit.app.get_app().post_quit(code)
task=asyncio.ensure_future(main())
