"""Ship owned v06 source, retaining modified remote files and all v05 bytes."""
import ast,base64,hashlib,io,json,zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
skip={'__pycache__','reports','vendor','.venv-web','deploy_history'}
files=[p for p in root.rglob('*') if p.is_file() and not skip.intersection(p.relative_to(root).parts)]
manifest={};stream=io.BytesIO()
with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
    for p in files:
        if p.suffix=='.py':ast.parse(p.read_text(encoding='utf-8'),filename=str(p))
        name=p.relative_to(root).as_posix();data=p.read_bytes();manifest[name]=hashlib.sha256(data).hexdigest();z.writestr(name,data)
report=root/'reports/deployment';report.mkdir(parents=True,exist_ok=True)
(report/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8');(report/'source.zip').write_bytes(stream.getvalue())
archive_hash=hashlib.sha256(stream.getvalue()).hexdigest();chunk_names=[];uploads=[]
for index,offset in enumerate(range(0,len(stream.getvalue()),60000)):
    chunk=stream.getvalue()[offset:offset+60000];name='deploy_'+archive_hash+'/'+str(index)+'.part';chunk_names.append(name)
    upload=report/('upload_'+str(index)+'.py');uploads.append(str(upload))
    upload.write_text("import base64,hashlib,json\nfrom pathlib import Path\nroot=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06')\nassert not root.is_symlink()\np=root/'reports/incoming'/"+repr(name)+"\nassert p.resolve().is_relative_to(root.resolve())\ndata=base64.b64decode("+repr(base64.b64encode(chunk).decode())+")\nassert hashlib.sha256(data).hexdigest()=="+repr(hashlib.sha256(chunk).hexdigest())+"\nif p.exists():assert p.read_bytes()==data\np.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)\nprint(json.dumps({'chunk':p.name,'bytes':len(data)}))\n",encoding='utf-8')
script='import base64,hashlib,io,json,zipfile\nfrom pathlib import Path,PurePosixPath\nfrom datetime import datetime,timezone\n'
script+="incoming=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/reports/incoming')\narchive=b''.join((incoming/n).read_bytes() for n in "+repr(chunk_names)+")\nassert hashlib.sha256(archive).hexdigest()=="+repr(archive_hash)+'\nexpected='+repr(manifest)+'\n'
script+='''parent=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
root=parent/'v06';assert parent.is_dir();assert not root.is_symlink()
previous=json.loads((root/'deployment_manifest.json').read_text()) if (root/'deployment_manifest.json').exists() else {}
with zipfile.ZipFile(io.BytesIO(archive)) as z:
    for name,digest in expected.items():
        rel=PurePosixPath(name);assert not rel.is_absolute() and '..' not in rel.parts
        target=root/name;assert target.resolve().is_relative_to(root.resolve())
        assert hashlib.sha256(z.read(name)).hexdigest()==digest
        if target.exists():assert hashlib.sha256(target.read_bytes()).hexdigest() in (digest,previous.get(name)), 'Preserve user change: '+name
    revision=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');root.mkdir(exist_ok=True);changed=[]
    for name,digest in expected.items():
        target=root/name
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==digest:continue
        if target.exists():
            saved=root/'deploy_history'/revision/name;saved.parent.mkdir(parents=True,exist_ok=True);saved.write_bytes(target.read_bytes())
        target.parent.mkdir(parents=True,exist_ok=True);tmp=target.with_name(target.name+'.deploy-'+revision)
        tmp.write_bytes(z.read(name));tmp.replace(target);changed.append(name)
    (root/'deployment_manifest.json').write_text(json.dumps(expected,indent=2))
assert all(hashlib.sha256((root/n).read_bytes()).hexdigest()==h for n,h in expected.items())
print(json.dumps({'project':str(root),'files':len(expected),'changed':len(changed),'revision':revision}))
'''
(report/'remote_deploy.py').write_text(script,encoding='utf-8')
(report/'upload_plan.json').write_text(json.dumps({'upload_scripts':uploads,'promote':str(report/'remote_deploy.py'),'archive_sha256':archive_hash}),encoding='utf-8')
print(json.dumps({'files':len(files),'bytes':len(stream.getvalue())}))
