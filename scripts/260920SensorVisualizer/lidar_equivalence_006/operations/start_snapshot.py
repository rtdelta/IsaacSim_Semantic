import json,os,subprocess,sys,time
from pathlib import Path
R=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/lidar_equivalence_006')
for p in Path('/proc').glob('[0-9]*/cmdline'):
    try:
        if p.read_bytes().split(b'\0')[0].endswith(b'/kit/kit'):raise RuntimeError('Existing Kit was not stopped')
    except OSError:pass
out=Path('/root/gpufree-data/semantic/output/lidar_equivalence_006')/('study_'+time.strftime('%Y%m%d_%H%M%S',time.gmtime()))
out.mkdir(parents=True,exist_ok=False);snap=out/'baseline_pose';snap.mkdir()
sys.path.insert(0,str(R/'legacy/frozen_runtime'))
from sensor_visualizer_v06.contracts import load_job
from run_capture import launch_spec
job=load_job(R/'legacy/frozen_runtime/config/offline.json');job.update(scene='/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_18_terrain_fisheye_mesh.usda',groups=3,output_directory=str(snap));job['render']['background_dome']=None
(snap/'job.json').write_text(json.dumps(job,indent=2));args,env,install=launch_spec(snap/'job.json',entry=R/'snapshot_entry.py')
with (snap/'engine.log').open('xb') as log:
    p=subprocess.Popen(args,env=env,cwd=install,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
info={'directory':str(out),'snapshot_pid':p.pid,'phase':'snapshot'}
(R/'reports/latest.json').write_text(json.dumps(info,indent=2));print(json.dumps(info))
