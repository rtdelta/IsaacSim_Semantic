"""Read-only final manifest, known source asset and task-release verification."""
import hashlib
import json
from pathlib import Path
import sys
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless')
sys.path.insert(0,str(root))
from single0602_headless.capture_supervisor import CaptureSupervisor
from single0602_headless.frame_contract import resolve_profile
manifest=json.loads((root/'project_manifest.json').read_text())
mismatch=[]
for name,expected in manifest['files'].items():
    path=root/name
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:mismatch.append(name)
profile=resolve_profile(root,'/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_18_terrain_fisheye_mesh.usda')
output=Path('/root/gpufree-data/semantic/output/sensor_visualizer/single0602Headless')
supervisor=CaptureSupervisor(root,output,output/'runtime/engine.sock')
active=[t['task_id'] for t in supervisor.status() if t['running'] or t.get('cleanup_pending')]
result={'state':'passed' if not mismatch and not active and not supervisor.resource_busy() else 'failed',
        'files_verified':len(manifest['files']),'mismatches':mismatch,'active_capture_tasks':active,
        'capture_lock_busy':supervisor.resource_busy(),'interactive_socket_exists':(output/'runtime/engine.sock').exists(),
        'source_scene_and_asset_profile_verified':profile['id']}
print(json.dumps(result))
if result['state']!='passed':raise SystemExit(1)
