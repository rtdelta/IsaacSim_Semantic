"""Create a scoped, hash-checked deployment; never touches old version folders."""
import base64,hashlib,io,json,zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1];manifest={}
with io.BytesIO() as buf:
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(root.rglob('*')):
            if not p.is_file() or any(x in p.relative_to(root).parts for x in ['reports','__pycache__','deploy_history']):continue
            rel=p.relative_to(root).as_posix();data=p.read_bytes();z.writestr(rel,data);manifest[rel]=hashlib.sha256(data).hexdigest()
        plan=root.parent/'docs/20261011_IsaacNativeCaptureBaselineImplementation.md'
        if 'docs/implementation_plan.md' not in manifest:
            data=plan.read_bytes();z.writestr('docs/implementation_plan.md',data);manifest['docs/implementation_plan.md']=hashlib.sha256(data).hexdigest()
    payload=base64.b64encode(buf.getvalue()).decode()
code='''import base64,hashlib,io,json,time,zipfile
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_baseline')
if root.parent.resolve()!=root.parent or root.exists() and root.resolve()!=root:raise RuntimeError('Unexpected symlink')
root.mkdir(exist_ok=True)
expected=MANIFEST
changed=[];stamp=time.strftime('%Y%m%d_%H%M%S',time.gmtime())
with zipfile.ZipFile(io.BytesIO(base64.b64decode(PAYLOAD))) as z:
 for rel in z.namelist():
  p=root/rel
  if not p.resolve().is_relative_to(root):raise RuntimeError('Unsafe member')
  data=z.read(rel)
  if hashlib.sha256(data).hexdigest()!=expected[rel]:raise RuntimeError('Payload mismatch')
  if p.exists() and p.read_bytes()==data:continue
  if p.exists():
   b=root/'deploy_history'/stamp/rel;b.parent.mkdir(parents=True,exist_ok=True);b.write_bytes(p.read_bytes())
  p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);changed.append(rel)
observed={k:hashlib.sha256((root/k).read_bytes()).hexdigest() for k in expected}
assert observed==expected
(root/'reports').mkdir(exist_ok=True)
(root/'reports/deployment.json').write_text(json.dumps({'hashes':observed,'changed':changed},indent=2))
print(json.dumps({'root':str(root),'verified':len(observed),'changed':changed}))
'''.replace('MANIFEST',repr(manifest)).replace('PAYLOAD',repr(payload))
out=root/'reports/deploy_reviewed.py';out.parent.mkdir(exist_ok=True);out.write_text(code,encoding='utf-8')
if len(code.encode())>256*1024:raise RuntimeError('Deployment exceeds audit input limit')
print(json.dumps({'script':str(out),'files':len(manifest)}))
