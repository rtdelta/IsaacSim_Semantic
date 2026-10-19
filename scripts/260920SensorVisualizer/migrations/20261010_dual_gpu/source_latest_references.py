import json,re
from pathlib import Path
base=Path('/root/gpufree-data/IsaacSim_Asset')
start=base/'combine_stage/combine_scene_16_terrain_fisheye.usda'
seen=set();pending=[start];rows=[]
while pending:
    p=pending.pop()
    if p in seen:continue
    seen.add(p)
    if not p.exists():rows.append({'path':str(p),'missing':True});continue
    if p.suffix.lower() not in {'.usda','.usd'}:continue
    raw=p.read_bytes()
    if not raw.startswith(b'#usda'):continue
    refs=sorted(set(re.findall(r'@([^@\r\n]+)@',raw.decode('utf-8',errors='replace'))))
    info=[]
    for v in refs:
        if '://' in v:info.append({'reference':v,'external':True});continue
        q=(Path(v) if v.startswith('/') else p.parent/v).resolve()
        info.append({'reference':v,'path':str(q),'exists':q.exists()})
        if q.exists() and q.suffix in {'.usda','.usd'}:pending.append(q)
    rows.append({'path':str(p),'references':info})
extras=Path('/root/gpufree-data/semantic/scripts/260907LidarVisualizer')
print(json.dumps({'latest_layer_graph':rows,'legacy_lidar_files':sum(1 for p in extras.rglob('*') if p.is_file()),
    'source_sdk_pxrlib':[str(p) for p in Path('/root/isaacsim/extscache').glob('omni.usd.libs-*/pxr')]}))
