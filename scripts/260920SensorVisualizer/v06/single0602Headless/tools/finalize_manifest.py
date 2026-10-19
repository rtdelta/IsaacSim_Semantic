"""Record current delivered hashes without changing original source-snapshot hashes."""
import hashlib
import json
from pathlib import Path
from project_files import delivery_files

ROOT=Path(__file__).resolve().parents[1]
source_path=ROOT/'source_provenance.json'
source=json.loads(source_path.read_text(encoding='utf-8'))
for row in source['files']:
    row['delivered_sha256']=hashlib.sha256((ROOT/row['destination']).read_bytes()).hexdigest()
    current=ROOT.parents[3]/row['source']
    row['source_still_matches_snapshot']=current.is_file() and hashlib.sha256(current.read_bytes()).hexdigest()==row['source_sha256']
source_path.write_text(json.dumps(source,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
files={}
for path in delivery_files(ROOT):
    files[path.relative_to(ROOT).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
manifest={'schema_version':1,'project':'single0602Headless','date':'2026-10-19','version':'0.3.0',
          'scope':'Delivered project source/config/docs and curated docs/reports; excluding runtime reports and caches',
          'files':dict(sorted(files.items()))}
(ROOT/'project_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'files':len(files),'source_snapshots':len(source['files']),
                  'original_sources_unchanged':all(x['source_still_matches_snapshot'] for x in source['files'])}))
