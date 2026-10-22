"""ROS 2 reader plus an owned SQLite cache; preserves source CDR and times."""
import bisect, collections, hashlib, json, sqlite3, time
from pathlib import Path
from .model import pose_matrix

def source_bag(capture):
    capture=Path(capture).resolve()
    for p in (capture/'bag_unified',capture/'bag',capture):
        if (p/'metadata.yaml').is_file() or p.suffix=='.mcap':return p
    raise FileNotFoundError('Pass the session or bag directory containing metadata.yaml')

def stamp_ns(stamp):return int(stamp.sec)*10**9+int(stamp.nanosec)

def message_stamp(topic,msg,recorded):
    if hasattr(msg,'header'):return stamp_ns(msg.header.stamp)
    if topic=='/tf':
        stamps={stamp_ns(t.header.stamp) for t in msg.transforms}
        if len(stamps)!=1:raise ValueError('Mixed-time TF message cannot be one group')
        return next(iter(stamps))
    if topic=='/clock':return stamp_ns(msg.clock)
    if topic=='/sensor_visualizer/frame_index':return int(json.loads(msg.data)['simulation_time_ns'])
    return int(recorded)

def signature(bag):
    files=list(bag.glob('*.mcap')) if bag.is_dir() else [bag]
    return [{'name':str(p.resolve()),'bytes':p.stat().st_size,'mtime_ns':p.stat().st_mtime_ns} for p in sorted(files)]

def build_index(capture,cache):
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    capture=Path(capture).resolve();bag=source_bag(capture);cache=Path(cache).resolve()
    before=signature(bag);cache.parent.mkdir(parents=True,exist_ok=True)
    if cache.is_file():
        with sqlite3.connect(cache) as db:
            old=json.loads(db.execute('SELECT value FROM settings WHERE key=?',('signature',)).fetchone()[0])
        if old==before:return BagIndex(cache)
        raise ValueError('Source bag changed. Use a new cache path; stale cache was not overwritten.')
    temp=cache.with_suffix('.building.sqlite')
    if temp.exists():raise ValueError('Interrupted cache build retained: '+str(temp))
    reader=rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(bag),storage_id='mcap'),rosbag2_py.ConverterOptions('',''))
    types={t.name:t.type for t in reader.get_all_topics_and_types()}
    chosen={name:kind for name,kind in types.items() if kind in ('sensor_msgs/msg/PointCloud2','tf2_msgs/msg/TFMessage','sensor_msgs/msg/JointState','rosgraph_msgs/msg/Clock') or name in ('/excavator/root_pose','/sensor_visualizer/frame_index')}
    reader.set_filter(rosbag2_py.StorageFilter(topics=list(chosen)))
    classes={name:get_message(kind) for name,kind in chosen.items()}
    counts=collections.Counter();delays=[];frames={};started=time.monotonic();ordinal=0
    with sqlite3.connect(temp) as db:
        db.execute('PRAGMA journal_mode=OFF');db.execute('PRAGMA synchronous=OFF')
        db.executescript('CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT); CREATE TABLE messages(id INTEGER PRIMARY KEY,topic TEXT,stamp INTEGER,recorded INTEGER,data BLOB,sha256 TEXT); CREATE TABLE frames(id INTEGER PRIMARY KEY,stamp INTEGER UNIQUE,metadata TEXT);')
        while reader.has_next():
            topic,raw,recorded=reader.read_next();msg=deserialize_message(raw,classes[topic]);stamp=message_stamp(topic,msg,recorded)
            db.execute('INSERT INTO messages VALUES(?,?,?,?,?,?)',(ordinal,topic,stamp,recorded,raw,hashlib.sha256(raw).hexdigest()));ordinal+=1;counts[topic]+=1
            if stamp!=recorded:delays.append({'topic':topic,'stamp_ns':stamp,'recorded_ns':recorded,'delay_ns':recorded-stamp})
            frame=frames.setdefault(stamp,{'root_col':None,'joints_rad':{},'body_world_row':None})
            if topic=='/excavator/root_pose':
                p,q=msg.pose.position,msg.pose.orientation;frame['root_col']=pose_matrix([p.x,p.y,p.z],[q.x,q.y,q.z,q.w]).tolist()
            elif topic=='/joint_states':frame['joints_rad']=dict(zip(msg.name,msg.position))
            elif topic=='/sensor_visualizer/frame_index':
                value=json.loads(msg.data);frame.update(body_world_row=value.get('viewer_body_world_row'),logical_time_s=value.get('trajectory',{}).get('trajectory_time_s'))
            elif topic=='/tf':
                for t in msg.transforms:
                    if t.child_frame_id=='swing_coordinate' and t.header.frame_id=='world':
                        p,q=t.transform.translation,t.transform.rotation;frame['root_col']=pose_matrix([p.x,p.y,p.z],[q.x,q.y,q.z,q.w]).tolist()
            if ordinal%100==0:db.commit()
        # Native sidecar records the root reference even when its TF is split.
        group_file=capture/'groups.jsonl'
        if group_file.is_file():
            for line in group_file.read_text().splitlines():
                g=json.loads(line);expected=round(g['native_time_s']*1e9)
                candidates=[s for s in frames if abs(s-expected)<=2]
                if len(candidates)!=1:raise ValueError('Ambiguous native group stamp')
                frame=frames[candidates[0]];frame.update(root_col=list(map(list,zip(*g['root_world_matrix_row']))),logical_time_s=g['logical_time_s'])
        stamps=[r[0] for r in db.execute("SELECT DISTINCT stamp FROM messages WHERE topic LIKE '/lidar/%/points' ORDER BY stamp")]
        required={name for name,kind in chosen.items() if kind=='sensor_msgs/msg/PointCloud2'}|{'/tf','/joint_states','/clock'}
        errors=[]
        for index,stamp in enumerate(stamps):
            frame=frames[stamp];present={r[0] for r in db.execute('SELECT DISTINCT topic FROM messages WHERE stamp=?',(stamp,))}
            missing=sorted(required-present)
            if missing:errors.append({'group':index,'missing':missing})
            frame['group']=index;frame['stamp_ns']=stamp
            if frame.get('logical_time_s') is None:frame['logical_time_s']=(stamp-stamps[0])/1e9
            db.execute('INSERT INTO frames VALUES(?,?,?)',(index,stamp,json.dumps(frame)))
        report={'groups':len(stamps),'topics':dict(counts),'delayed_messages':len(delays),'delayed_groups':len({d['stamp_ns'] for d in delays}),'max_abs_record_header_difference_ns':max((abs(d['delay_ns']) for d in delays),default=0),'delays':delays,'missing':errors,'header_interval_ns_range':[min(b-a for a,b in zip(stamps,stamps[1:])),max(b-a for a,b in zip(stamps,stamps[1:]))] if len(stamps)>1 else [],'indexed_seconds':time.monotonic()-started,'image_topics_indexed':False,'signature_scope':'path/size/mtime for cache reuse; each indexed source CDR has SHA256; source files not rewritten'}
        for key,value in {'signature':before,'types':chosen,'report':report,'capture':str(capture)}.items():db.execute('INSERT INTO settings VALUES(?,?)',(key,json.dumps(value)))
        db.execute('CREATE INDEX by_stamp ON messages(stamp,id)');db.execute('CREATE INDEX by_recorded ON messages(recorded,id)');db.commit()
    if signature(bag)!=before:raise ValueError('Source bag changed during cache build')
    temp.replace(cache)
    cache.with_suffix('.audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return BagIndex(cache)

class BagIndex:
    def __init__(self,path):
        self.path=Path(path)
        with sqlite3.connect(self.path) as db:
            settings=dict(db.execute('SELECT key,value FROM settings'))
            self.frames=[json.loads(r[0]) for r in db.execute('SELECT metadata FROM frames ORDER BY id')]
        self.types=json.loads(settings['types']);self.report=json.loads(settings['report']);self.stamps=[f['stamp_ns'] for f in self.frames]
        if not self.frames or self.report['missing']:raise ValueError('Incomplete source groups: '+str(self.report['missing'][:3]))
    def messages(self,group,mode='synchronized'):
        stamp=self.stamps[group]
        with sqlite3.connect(self.path) as db:
            if mode=='synchronized':return list(db.execute('SELECT topic,data,stamp,recorded FROM messages WHERE stamp=? ORDER BY id',(stamp,)))
            end=self.stamps[group+1] if group+1<len(self.stamps) else max(self.stamps[-1]+100_000_000,max((d['recorded_ns'] for d in self.report['delays']),default=0)+1)
            return list(db.execute('SELECT topic,data,stamp,recorded FROM messages WHERE recorded>=? AND recorded<? ORDER BY recorded,id',(stamp,end)))
