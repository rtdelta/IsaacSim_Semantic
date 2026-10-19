"""Independent preregistered input table and capture hash review."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.native_rotation_localization.io import rows
def review(path):
 path=Path(path);spec=json.loads((path/'run_spec.json').read_text());frozen=ROOT/spec['frozen_input_path'];b=frozen.read_bytes()
 if hashlib.sha256(b).hexdigest()!=spec['frozen_input_sha256']:raise RuntimeError('Preregistered input table changed')
 expected=json.loads(b)['rows'];actual=rows(path/'continuous/pose_table.jsonl');h=json.loads((path/'continuous/motion_table_hash.json').read_text())
 table={r['physical_step']:r for r in actual};digest=hashlib.sha256(json.dumps(table,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 agree=len(expected)==len(actual) and all(a['motion_step']==e['motion_step'] and abs(a['yaw_rad']-e['yaw_rad'])<=1e-12 for a,e in zip(actual,expected))
 return {'run':str(path),'expected_steps':len(expected),'actual_steps':len(actual),'full_preregistered_table_matches':agree,'recorded_capture_hash_matches':digest==h['sha256'],'runtime_frozen_before_motion':h['frozen_before_motion'],'preregistered_input_sha256':spec['frozen_input_sha256']}
