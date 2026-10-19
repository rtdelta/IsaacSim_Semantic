"""System-Python launcher; uses the existing supported Isaac/ROS environment."""
import argparse
import json
import os
from pathlib import Path
import sys

p = argparse.ArgumentParser()
p.add_argument('--job-dir', type=Path, required=True)
p.add_argument('--source', default='/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_11_origin03.usda')
p.add_argument('--stage', default='/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_12_myairy.usda')
p.add_argument('--asset', default='/root/gpufree-data/IsaacSim_Asset/sensor_set/lidar_set/MyAiry/MyAiry.usda')
p.add_argument('--visualizer', default='/root/gpufree-data/semantic/scripts/260907LidarVisualizer')
p.add_argument('--domain', type=int, default=173)
p.add_argument('--seconds', type=float, default=3.)
p.add_argument('--reuse-stage', action='store_true')
a = p.parse_args()
a.job_dir.mkdir(parents=True, exist_ok=False)
job = {k:str(v) if isinstance(v, Path) else v for k,v in vars(a).items()}
(a.job_dir/'request.json').write_text(json.dumps(job, indent=2)+'\n')
env = os.environ.copy()
env['AIRY_CAPTURE_REQUEST'] = str(a.job_dir/'request.json')
env['ROS_DOMAIN_ID'] = str(a.domain)
script = Path(__file__).with_name('capture_scene.py')
argv = [sys.executable, str(Path(a.visualizer)/'launch_isaac.py'), '--no-window',
        '--/app/fastShutdown=true', '--/app/file/ignoreUnsavedOnExit=true', '--exec', str(script)]
os.execve(sys.executable, argv, env)
