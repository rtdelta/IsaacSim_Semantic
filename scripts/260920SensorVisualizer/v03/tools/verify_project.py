"""Static isolation and optional original-file hash verification; executes no old code."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sensor_visualizer_v03.contracts import load_job,write_json


def verify(originals=False):
    errors=[];count=0
    for path in ROOT.rglob('*.py'):
        source=path.read_text(encoding='utf-8-sig');tree=ast.parse(source);count+=1
        if path.name=='verify_project.py':continue
        for node in ast.walk(tree):
            names=[]
            if isinstance(node,ast.Import):names=[a.name for a in node.names]
            if isinstance(node,ast.ImportFrom):
                names=[node.module or '']
                if node.level:
                    parent=path.parent
                    for _ in range(node.level-1):parent=parent.parent
                    candidate=parent/(node.module or '').replace('.','/')
                    if not (candidate.with_suffix('.py').is_file() or (candidate/'__init__.py').is_file()):
                        errors.append('Missing local import: '+str(path.relative_to(ROOT))+':'+str(node.module))
            if any(n.startswith(('sensor_visualizer_v02','sv02_legacy','lidar_visualizer')) for n in names):
                errors.append('Old project import: '+str(path.relative_to(ROOT)))
        if 'sensor_visualizer_v02' in source or '/260920SensorVisualizer/v02' in source or 'sv02_legacy' in source:
            errors.append('Old runtime dependency string: '+str(path.relative_to(ROOT)))
    for path in (ROOT/'config').glob('*.json'):
        if path.name!='robot_sensors.json':load_job(path)
    result={'python_files':count,'runtime_isolation_passed':not errors,'errors':errors}
    if originals:
        baseline=json.loads((ROOT/'reports/original_files_before.json').read_text())
        changed=[];missing=[]
        for relative,expected in baseline.items():
            path=ROOT.parent/relative
            if not path.is_file():missing.append(relative)
            elif hashlib.sha256(path.read_bytes()).hexdigest()!=expected:changed.append(relative)
        result.update(original_files_checked=len(baseline),original_files_changed=changed,original_files_missing=missing)
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--originals',action='store_true');args=parser.parse_args()
    result=verify(args.originals);write_json(ROOT/'reports/isolation_check.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if result['errors'] or result.get('original_files_changed') or result.get('original_files_missing'):raise SystemExit(1)
