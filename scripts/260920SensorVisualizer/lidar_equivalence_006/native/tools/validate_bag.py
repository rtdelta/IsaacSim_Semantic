"""Post-run ROS standard decoding; never on the capture path."""
import collections,json,math,struct,sys
from pathlib import Path
import rosbag2_py
import numpy as np
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message

def validate(directory):
    out=Path(directory);manifest=json.loads((out/'sensor_manifest.json').read_text());sensors=manifest['sensors']
    reader=rosbag2_py.SequentialReader();reader.open(rosbag2_py.StorageOptions(uri=str(out/'bag'),storage_id='mcap'),rosbag2_py.ConverterOptions('',''))
    topic_types={t.name:t.type for t in reader.get_all_topics_and_types()}
    types={t:get_message(v) for t,v in topic_types.items()};stats={};errors=[];tf_edges=set();camera_calibration={};clock_stamps=set()
    spec=json.loads((out/'spec.json').read_text());warnings=[]
    expected={s['topic'] for s in sensors}|{s['info_topic'] for s in sensors if s['kind']=='camera'}|{'/tf','/clock','/joint_states'}
    mapping={s['topic']:s for s in sensors}
    info_mapping={s['info_topic']:s for s in sensors if s['kind']=='camera'}
    first_images={};tf_latest={};tf_ranges={};stamp_sets={};measurement_counts=collections.Counter();joint_ranges={};measurement_images={}
    window=json.loads((out/'engine_result.json').read_text())
    begin_ns=round(window['simulation_start_s']*1e9);end_ns=round(window['simulation_end_s']*1e9)
    while reader.has_next():
        topic,data,bag_time=reader.read_next();msg=deserialize_message(data,types[topic])
        st=stats.setdefault(topic,{'type':topic_types[topic],'messages':0,'bytes':0,'header_times':[],'bag_first_ns':bag_time,'bag_last_ns':bag_time,'frames':set()})
        st['messages']+=1;st['bytes']+=len(data);st['bag_last_ns']=bag_time
        header=getattr(msg,'header',None)
        if header:
            stamp=header.stamp.sec*10**9+header.stamp.nanosec;st['header_times'].append(stamp);st['frames'].add(header.frame_id)
            stamp_sets.setdefault(topic,set()).add(stamp)
            if begin_ns<stamp<=end_ns:measurement_counts[topic]+=1
        if topic=='/clock':clock_stamps.add(msg.clock.sec*10**9+msg.clock.nanosec)
        elif topic=='/joint_states':
            for name,pos in zip(msg.name,msg.position):
                interval=joint_ranges.setdefault(name,[pos,pos]);interval[0]=min(interval[0],pos);interval[1]=max(interval[1],pos)
        elif topic=='/tf':
            for tr in msg.transforms:
                tf_edges.add((tr.header.frame_id,tr.child_frame_id));tf_latest[tr.child_frame_id]=tr
                xyz=np.array([tr.transform.translation.x,tr.transform.translation.y,tr.transform.translation.z])
                interval=tf_ranges.setdefault(tr.child_frame_id,[xyz.copy(),xyz.copy()])
                interval[0]=np.minimum(interval[0],xyz);interval[1]=np.maximum(interval[1],xyz)
        elif topic in mapping:
            s=mapping[topic]
            if header.frame_id!=s['frame_id']:errors.append('Unexpected frame_id '+topic)
            if s['kind']=='camera':
                w,h=s['size'];channels=3 if msg.encoding=='rgb8' else 4 if msg.encoding=='rgba8' else None
                if (msg.width,msg.height)!=(w,h) or channels is None or len(msg.data)!=msg.step*msg.height:errors.append('Invalid image '+topic)
                st['image_encoding']=msg.encoding;st['resolution']=[msg.width,msg.height]
                if begin_ns<stamp<=end_ns:measurement_images[topic]=(bytes(msg.data),channels,w,h,s['id'])
                if topic not in first_images:
                    first_images[topic]=True
                    try:
                        from PIL import Image
                        Image.frombytes('RGB' if channels==3 else 'RGBA',(w,h),bytes(msg.data)).convert('RGB').save(out/(s['id']+'_first.png'))
                    except ImportError:pass
            else:
                fields={f.name:f for f in msg.fields};st['point_fields']=[{'name':f.name,'offset':f.offset,'datatype':f.datatype,'count':f.count} for f in msg.fields]
                count=msg.width*msg.height;st.setdefault('point_counts',[]).append(count)
                if not all(k in fields for k in ('x','y','z')) or len(msg.data)!=msg.row_step*msg.height:errors.append('Invalid cloud layout '+topic)
                elif count:
                    offsets=[fields[n].offset for n in ('x','y','z')];endian='>' if msg.is_bigendian else '<'
                    if any(fields[n].datatype!=7 for n in ('x','y','z')):raise RuntimeError('Unexpected native XYZ type')
                    finite=np.ones((msg.height,msg.width),dtype=bool)
                    for off in offsets:
                        values=np.ndarray((msg.height,msg.width),dtype=endian+'f4',buffer=msg.data,
                                          offset=off,strides=(msg.row_step,msg.point_step))
                        finite &= np.isfinite(values)
                    bad=int((~finite).sum())
                    st['nonfinite_xyz']=st.get('nonfinite_xyz',0)+bad
                    if bad:errors.append('Nonfinite cloud '+topic)
        elif topic in info_mapping:
            s=info_mapping[topic];c=s['calibration'];expected_d=[c[n] for n in ['k1','k2','k3','k4']]
            actual={'width':msg.width,'height':msg.height,'model':msg.distortion_model,'k':list(msg.k),'d':list(msg.d)}
            camera_calibration[topic]=actual
            if msg.distortion_model!='equidistant' or len(msg.d)!=4 or max(abs(a-b) for a,b in zip(msg.d,expected_d))>1e-6:errors.append('Fisheye distortion mismatch '+topic)
            for idx,n in [(0,'fx'),(4,'fy'),(2,'cx'),(5,'cy')]:
                if abs(msg.k[idx]-c[n])>1e-3:errors.append('Fisheye intrinsics mismatch '+topic+' '+n)
    for topic in sorted(expected):
        if stats.get(topic,{}).get('messages',0)==0:errors.append('Missing topic data '+topic)
    for topic,st in stats.items():
        times=st.pop('header_times');st['frames']=sorted(st['frames'])
        if times:
            st['header_first_ns']=min(times);st['header_last_ns']=max(times)
            st['duplicate_stamps']=len(times)-len(set(times));st['backward_stamps']=sum(b<a for a,b in zip(times,times[1:]))
            span=(max(times)-min(times))/1e9;st['effective_sim_hz']=(len(times)-1)/span if span else None
            st['stamps_absent_from_clock']=sum(t not in clock_stamps for t in times)
            if st['backward_stamps']:errors.append('Backward sensor stamps '+topic)
            if st['duplicate_stamps']:warnings.append('Repeated native header stamps '+topic)
        counts=st.pop('point_counts',[])
        if counts:st['points']={'min':min(counts),'max':max(counts),'mean':sum(counts)/len(counts)}
    wanted_frames={s['frame_id'] for s in sensors}|{'swing_coordinate'}
    missing_tf=wanted_frames-{c for p,c in tf_edges}
    if missing_tf:errors.append('TF missing sensor/root frames: '+str(sorted(missing_tf)))
    tf_comparison={}
    expected_path=out/'expected_final_transforms.json'
    if expected_path.exists():
        for child,value in json.loads(expected_path.read_text()).items():
            tr=tf_latest.get(child)
            if tr is None:continue
            q=tr.transform.rotation;t=tr.transform.translation
            actual_q=np.array([q.x,q.y,q.z,q.w]);wanted_q=np.array(value['quaternion_xyzw'])
            translation_error=float(np.linalg.norm(np.array([t.x,t.y,t.z])-np.array(value['translation'])))
            rotation_error=float(2*math.acos(min(1.,abs(float(np.dot(actual_q,wanted_q))))))
            tf_comparison[child]={'translation_error_m':translation_error,'rotation_error_rad':rotation_error,
              'translation_min':tf_ranges[child][0].tolist(),'translation_max':tf_ranges[child][1].tolist()}
            if translation_error>1e-3 or rotation_error>1e-3:errors.append('Final TF disagrees with USD '+child)
    sensor_sets=[stamp_sets.get(s['topic'],set()) for s in sensors]
    common_stamps=set.intersection(*sensor_sets) if sensor_sets else set()
    if window.get('publication_tail_updates') and not spec['multi_tick']:
        for s in sensors:
            if measurement_counts[s['topic']]!=window['frames']:errors.append('Measurement message count differs from native frame count '+s['topic'])
    if spec['schedule']=='frozen':warnings.append('Per-group frozen equivalence is checked separately by validate_groups.py; native extra messages remain in the bag.')
    for raw,channels,w,h,sid in measurement_images.values():
        try:
            from PIL import Image
            Image.frombytes('RGB' if channels==3 else 'RGBA',(w,h),raw).convert('RGB').save(out/(sid+'_measurement_last.png'))
        except ImportError:pass
    result={'ok':not errors,'errors':sorted(set(errors)),'warnings':warnings,'topics':stats,'expected_topics':sorted(expected),
         'tf_edges':sorted([list(e) for e in tf_edges]),'camera_calibration':camera_calibration,
         'tf_final_comparison':tf_comparison,'measurement_topic_counts':dict(measurement_counts),
         'all_sensor_common_stamps':len(common_stamps),
         'joint_ranges_rad':joint_ranges,
         'mcap_files':[{'name':p.name,'bytes':p.stat().st_size} for p in (out/'bag').glob('*.mcap')],
         'limits':['Standard streaming topics are independent, not custom synchronized groups.',
           'Camera info and sensor headers are checked; bag receive timestamps need not equal sensor acquisition timestamps.',
           'Finite XYZ and TF connectivity do not prove identical old-project pose or 3DGS physical alignment.']}
    (out/'validation.json').write_text(json.dumps(result,indent=2));return result
if __name__=='__main__':
    r=validate(sys.argv[1]);print(json.dumps({'ok':r['ok'],'errors':r['errors'],'topics':len(r['topics'])}));raise SystemExit(0 if r['ok'] else 1)
