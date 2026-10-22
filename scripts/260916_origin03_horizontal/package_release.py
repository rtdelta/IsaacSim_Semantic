"""Package reviewed local files and generate a guarded, backed-up remote installer."""
import base64, io, json, zipfile
from pathlib import Path
ROOT = Path('D:/learning/IntelligentDepartment/CodesSet/Self/260907LidarVisualizer')
OUT = Path(__file__).resolve().parent
baseline = json.loads((ROOT/'backups/origin03_horizontal_20260916_105615/manifest.json').read_text())
files = [p.relative_to(ROOT).as_posix() for p in (ROOT/'lidar_visualizer').glob('*.py')]
files += ['config/sensors.json','run_in_isaac.py','README.md','ORIGIN03_HORIZONTAL.md',
          'validation/test_reference_frames.py','validation/validate_horizontal_isaac.py',
          'validation/verify_horizontal_bag.py']
buffer = io.BytesIO()
with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
    for name in files: archive.writestr(name,(ROOT/name).read_bytes())
payload = base64.b64encode(buffer.getvalue()).decode()
template = '''import base64, datetime, hashlib, io, json, shutil, zipfile
from pathlib import Path, PurePosixPath
root=Path('/root/gpufree-data/semantic/scripts/260907LidarVisualizer')
baseline=BASELINE
archive=zipfile.ZipFile(io.BytesIO(base64.b64decode(PAYLOAD)))
receipt=root/'DEPLOYMENT_ORIGIN03.json'
previous=json.loads(receipt.read_text()).get('files',{}) if receipt.exists() else {}
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for name in archive.namelist():
    assert not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts
    p=root/name
    assert p.resolve().is_relative_to(root.resolve())
    if p.exists():
        allowed=[x for x in (baseline.get(name),previous.get(name)) if x]
        assert sha(p) in allowed, ('Unexpected remote change',name,sha(p))
backup=root/'backups'/('origin03_horizontal_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
backup.mkdir(parents=True)
before={}
for name in archive.namelist():
    p=root/name
    if p.exists():
        dest=backup/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest);before[name]=sha(p)
    p.parent.mkdir(parents=True,exist_ok=True)
    temp=p.with_name(p.name+'.origin03_pending')
    assert not temp.exists()
    temp.write_bytes(archive.read(name));temp.replace(p)
(backup/'manifest.json').write_text(json.dumps(before,indent=2))
result={'project':str(root),'backup':str(backup),'files':{name:sha(root/name) for name in archive.namelist()}}
receipt.write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
'''
(OUT/'deploy_remote.py').write_text(template.replace('BASELINE',repr(baseline)).replace('PAYLOAD',repr(payload)),encoding='utf-8')
print('Packaged',len(files),'files;',len(buffer.getvalue()),'bytes')
