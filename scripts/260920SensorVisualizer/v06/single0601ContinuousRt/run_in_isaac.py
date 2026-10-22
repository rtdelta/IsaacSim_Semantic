"""Single GUI entry point. CPU ROS worker and validator have no Isaac engine."""
import asyncio
import os
import json
from pathlib import Path
import sys
import traceback
PROJECT=Path(__file__).resolve().parent
sys.path.insert(0,str(PROJECT))


async def main():
    import omni.kit.app
    from single0601_continuous_rt.config import load
    from single0601_continuous_rt.engine_owner import EngineOwner
    from single0601_continuous_rt.recording import Recording
    from single0601_continuous_rt.common import save_json
    from single0601_continuous_rt.config import validate
    from single0601_continuous_rt.diagnostics import process_resources
    import gc
    import time
    matrix_path=os.environ.get('S0601_MATRIX')
    cases=json.loads(Path(matrix_path).read_text())['cases'] if matrix_path else [{'name':'manual','config':os.environ['S0601_JOB'],'motion':os.environ.get('S0601_MOTION','static')}]
    results=[]
    run_id='matrix_'+time.strftime('%Y%m%d_%H%M%S')
    code=0
    for case in cases:
        job=load(PROJECT/case['config'])
        if 'groups' in case:
            job['capture']['requested_groups']=case['groups']
        if 'diagnostics' in case:
            job['diagnostics']=case['diagnostics']
        if 'group_timeout_wall_s' in case:
            job['capture']['group_timeout_wall_s']=case['group_timeout_wall_s']
        validate(job)
        job['test_case']=case['name']
        job['motion_mode']=case['motion'] if case['name']!='manual' else 'interactive'
        os.environ['S0601_MOTION']=case['motion']
        before=process_resources()
        owner=EngineOwner(PROJECT,job)
        directory=Path(job['output']['directory'])/'partial'/owner.recording_id
        try:
            result=await Recording(owner,directory).run()
            results.append(dict(result,test_case=case['name']))
            if result['status']!='READY' and not case.get('expected_failure',False):
                code=2
                break
        except Exception:
            traceback.print_exc()
            failed=directory.parent.parent/'failed'/directory.name
            results.append({'test_case':case['name'],'recording_id':owner.recording_id,'directory':str(failed if failed.exists() else directory),
                            'status':'FAILED','expected_failure':case.get('expected_failure',False)})
            if not case.get('expected_failure',False):
                code=2
                break
        del owner
        gc.collect()
        for _ in range(3):
            await omni.kit.app.get_app().next_update_async()
        results[-1]['gui_resources_before_case']=before
        results[-1]['gui_resources_after_case']=process_resources()
        report={'schema_version':1,'run_id':run_id,'matrix_path':matrix_path,'results':results,'all_requested_cases_executed':len(results)==len(cases)}
        save_json(PROJECT/'reports/acceptance_matrix_actual.json',report)
        save_json(PROJECT/'reports'/run_id/'results.json',report)
    report={'schema_version':1,'run_id':run_id,'matrix_path':matrix_path,'results':results,'all_requested_cases_executed':len(results)==len(cases)}
    save_json(PROJECT/'reports/acceptance_matrix_actual.json',report)
    save_json(PROJECT/'reports'/run_id/'results.json',report)
    omni.kit.app.get_app().post_uncancellable_quit(code)

asyncio.ensure_future(main())
