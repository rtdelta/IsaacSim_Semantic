"""Configuration reconnaissance only; not a member of either test group."""
import asyncio,json,os,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT.parent)]
from tools.native_instant_baseline.runtime import record,settings
from tools.native_instant_baseline.io import save
from single0601_continuous_rt.native_probe_owner import NativeProbeOwner

async def run():
    import omni.kit.app
    from single0601_continuous_rt.config import load
    spec=json.loads(os.environ['NIB_PROBE_SPEC']);out=ROOT/'reports/native_instant_baseline'/spec['name'];out.mkdir(parents=True,exist_ok=False)
    import carb.settings
    owner=NativeProbeOwner(ROOT,load(ROOT/'config/mixed_pair.json'));report={'startup_history_count_without_launch_override':carb.settings.get_settings().get('/rtx/scenedb/maxHistoryTransformCount')}
    try:
        await asyncio.wait_for(owner.initialize(),180)
        owner.timeline.play();owner.timeline.commit()
        for _ in range(24):await owner.app.next_update_async()
        record(out,owner.stage,'/RecoverySensor',owner.backend.products[0].path,spec,{'initial_physics_updates':6,'static_updates':24})
        report['effective']=settings(owner.stage)
        owner.timeline.pause();owner.timeline.commit()
        report['paused_effective']=settings(owner.stage);report['passed']=True
    except Exception as exc:report.update(passed=False,error=str(exc),traceback=traceback.format_exc())
    finally:
        try:await owner.close();report['cleanup']=owner.cleanup_report
        except Exception as exc:report['cleanup']={'passed':False,'error':str(exc),**getattr(owner,'cleanup_report',{})}
        save(out/'probe_result.json',report);omni.kit.app.get_app().post_uncancellable_quit(0 if report.get('passed') and report['cleanup']['passed'] else 2)
asyncio.ensure_future(run())
