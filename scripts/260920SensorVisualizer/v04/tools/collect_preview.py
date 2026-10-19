from pathlib import Path
import argparse,base64,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--ops',required=True);a=p.parse_args()
r=subprocess.run([sys.executable,'-X','utf8',a.ops,'exec','--target','isaac-new','--task','sv04-deploy-20261008',
    '--purpose','Review four decoded camera images from native acceptance','--script',str(ROOT/'tools/remote_preview_images.py'),
    '--intent','read','--timeout','30'],capture_output=True,text=True,encoding='utf-8',timeout=60)
if r.returncode:raise RuntimeError(r.stderr or r.stdout)
e=json.loads(r.stdout)
if e['result']['exit_code']:raise RuntimeError(e['result']['stderr'])
data=json.loads(e['result']['stdout']);dest=ROOT/'reports/native_camera_preview.jpg'
dest.parent.mkdir(exist_ok=True);dest.write_bytes(base64.b64decode(data['base64']))
(dest.with_suffix('.json')).write_text(json.dumps({'source':data['source'],'operation_id':e['operation_id']},indent=2),encoding='utf-8')
print(str(dest))
