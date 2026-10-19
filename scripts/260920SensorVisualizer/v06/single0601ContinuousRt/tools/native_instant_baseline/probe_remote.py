import json,os,subprocess,sys,signal
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt');sys.path.insert(0,str(root))
from run_capture import launch_spec
from tools.experiments.start_paired_remote import kits
if kits():raise RuntimeError('Existing Kit')
os.environ['DISPLAY']=':20';os.environ.pop('S0601_FORCE_BARRIER',None)
spec={'name':'effective_E_probe_20261015_r03','group':'probe','entry':'tools/native_instant_baseline/probe_effective.py',
 'scene_asset':'/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_18_terrain_fisheye_mesh.usda',
 'source_prim':'/World/Excavator/swing_link/MyAiry_front/sensor'}
os.environ['NIB_PROBE_SPEC']=json.dumps(spec)
command,env,install=launch_spec(root/'config/mixed_pair.json',root/spec['entry'])
command=[c for c in command if not c.startswith('--/rtx/scenedb/maxHistoryTransformCount=')]
out=root/'reports/native_instant_baseline';out.mkdir(parents=True,exist_ok=True)
with (out/(spec['name']+'_launch.log')).open('xb') as f:
 child=subprocess.Popen(command,cwd=install,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
 try:code=child.wait(timeout=240)
 except subprocess.TimeoutExpired:
  os.killpg(child.pid,signal.SIGTERM);raise
if code:raise RuntimeError('Probe exit '+str(code))
result=json.loads((out/spec['name']/'probe_result.json').read_text())
finger=json.loads((out/spec['name']/'configuration_fingerprint.json').read_text())
print(json.dumps({'result':result,'fingerprint':finger}))
