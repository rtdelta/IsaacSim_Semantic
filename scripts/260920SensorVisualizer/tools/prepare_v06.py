"""Preserve the exact v05 source and create an independent performance version."""
from datetime import datetime
import hashlib,json,shutil,zipfile
from pathlib import Path
parent=Path(__file__).resolve().parents[1];source=parent/'v05';dest=parent/'v06'
assert not dest.exists(),'Preserve an existing v06; inspect before continuing'
excluded={'__pycache__','reports','vendor','.venv-web','deploy_history'}
files=[p for p in source.rglob('*') if p.is_file() and not excluded.intersection(p.relative_to(source).parts)]
stamp=datetime.now().strftime('%Y%m%d_%H%M%S');backup=parent/'backups'/('v05_performance_baseline_'+stamp);backup.mkdir()
manifest={p.relative_to(source).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
with zipfile.ZipFile(backup/'v05_source.zip','x',zipfile.ZIP_DEFLATED) as z:
    for p in files:z.write(p,p.relative_to(source))
(backup/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
dest.mkdir()
for p in files:
    rel=p.relative_to(source)
    if rel.parts[0]=='docs' or rel.name=='README.md':continue
    target=dest/str(rel).replace('sensor_visualizer_v05','sensor_visualizer_v06');target.parent.mkdir(parents=True,exist_ok=True)
    text=p.read_text(encoding='utf-8')
    for a,b in [('sensor_visualizer_v05','sensor_visualizer_v06'),('SV05','SV06'),('sv05','sv06'),('SensorVisualizerV05','SensorVisualizerV06'),
                ('/v05','/v06'),('17865','17875'),('17866','17876'),('17867','17877')]:text=text.replace(a,b)
    target.write_text(text,encoding='utf-8')
(dest/'docs').mkdir();(dest/'reports').mkdir()
(dest/'baseline_manifest.json').write_text(json.dumps({'source':'v05','local_backup':str(backup),'sha256':manifest},indent=2),encoding='utf-8')
prompt=Path('C:/Users/15452/.codex/attachments/f27bdf4f-19ac-47f7-af4b-6b9f4621829a/已粘贴的文本.txt')
shutil.copyfile(prompt,dest/'docs/task_prompt_20261010.txt')
print(json.dumps({'project':str(dest),'backup':str(backup),'source_files':len(files)}))
