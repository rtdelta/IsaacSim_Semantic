"""Build new terrain and scene with existing software; no network or installation."""
import json
import os
from pathlib import Path
import subprocess
import sys

root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
asset=Path('/root/gpufree-data/IsaacSim_Asset/environment_module_set/UndulatingGround_20260922')
scene=Path('/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_16_terrain_fisheye.usda')
env=dict(os.environ)
for key in ['LD_PRELOAD','LD_LIBRARY_PATH','PYTHONPATH','PYTHONHOME','VIRTUAL_ENV','CONDA_PREFIX']:
    env.pop(key,None)
env['LD_LIBRARY_PATH']='/opt/blender/lib'
partial=asset/'terrain.blend'
if partial.exists() and not (asset/'terrain.usdc').exists() and not (asset/'build_report.json').exists():
    archived=asset/'terrain.incomplete-export.blend'
    if archived.exists():raise FileExistsError('Inspect previous build attempts before retry')
    partial.rename(archived)
r=subprocess.run(['/opt/blender/blender','--background','--factory-startup','--disable-autoexec',
    '--python-exit-code','1','--python',str(root/'tools/build_terrain_blender.py'),'--','--config',str(root/'config/terrain.json'),
    '--output',str(asset)],env=env,capture_output=True,text=True,timeout=80)
report=root/'reports/tilt_terrain';report.mkdir(parents=True,exist_ok=True)
(report/'blender_build.log').write_text(r.stdout+'\n'+r.stderr)
if r.returncode:
    print(json.dumps({'step':'blender','exit':r.returncode,'stdout':r.stdout[-2000:],'stderr':r.stderr[-2000:]}))
    raise SystemExit(1)
if not (asset/'build_report.json').is_file():raise RuntimeError('Blender did not produce build_report.json')
libs=sorted(Path('/root/isaacsim/extscache').glob('omni.usd.libs-*'))[-1]
native=list(libs.rglob('libusd_tf.so'))[0].parent
env['LD_LIBRARY_PATH']=str(native)+':/root/isaacsim/kit/lib'
r=subprocess.run([sys.executable,'-B',str(root/'tools/build_terrain_stage.py'),'--terrain',str(asset/'terrain.usdc'),
                  '--output',str(scene)],env=env,capture_output=True,text=True,timeout=40)
(report/'stage_build.log').write_text(r.stdout+'\n'+r.stderr)
print(json.dumps({'step':'stage','exit':r.returncode,'stdout':r.stdout[-10000:],'stderr':r.stderr[-2500:],
                  'blender_report':json.loads((asset/'build_report.json').read_text())}))
raise SystemExit(r.returncode)
