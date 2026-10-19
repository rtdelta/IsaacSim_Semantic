from pathlib import Path
import base64,gzip,json,subprocess
ROOT=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v04')
info=json.loads((ROOT/'reports/latest_experiment.json').read_text());out=Path(info['directory'])
result={'experiment':info,'files':[{ 'name':p.name,'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()]}
for name in ('capture_result.json','supervisor_result.json','sdk_probe.json','process.json'):
    p=out/name
    if p.exists():result[name]=json.loads(p.read_text())
result['sessions']={str(p.relative_to(out)):json.loads(p.read_text()) for p in out.rglob('session.json')}
result['kit_tail']=(out/'kit.log').read_text(errors='replace')[-12000:] if (out/'kit.log').exists() else None
result['supervisor_tail']=(out/'supervisor.log').read_text(errors='replace')[-4000:]
result['gpu']=subprocess.run(['nvidia-smi','--query-gpu=utilization.gpu,utilization.memory,memory.used','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=10).stdout
print(json.dumps({'encoding':'gzip-base64-json','data':base64.b64encode(gzip.compress(json.dumps(result).encode())).decode()}))
