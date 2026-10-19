from pathlib import Path
import json
root=Path('/root/isaacsim/extscache')
result=[]
for base in root.glob('omni.replicator.core-*'):
 for p in base.rglob('*.py'):
  if p.name not in ('annotators.py','annotator.py'):continue
  s=p.read_text();lines=s.splitlines();hits=[i for i,l in enumerate(lines) if any(x in l for x in ('def get_data(', 'def get_annotator(', 'do_array_copy', 'register_annotator_from_node'))]
  result.append({'path':str(p),'snippets':'\n'.join('\n'.join(lines[max(0,i-3):i+65]) for i in hits[:20])})
print(json.dumps(result))
