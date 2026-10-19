import base64,gzip,json,sys
from pathlib import Path
source=Path(sys.argv[1]);o=json.loads(source.read_text(encoding='utf-8-sig'))
if o['status']!='succeeded':raise RuntimeError(o)
z=json.loads(o['result']['stdout'])
d=json.loads(gzip.decompress(base64.b64decode(z['data']))) if z.get('encoding')=='gzip-base64-json' else z
dest=Path(sys.argv[2]);dest.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:d[k] for k in ('experiment','sessions','gpu') if k in d},ensure_ascii=False,indent=2))
if 'kit_tail' in d: print(d['kit_tail'][-1800:])
