"""Extract this task's compact evidence with path, size and SHA checks."""
import argparse,hashlib,json,tarfile
from pathlib import Path,PurePosixPath

def run(archive,directory,expected_sha):
    archive=Path(archive);directory=Path(directory).resolve()
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest!=expected_sha:raise ValueError('Archive transfer SHA mismatch')
    directory.mkdir(parents=True,exist_ok=False)
    with tarfile.open(archive,'r:gz') as z:
        members=z.getmembers();seen=set();total=0
        for member in members:
            rel=PurePosixPath(member.name)
            if not member.isfile() or rel.is_absolute() or '..' in rel.parts or member.name in seen:raise ValueError('Unsafe or duplicate archive member')
            seen.add(member.name);path=(directory/Path(*rel.parts)).resolve()
            if directory not in path.parents or member.size>64*1024**2:raise ValueError('Path or file budget')
            total+=member.size
            if total>2*1024**3:raise ValueError('Archive total budget')
            path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as f:f.write(z.extractfile(member).read())
    manifest=json.loads((directory/'delivery_manifest.json').read_text())
    for row in manifest['files']:
        p=directory/row['path']
        if p.stat().st_size!=row['bytes'] or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('Member SHA mismatch: '+row['path'])
    result={'archive_sha256':digest,'verified_files':len(manifest['files']),'uncompressed_bytes':manifest['uncompressed_bytes'],'directory':str(directory)}
    (directory/'local_transfer_verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('archive');p.add_argument('directory');p.add_argument('sha256');a=p.parse_args();run(a.archive,a.directory,a.sha256)
