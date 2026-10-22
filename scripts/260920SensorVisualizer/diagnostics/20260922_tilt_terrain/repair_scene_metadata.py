import json
import os
from pathlib import Path
import subprocess
import sys

code='''import hashlib,json
from pathlib import Path
import sys
sys.path.insert(0,sys.argv[1])
from pxr import Sdf
base=Path('/root/gpufree-data/IsaacSim_Asset/combine_stage')
source=Sdf.Layer.FindOrOpen(str(base/'combine_scene_15_surround_fisheye.usda'))
target_path=base/'combine_scene_16_terrain_fisheye.usda'
target=Sdf.Layer.FindOrOpen(str(target_path))
report=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/reports/tilt_terrain')
backup=report/'scene16_before_metadata_fix.usda'
if not backup.exists():backup.write_bytes(target_path.read_bytes())
terrain=target.customLayerData['sensorVisualizerTerrain']
keys=[]
for key in ('metersPerUnit','upAxis','timeCodesPerSecond','framesPerSecond','startTimeCode','endTimeCode','defaultPrim','renderSettingsPrimPath','customLayerData'):
 if source.pseudoRoot.HasInfo(key):target.pseudoRoot.SetInfo(key,source.pseudoRoot.GetInfo(key));keys.append(key)
metadata=dict(target.customLayerData);metadata.update(sensorVisualizerTerrain=terrain,omni_layer={'authoring_layer':'./'+target_path.name})
target.customLayerData=metadata;target.Save()
print(json.dumps({'restored_metadata':keys,'scene_sha256':hashlib.sha256(target_path.read_bytes()).hexdigest()}))
'''
libs=sorted(Path('/root/isaacsim/extscache').glob('omni.usd.libs-*'))[-1]
env=dict(os.environ);env['LD_LIBRARY_PATH']=str(list(libs.rglob('libusd_tf.so'))[0].parent)+':/root/isaacsim/kit/lib'
r=subprocess.run([sys.executable,'-I','-S','-B','-c',code,str(libs)],env=env,capture_output=True,text=True,timeout=20)
print(json.dumps({'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr}));raise SystemExit(r.returncode)
