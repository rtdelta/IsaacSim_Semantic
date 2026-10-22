"""Package owned source only; generate an audited remote promotion script."""
import ast,base64,hashlib,io,json
from pathlib import Path
import zipfile
root=Path(__file__).resolve().parents[1]
files=[p for p in root.rglob('*') if p.is_file() and not any(x in p.relative_to(root).parts for x in ('__pycache__','reports','vendor','.venv-web'))]
manifest={};stream=io.BytesIO()
with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
    for p in files:
        if p.suffix=='.py':ast.parse(p.read_text(encoding='utf-8'),filename=str(p))
        relative=p.relative_to(root).as_posix();data=p.read_bytes();manifest[relative]=hashlib.sha256(data).hexdigest();z.writestr(relative,data)
data=stream.getvalue();report=root/'reports/deployment';report.mkdir(parents=True,exist_ok=True)
(report/'source.zip').write_bytes(data)
(report/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
script='import base64,hashlib,io,json,zipfile\nfrom pathlib import Path,PurePosixPath\nfrom datetime import datetime,timezone\n'
script+='archive=base64.b64decode('+repr(base64.b64encode(data).decode())+')\n'
script+='expected='+repr(manifest)+'\n'
script+='''parent=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
root=parent/'v05'
assert parent.is_dir()
previous=json.loads((root/'deployment_manifest.json').read_text()) if (root/'deployment_manifest.json').exists() else {}
with zipfile.ZipFile(io.BytesIO(archive)) as z:
    for name,digest in expected.items():
        rel=PurePosixPath(name)
        assert not rel.is_absolute() and '..' not in rel.parts
        target=root/name
        assert target.resolve().is_relative_to(root.resolve())
        assert hashlib.sha256(z.read(name)).hexdigest()==digest
        if target.exists():
            actual=hashlib.sha256(target.read_bytes()).hexdigest()
            assert actual in (digest,previous.get(name)), 'Preserve unexpected user change: '+name
    backup=parent/'backups/20261009_before_v05'
    backup.mkdir(parents=True,exist_ok=True)
    if not (backup/'v04_remote_manifest.json').exists():
        old=parent/'v04';old_files=[p for p in old.rglob('*') if p.is_file() and p.suffix in ('.py','.json','.md') and not any(x in p.relative_to(old).parts for x in ('__pycache__','reports','experiments','deploy_history'))]
        hashes={p.relative_to(old).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in old_files}
        with zipfile.ZipFile(backup/'v04_remote_source.zip','x',zipfile.ZIP_DEFLATED) as out:
            for p in old_files:out.write(p,p.relative_to(old).as_posix())
        (backup/'v04_remote_manifest.json').write_text(json.dumps(hashes,indent=2))
    revision=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    root.mkdir(parents=True,exist_ok=True)
    changed=[]
    for name,digest in expected.items():
        target=root/name;new=z.read(name)
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==digest:continue
        if target.exists():
            save=root/'deploy_history'/revision/name;save.parent.mkdir(parents=True,exist_ok=True);save.write_bytes(target.read_bytes())
        target.parent.mkdir(parents=True,exist_ok=True)
        temp=target.with_name(target.name+'.deploy-'+revision);temp.write_bytes(new);temp.replace(target);changed.append(name)
    (root/'deployment_manifest.json').write_text(json.dumps(expected,indent=2))
    mismatches=[name for name,h in expected.items() if hashlib.sha256((root/name).read_bytes()).hexdigest()!=h]
    assert not mismatches,mismatches
print(json.dumps({'project':str(root),'files':len(expected),'changed':len(changed),'mismatches':mismatches,'backup':str(backup),'revision':revision}))
'''
(report/'remote_deploy.py').write_text(script,encoding='utf-8')
print(json.dumps({'files':len(files),'archive_bytes':len(data),'script':str(report/'remote_deploy.py')}))
