"""AST/config integrity and unchanged-original comparison; no SDK claim."""
import ast,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from single0601_continuous_rt.config import load
from single0601_continuous_rt.common import save_json,file_hash
files=[]
for p in sorted(ROOT.rglob('*.py')):
    if any(part in ('reports','.deploy_backups','__pycache__') for part in p.parts):continue
    ast.parse(p.read_text(encoding='utf-8-sig'),filename=str(p))
    files.append({'path':p.relative_to(ROOT).as_posix(),'sha256':file_hash(p)})
configs=[]
for name in ('strict_scene18','single_camera','single_lidar','mixed_pair','benchmark_scene18'):
    p=ROOT/'config'/(name+'.json')
    load(p)
    configs.append({'path':p.relative_to(ROOT).as_posix(),'sha256':file_hash(p)})
report={'schema_version':1,'parsed_python_files':len(files),'validated_job_configs':len(configs),'passed':True,
        'source_files':files,'configs':configs,'scope':'local Python grammar and schema4; real SDK and ROS checks are separate'}
old=ROOT/'reports/preflight_response.json'
new=ROOT/'reports/recovery_final_preservation_actual.json'
if not new.exists():new=ROOT/'reports/remote/reports/final_original_asset_source.json'
if old.exists() and new.exists():
    before=json.loads(json.loads(old.read_text(encoding='utf-8'))['result']['stdout'])
    after=json.loads(new.read_text(encoding='utf-8'))
    changes=[]
    mapping={f['path']:f for f in before['source_files']}
    for item in after['source_files']:
        if item['path'] in mapping and item['sha256']!=mapping[item['path']]['sha256']:changes.append(item['path'])
    added=[item['path'] for item in after['source_files'] if item['path'] not in mapping]
    deleted=sorted(set(mapping)-{item['path'] for item in after['source_files']})
    report['original_preservation']={'scene_sha256_unchanged':before['scene']['sha256']==after['scene']['sha256'],
        'comparison_before':str(old.relative_to(ROOT)),'comparison_after':str(new.relative_to(ROOT)),
        'comparison_created_utc':after.get('created_utc','not recorded in prior snapshot'),
        'changed_original_files':changes,'added_original_files':added,'deleted_original_files':deleted,
        'passed':not changes and not added and not deleted and before['scene']['sha256']==after['scene']['sha256']}
    report['passed']=report['passed'] and report['original_preservation']['passed']
save_json(ROOT/'reports/source_integrity.json',report)
print(json.dumps({k:v for k,v in report.items() if k not in ('source_files','configs')}))
sys.exit(0 if report['passed'] else 2)
