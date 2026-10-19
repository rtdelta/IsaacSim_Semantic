import hashlib,json,zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1];source=root.parent/'native_capture_quality_002'
manifest={}
for p in source.rglob('*'):
 if p.is_file() and not any(x in p.relative_to(source).parts for x in ('reports','backups','deploy_history','__pycache__')):
  manifest[p.relative_to(source).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
(root/'backups').mkdir(exist_ok=True);(root/'reports').mkdir(exist_ok=True)
with zipfile.ZipFile(root/'backups/NC003_pre_Q002.zip','x',zipfile.ZIP_DEFLATED) as z:
 for rel in manifest:z.write(source/rel,rel)
(root/'reports/preserved_q002_local.json').write_text(json.dumps(manifest,indent=2))
for rel in ('run.py','kit_entry.py','experiment.py','config/baseline.json','tools/validate_bag.py','tools/validate_groups.py','tools/analyze_results.py','tools/build_deploy.py','tools/pull_evidence.py'):
 p=root/rel;p.parent.mkdir(exist_ok=True)
 assert not p.exists(),str(p)
 text=(source/rel).read_text()
 text=text.replace('native_capture_quality_002','native_capture_continuous_pt_003')
 if rel=='tools/build_deploy.py':text=text.replace("oldnames=('native_capture_baseline','v06','single06_lab')","oldnames=('native_capture_baseline','v06','single06_lab','native_capture_quality_002')")
 p.write_text(text,encoding='utf-8')
spec=json.loads((root/'config/baseline.json').read_text())
spec.update(experiment='continuous_pt',schedule='native_run',render_mode='PathTracing',pt_spp=32,pt_total_spp=1024,
 measure_frames=4,warmup_frames=8,motion='logical_joint_test',export_quality_images=False,timeout_s=900,trace=False,
 reset_pt_per_frame=True,continuous_basic_writer=True,ros_domain_id=188)
(root/'config/baseline.json').write_text(json.dumps(spec,indent=2))
print(json.dumps({'project':str(root),'preserved_local_q002_files':len(manifest)}))
