import json,sqlite3
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06')
info=json.loads((root/'reports/latest_native_trace.json').read_text());out=Path(info['directory'])
reports={n:json.loads((out/(n+'.json')).read_text()) for n in ('result','status') if (out/(n+'.json')).exists()}
files=[{'name':p.name,'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()]
tables=[]
if (out/'native.sqlite').exists():
    with sqlite3.connect('file:'+str(out/'native.sqlite')+'?mode=ro',uri=True) as db:
        tables=[x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print(json.dumps({'directory':str(out),'reports':reports,'files':files,'tables':tables,'log_tail':(out/'nsys.log').read_text(errors='replace')[-5000:]}))
