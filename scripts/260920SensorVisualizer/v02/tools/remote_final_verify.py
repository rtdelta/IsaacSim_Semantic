from pathlib import Path
import hashlib
import json
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v02')
manifest=json.loads((root/'deployment_manifest.json').read_text())
bad=[name for name,value in manifest.items() if not (root/name).is_file() or hashlib.sha256((root/name).read_bytes()).hexdigest()!=value]
provenance=json.loads((root/'provenance.json').read_text())
original=provenance['source_files']
old_bad=[name for name,value in original.items() if hashlib.sha256((root.parent/name).read_bytes()).hexdigest()!=value]
old_detail={name:{'sha256':hashlib.sha256((root.parent/name).read_bytes()).hexdigest(),
 'lf_sha256':hashlib.sha256((root.parent/name).read_text().encode()).hexdigest(),
 'mtime_ns':(root.parent/name).stat().st_mtime_ns} for name in original}
processes=[]
for p in Path('/proc').glob('[0-9]*/cmdline'):
    try: cmd=p.read_bytes().replace(b'\0',b' ').decode(errors='replace')
    except OSError: continue
    if str(root) in cmd and ('kit_entry.py' in cmd or 'record_worker.py' in cmd or 'kit_ui_test.py' in cmd or 'kit_quality_test.py' in cmd):
        processes.append({'pid':int(p.parent.name),'command':cmd[:220]})
asset=Path('/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_16_terrain_fisheye.usda')
normalized_bad=[n for n,d in old_detail.items() if d['lf_sha256']!=provenance['source_lf_sha256'][n]]
baseline_bad=[n for n,value in provenance['remote_initial_files'].items() if hashlib.sha256((root.parent/n).read_bytes()).hexdigest()!=value]
print(json.dumps({'deployed_files':len(manifest),'deployment_mismatches':bad,
 'original_source_files_checked':len(original),'cross_platform_byte_differences':old_bad,
 'original_normalized_source_mismatches':normalized_bad,'remote_pre_task_hash_mismatches':baseline_bad,
 'original_source_details':old_detail,
 'root_asset_sha256':hashlib.sha256(asset.read_bytes()).hexdigest(),
 'user_gui_pid_19303_alive':Path('/proc/19303/cmdline').exists(),'task_processes':processes}))
