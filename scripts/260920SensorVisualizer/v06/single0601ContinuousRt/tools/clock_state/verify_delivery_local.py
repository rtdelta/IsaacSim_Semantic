"""Safely expand only expected regular metadata files and verify every SHA."""
import argparse,hashlib,json,tarfile
from pathlib import Path,PurePosixPath

def verify(archive_path,destination):
    archive_path=Path(archive_path);destination=Path(destination).resolve()
    if destination.exists():raise ValueError('Refuse local evidence directory overwrite')
    with tarfile.open(archive_path,'r:gz') as archive:
        members=archive.getmembers();names=[m.name for m in members]
        if len(set(names))!=len(names):raise ValueError('Duplicate archive members')
        for m in members:
            p=PurePosixPath(m.name)
            if not m.isfile() or p.is_absolute() or '..' in p.parts or '\\' in m.name or ':' in m.name:raise ValueError('Unsafe member '+m.name)
        manifest=json.load(archive.extractfile('delivery_manifest.json'))
        expected={m['path']:m for m in manifest['files']}
        if set(names)!=set(expected)|{'delivery_manifest.json'}:raise ValueError('Unexpected or missing evidence file')
        if sum(m.size for m in members)>2*1024**3:raise ValueError('Uncompressed budget')
        destination.mkdir(parents=True)
        for m in members:
            data=archive.extractfile(m).read()
            if m.name in expected:
                item=expected[m.name]
                if len(data)!=item['bytes'] or hashlib.sha256(data).hexdigest()!=item['sha256']:raise ValueError('SHA mismatch '+m.name)
            path=destination/Path(*PurePosixPath(m.name).parts)
            if destination not in path.resolve().parents:raise ValueError('Resolved member outside destination')
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    report={'verified_files':len(expected),'uncompressed_bytes':manifest['bytes'],
        'archive_sha256':hashlib.sha256(archive_path.read_bytes()).hexdigest(),'directory':str(destination),
        'full_raw_payload_scope':'retained remotely; this local delivery is metadata and analysis only'}
    (destination/'local_verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report));return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('archive');p.add_argument('destination');a=p.parse_args();verify(a.archive,a.destination)
