"""Final source and generated-asset checks after real engine validation."""
import hashlib,json
from pathlib import Path
work=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/mesh_scene18')
m=json.loads((work/'build_manifest.json').read_text())
hashes=json.loads((Path(m['backup_directory'])/'source_hashes.json').read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
changed=[p for p,h in hashes.items() if sha(p)!=h]
generated={m['asset']:m['asset_sha256'],m['scene']:m['scene_sha256'],**{r['geometry_file']:r['geometry_sha256'] for r in m['parts'].values()}}
changed_new=[p for p,h in generated.items() if sha(p)!=h]
latest=json.loads((work/'latest_capture.json').read_text());case=Path(latest['case']);result=json.loads((case/'result.json').read_text())
kit=[]
for p in Path('/proc').glob('[0-9]*/cmdline'):
    try:
        if p.read_bytes().split(b'\0')[0].endswith(b'/kit/kit'):kit.append(int(p.parent.name))
    except OSError:pass
lines=(case/'engine.log').read_text(errors='replace').splitlines()
report={'passed':not changed and not changed_new and result['state']=='completed','checked_source_files':len(hashes),'changed_source_files':changed,'changed_generated_files':changed_new,'capture_state':result['state'],'kit_processes_now':kit,'engine_error_lines':sum('[Error]' in s for s in lines),'engine_warning_lines':sum('[Warning]' in s for s in lines),'remote_scene':m['scene'],'source_scene_preserved':m['source_scene'],'local_mirrors':'Transferred separately with audited SFTP and per-file SHA256; not a claim of standalone combine dependencies.'}
(work/'final_verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report));assert report['passed']
