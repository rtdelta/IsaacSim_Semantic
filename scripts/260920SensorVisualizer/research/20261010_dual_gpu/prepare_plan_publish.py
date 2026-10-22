"""Validate project Markdown and build an audited, non-overwriting upload."""
import base64,hashlib,json,re
from pathlib import Path
here=Path(__file__).resolve().parent;project=here.parent.parent
names=['docs/20261010_dual_gpu_v07_optimization_plan.md']+[
 'research/20261010_dual_gpu/'+name for name in ('hardware_report.json','sdk_report.json',
 'sdk_code_details.json','device_path_report.json','findings_and_plan.json')]
doc=project/names[0];body=doc.read_text(encoding='utf-8')
assert body.startswith('# Sensor Visualizer v07') and body.count('```')%2==0
local_links=[]
for link in re.findall(r'\]\(([^)]+)\)',body):
    if link.startswith(('http://','https://','#')):continue
    p=(doc.parent/link.split('#')[0]).resolve()
    assert p.is_file(),link
    local_links.append(link)
entries=[]
for relative in names:
    p=project/relative;data=p.read_bytes()
    if p.suffix=='.json':json.loads(data)
    entries.append({'relative':relative,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
                    'base64':base64.b64encode(data).decode('ascii')})
template='''import base64,hashlib,json,os,uuid
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
workspace=Path('/root/gpufree-data').resolve()
assert root.resolve().is_relative_to(workspace)
entries=json.loads(base64.b64decode(PAYLOAD))
ready=[]
for item in entries:
    dst=root/item['relative'];data=base64.b64decode(item['base64'])
    assert dst.resolve().is_relative_to(root.resolve()) and not dst.is_symlink()
    assert len(data)==item['bytes'] and hashlib.sha256(data).hexdigest()==item['sha256']
    if dst.exists():
        assert dst.is_file() and hashlib.sha256(dst.read_bytes()).hexdigest()==item['sha256'],'Existing file differs: '+item['relative']
    ready.append((item,dst,data))
copied=[]
for item,dst,data in ready:
    if not dst.exists():
        dst.parent.mkdir(parents=True,exist_ok=True)
        assert dst.parent.resolve().is_relative_to(root.resolve())
        temp=dst.parent/('.codex-plan-'+uuid.uuid4().hex+'.tmp')
        try:
            with temp.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
            temp.chmod(0o644)
            os.link(temp,dst)
            copied.append(item['relative'])
        finally:
            if temp.exists():temp.unlink()
    assert hashlib.sha256(dst.read_bytes()).hexdigest()==item['sha256']
print(json.dumps({'passed':True,'files':len(entries),'new_files':copied,
                  'document':str(root/entries[0]['relative']),'document_sha256':entries[0]['sha256'],
                  'original_code_modified':False,'runtime_started':False}))
'''
payload=base64.b64encode(json.dumps(entries).encode()).decode('ascii')
(here/'publish_plan_payload.py').write_text(template.replace('PAYLOAD',repr(payload)),encoding='utf-8')
validation={'passed':True,'document':str(doc),'bytes':doc.stat().st_size,
            'headings':len(re.findall(r'^#{1,3} ',body,re.M)),
            'local_links_checked':len(local_links),'files_prepared':len(entries),
            'document_sha256':entries[0]['sha256']}
(here/'plan_document_validation.json').write_text(json.dumps(validation,indent=2),encoding='utf-8')
print(json.dumps(validation))
