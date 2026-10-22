"""Real loopback HTTP export/import using an owned recorded trajectory; no token logging."""
import json,re,sys,threading,urllib.request,urllib.parse
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06');sys.path.insert(0,str(root))
from sensor_visualizer_v06.web_service import WebService,make_server
from sensor_visualizer_v06.trajectory import Trajectory
d=root/'reports/native_owner';owner=json.loads((d/'owner.json').read_text());original=json.loads((d/'interaction.json').read_text())['trajectory']
service=WebService(root,'/root/gpufree-data/semantic/output/sensor_visualizer/v06',owner['socket'])
server=None
try:
    server=make_server(service,port=17876)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));url='http://127.0.0.1:17876'
    html=opener.open(url,timeout=2).read().decode();capability=re.search(r'window.CONTROL_TOKEN="([^"]+)"',html).group(1)
    archive=opener.open(url+'/api/export?'+urllib.parse.urlencode({'path':original}),timeout=3).read()
    request=urllib.request.Request(url+'/api/import_zip',data=archive,headers={'Content-Type':'application/zip','X-SV06-Token':capability})
    result=json.load(opener.open(request,timeout=3));a=Trajectory.load(original);b=Trajectory.load(result['path'])
    assert abs(a.duration-b.duration)<1e-9 and len(a.states)==len(b.states)
    for t in (0,.1,.2,a.duration):
        left,right=a.sample(t),b.sample(t)
        for field in ('position_world_m','quaternion_xyzw'):
            assert all(abs(u-v)<1e-9 for u,v in zip(left[field],right[field]))
        assert left['joints_deg']==right['joints_deg'] and left['mounts']==right['mounts']
    report={'passed':True,'http_export_import_roundtrip':True,'rows':result['rows'],'imported_path':result['path'],
        'duration_s':a.duration,'zip_bytes':len(archive),'capability_output':'omitted'}
    (d/'http_trajectory.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    service.closed=True
    if server:server.shutdown();server.server_close();thread.join(timeout=2)
