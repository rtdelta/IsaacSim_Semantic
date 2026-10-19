import json,subprocess,sys,time,urllib.request,uuid,re
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v05');directory=root/'reports/native_owner'
owner=json.loads((directory/'owner.json').read_text());log=(directory/'web_test.log').open('ab')
p=subprocess.Popen(['/usr/bin/python3',str(root/'run_web.py'),'--port','17866','--socket',owner['socket']],
    stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);log.close()
url='http://127.0.0.1:17866';opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));values=[]
try:
    end=time.monotonic()+5
    while True:
        try:html=opener.open(url,timeout=1).read().decode();break
        except OSError:
            if time.monotonic()>end:raise
            time.sleep(.1)
    for _ in range(120):
        begin=time.monotonic();s=json.load(opener.open(url+'/api/status',timeout=2));values.append((time.monotonic()-begin)*1000)
        assert s['engine']['phase']=='interactive_ready',s['engine']
        time.sleep(.1)
    values.sort();report={'passed':True,'requests':len(values),'http_get_p50_ms':values[len(values)//2],
        'http_get_p95_ms':values[int(.95*len(values))],'http_get_max_ms':max(values),
        'note':'Same-host loopback HTTP responsiveness; excludes human-visible remote desktop/browser input latency'}
    (directory/'http_runtime.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    p.terminate()
    try:p.wait(timeout=5)
    except subprocess.TimeoutExpired:p.kill();p.wait(timeout=5)
