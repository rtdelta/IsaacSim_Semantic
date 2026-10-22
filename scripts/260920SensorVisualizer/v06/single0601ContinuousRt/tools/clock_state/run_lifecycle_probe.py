"""Isolated installed-SDK teardown probe; no production recording or scene save."""
import asyncio,json,os,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT.parent)]
from tools.experiments.storage import save
from single0601_continuous_rt.native_probe_owner import NativeProbeOwner

async def run():
    import omni.kit.app
    from isaacsim.core.rendering_manager import RenderingManager
    from single0601_continuous_rt.config import load
    spec=json.loads(os.environ['S0601_LIFECYCLE_PROBE'])
    output=ROOT/'reports/clock_state_consistency/lifecycle_probes'/spec['name'];output.mkdir(parents=True,exist_ok=False)
    job=load(ROOT/'config/mixed_pair.json');job['clock'].update(physics_hz=spec['hz'],loop_hz=spec['hz'])
    owner=NativeProbeOwner(ROOT,job);report={'spec':spec,'scope':'isolated cleanup only; no geometric qualification'}
    def snapshot():
        runner=RenderingManager._loop_runner
        return {'stage_tcps':owner.stage.GetTimeCodesPerSecond() if owner.stage else None,
            'timeline_tcps':owner.timeline.get_time_codes_per_second(),'target_framerate':owner.timeline.get_target_framerate(),
            'loop_manual_mode':runner.get_manual_mode(),'loop_step_size':runner.get_manual_step_size(),
            'settings':{k:owner.settings.get(k) for k in owner.saved_settings}}
    try:
        await asyncio.wait_for(owner.initialize(sensor_products=spec.get('sensor_products',True)),timeout=120)
        owner.timeline.play();owner.timeline.commit()
        for _ in range(24):await owner.app.next_update_async()
        owner.timeline.pause();owner.timeline.commit()
        report['before_close']=snapshot();report['expected_original']={'stage_tcps':owner.original_tcps,'timeline_tcps':owner.original_timeline_tcps,
            'target_framerate':owner.original_framerate,'loop':owner.original_loop,'settings':owner.saved_settings.copy()}
        try:await owner.close()
        except Exception as exc:report['close_exception']=str(exc)
        report['cleanup_detail']=owner.cleanup_report;report['after_close']=snapshot()
        if spec.get('commit_recheck'):
            # Isolate publication of already requested timeline changes; no app update.
            owner.timeline.commit();report['after_commit_only']=snapshot()
    except Exception as exc:report.update(failure=str(exc),traceback=traceback.format_exc())
    finally:
        save(output/'result.json',report);print('[LIFECYCLE PROBE] '+json.dumps(report),flush=True)
        omni.kit.app.get_app().post_uncancellable_quit(0 if 'cleanup_detail' in report else 2)

asyncio.ensure_future(run())
