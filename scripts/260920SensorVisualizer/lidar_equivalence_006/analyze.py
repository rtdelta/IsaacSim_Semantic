"""Hash-select actual MCAP messages, compare sensor-local geometry and scene state."""
import collections,hashlib,json,sys
from pathlib import Path
import numpy as np
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
def read(p):return json.loads(p.read_text())
def sha(a):return hashlib.sha256(np.ascontiguousarray(a,dtype='<f4').tobytes()).hexdigest()
def xyz(m):
    f={x.name:x for x in m.fields};coords=[]
    for axis in ('x','y','z'):
        a=f[axis];assert a.datatype==7 and a.count==1
        coords.append(np.ndarray((m.height,m.width),dtype=('>' if m.is_bigendian else '<')+'f4',buffer=m.data,offset=a.offset,strides=(m.row_step,m.point_step)).reshape(-1))
    return np.ascontiguousarray(np.stack(coords,axis=1),dtype='<f4')
def stats(a):
    d=np.linalg.norm(a.astype(np.float64),axis=1)
    return {'points':len(a),'nonfinite':int((~np.isfinite(a).all(axis=1)).sum()),'zero':int((a==0).all(axis=1).sum()),'near_counts':{str(v):int((d<=v).sum()) for v in (.1,.5,1.,2.,5.,10.)},'range_percentiles':dict(zip(('min','p1','p50','p99','max'),np.percentile(d,[0,1,50,99,100]).tolist())) if len(a) else None}
def bag_verify(cap,family):
    files=sorted((cap/'formal_clouds').glob('*/*.json'));expected=[read(f) for f in files]
    mcap=list(cap.rglob('*.mcap'));assert len(mcap)==1,[str(p) for p in mcap]
    reader=rosbag2_py.SequentialReader();reader.open(rosbag2_py.StorageOptions(uri=str(mcap[0].parent),storage_id='mcap'),rosbag2_py.ConverterOptions('',''))
    reader.set_filter(rosbag2_py.StorageFilter(topics=['/lidar/'+x['sensor']+'/points' for x in expected]));typ=get_message('sensor_msgs/msg/PointCloud2')
    matched=collections.defaultdict(list);same=collections.defaultdict(set);idx=0
    while reader.has_next():
        topic,cdr,t=reader.read_next();msg=deserialize_message(cdr,typ);stamp=msg.header.stamp.sec*10**9+msg.header.stamp.nanosec
        candidates=[r for r in expected if topic=='/lidar/'+r['sensor']+'/points' and abs(r['stamp_ns']-stamp)<=2]
        if candidates:
            data=xyz(msg);h=sha(data)
            for e in candidates:
                key=f"{e['group']}/{e['sensor']}";same[key].add(h)
                if h==e['sha256_xyz']:matched[key].append({'lidar_message_ordinal':idx,'cdr_sha256':hashlib.sha256(cdr).hexdigest(),'record_stamp_ns':t,'header_stamp_ns':stamp,'frame_id':msg.header.frame_id})
        idx+=1
    rows=[]
    for e in expected:
        k=f"{e['group']}/{e['sensor']}";path=cap/'formal_clouds'/f"{e['group']:03d}"/(e['sensor']+'.npy');a=np.load(path,allow_pickle=False);assert sha(a)==e['sha256_xyz']
        rows.append({**e,**stats(a),'matching_mcap_messages':len(matched[k]),'unique_xyz_at_same_stamp':len(same[k]),'selected_last_match':matched[k][-1] if matched[k] else None})
    return {'passed':bool(expected) and all(r['matching_mcap_messages']>0 for r in rows),'mcap_path':str(mcap[0]),'rows':rows}
def compare(a,b):
    sa,sb=stats(a),stats(b)
    result={'left':sa,'right':sb,'identical_xyz':a.shape==b.shape and np.array_equal(a,b),'point_count_delta':len(b)-len(a)}
    try:
        from scipy.spatial import cKDTree
        for label,x,y in [('left_to_right',a,b),('right_to_left',b,a)]:
            if len(x) and len(y):
                d,_=cKDTree(y).query(x,k=1,workers=1)
                result[label]={'median_m':float(np.median(d)),'p95_m':float(np.percentile(d,95)),'max_m':float(d.max()),'over_1cm':int((d>.01).sum()),'over_5cm':int((d>.05).sum()),'over_20cm':int((d>.2).sum())}
    except ImportError:result['nearest_neighbor']='scipy unavailable; not installed'
    return result
def main(out):
    out=Path(out);dest=out/'analysis';dest.mkdir(exist_ok=True);p=read(out/'progress.json');allrows=[];verified=[];comparisons=[];states=[]
    completed={(c['family'],c['round']) for c in p['completed'] if c['exit_code']==0}
    for case in p['completed']:
        cap=Path(case['directory'])/'capture'
        if case['exit_code']:continue
        v=bag_verify(cap,case['family']);v.update(family=case['family'],round=case['round']);verified.append(v)
        for r in v['rows']:allrows.append(dict(r,family=case['family'],round=case['round']))
    for repeat in (1,2,3):
        if ('legacy',repeat) not in completed or ('native',repeat) not in completed:continue
        for group in range(3):
            ac=out/'legacy'/f'round_{repeat:02d}'/'capture';bc=out/'native'/f'round_{repeat:02d}'/'capture'
            if not (ac/'formal_clouds'/f'{group:03d}').exists() or not (bc/'formal_clouds'/f'{group:03d}').exists():continue
            for a in sorted((ac/'formal_clouds'/f'{group:03d}').glob('*.npy')):
                b=bc/'formal_clouds'/f'{group:03d}'/a.name
                comparisons.append({'round':repeat,'group':group,'sensor':a.stem,**compare(np.load(a,allow_pickle=False),np.load(b,allow_pickle=False))})
            aa=read(ac/'state_evidence'/f'{group:03d}.json');bb=read(bc/'state_evidence'/f'{group:03d}.json');diff=[];maxpose=0.
            for key,value in aa['meshes'].items():
                other=bb['meshes'].get(key)
                if other is None:diff.append({'mesh':key,'missing':'native'});continue
                err=float(np.max(np.abs(np.array(value['world_matrix_row'])-np.array(other['world_matrix_row']))));maxpose=max(maxpose,err)
                changed=[k for k in ('visibility','purpose','points','points_sha256','face_indices_sha256') if value[k]!=other[k]]
                if changed or err>1e-5:diff.append({'mesh':key,'pose_max_abs_error':err,'changed':changed})
            param=[]
            for key,vals in aa['sensor_attributes'].items():
                other=bb['sensor_attributes'].get(key,{})
                for k,v in vals.items():
                    if k.startswith('omni:sensor:') and v!=other.get(k):param.append({'sensor':key,'parameter':k,'legacy':v,'native':other.get(k)})
            states.append({'round':repeat,'group':group,'mesh_count_legacy':len(aa['meshes']),'mesh_count_native':len(bb['meshes']),'max_mesh_world_matrix_error':maxpose,'mesh_differences':diff,'sensor_parameter_differences':param})
    repeatability=[]
    for family in ('legacy','native'):
        base=out/family/'round_01/capture/formal_clouds'
        for repeat in (2,3):
            if (family,1) not in completed or (family,repeat) not in completed:continue
            for group in range(3):
                for a in sorted((base/f'{group:03d}').glob('*.npy')):
                    b=out/family/f'round_{repeat:02d}'/'capture/formal_clouds'/f'{group:03d}'/a.name
                    if b.exists():repeatability.append({'family':family,'round':repeat,'group':group,'sensor':a.stem,**compare(np.load(a,allow_pickle=False),np.load(b,allow_pickle=False))})
    summary={'bag_verifications_passed':all(v['passed'] for v in verified),'verified_cases':len(verified),'formal_cloud_samples':len(allrows),'cross_pairs':len(comparisons),'cross_identical_xyz':sum(c['identical_xyz'] for c in comparisons),'max_abs_count_delta':max((abs(c['point_count_delta']) for c in comparisons),default=None),'same_chain_repeat_pairs':len(repeatability),'same_chain_repeat_identical':sum(c['identical_xyz'] for c in repeatability),'state_alignment':states,'focus_first_group':[c for c in comparisons if c['round']==1 and c['group']==0 and c['sensor'] in ('MyNZ3_left','MyNZ3_right','MyNZ3_front','MyAiry_left')]}
    for name,value in [('bag_verifications',verified),('cross_comparisons',comparisons),('repeatability',repeatability),('summary',summary)]:
        (dest/(name+'.json')).write_text(json.dumps(value,indent=2))
    print(json.dumps({k:v for k,v in summary.items() if k not in ('state_alignment','focus_first_group')},indent=2))
if __name__=='__main__':main(sys.argv[1])
