"""Independent closed-MCAP CDR, payload, TF and schedule validation."""
import hashlib
import io
import json
from fractions import Fraction
from pathlib import Path
import uuid
import numpy as np
from .common import cjson, digest, file_hash, save_json, source_ns, utc, ContractError
from .sensor_backend import pose_error


CHECKS = ['commit_presence','topic_set','cdr_hashes','payload_hashes','header_times','source_times',
          'state_epochs','freshness','tf_consistency','calibration','point_layout','schedule_completeness']


def ns(stamp):
    if not 0 <= stamp.nanosec < 10**9:
        raise ContractError('header_times', 'ROS nanoseconds out of range')
    return stamp.sec*10**9+stamp.nanosec


def column_pose(position, quaternion):
    """Independent ROS column-vector conversion, not the production Gf helper."""
    p, q = np.asarray(position, float), np.asarray(quaternion, float)
    if not np.isfinite(p).all() or not np.isfinite(q).all() or abs(np.dot(q,q)-1) > 1e-6:
        raise ContractError('tf_consistency', 'Invalid ROS pose or quaternion')
    x,y,z,w = q
    m = np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w),p[0]],
                  [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w),p[1]],
                  [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y),p[2]], [0.,0.,0.,1.]])
    return m


def ros_pose(value):
    return column_pose([value.position.x,value.position.y,value.position.z],
                       [value.orientation.x,value.orientation.y,value.orientation.z,value.orientation.w])


def ros_transform(value):
    return column_pose([value.translation.x,value.translation.y,value.translation.z],
                       [value.rotation.x,value.rotation.y,value.rotation.z,value.rotation.w])


def require(condition, code, message):
    if not condition:
        raise ContractError(code, message)


def validate_group(ordinary, commit, registry, metadata, previous_refs, expected_group_id):
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    from PIL import Image
    require(commit.get('schema_version') == 1, 'commit_presence', 'Unknown group commit schema')
    descriptors = [{'ordinal':i, 'topic':topic, 'ros_type':typ, 'cdr_nbytes':len(raw), 'cdr_sha256':hashlib.sha256(raw).hexdigest()}
                   for i,(topic,typ,raw,stamp) in enumerate(ordinary)]
    require(descriptors == commit['messages'] and digest(descriptors) == commit['group_hash'], 'cdr_hashes', 'Actual raw CDR or ordered topic/type commit hash differs')
    require(commit['message_count'] == len(ordinary) == 3*len(registry['cameras'])+len(registry['lidars'])+5,
            'topic_set', 'Wrong ordinary message count')
    decoded = {topic: deserialize_message(raw,get_message(typ)) for topic,typ,raw,stamp in ordinary}
    require(len(decoded) == len(ordinary), 'topic_set', 'Duplicate group topic')
    from .messages import topics,type_name
    required={t:type_name(c) for t,c in topics(registry).items() if t not in ('/sensor_visualizer/group_commit','/sensor_visualizer/run_metadata','/sensor_visualizer/camera_metadata')}
    require({t:typ for t,typ,raw,stamp in ordinary}==required,'topic_set','Actual ordinary topics/types differ from selected registry')
    frame = json.loads(decoded['/sensor_visualizer/frame_index'].data)
    require(frame['schema_version'] == 3, 'state_epochs', 'Unknown frame_index schema')
    require(frame['group_id'] == expected_group_id, 'schedule_completeness', 'Output group sequence is not continuous')
    for key in ('recording_id','epoch_id','segment_id','group_id','target_index','target_step','simulation_time_ns','state_sha256','sync_checks'):
        require(frame[key] == commit[key], 'commit_presence', 'Frame/commit identity differs: '+key)
    for key in ('recording_id','epoch_id','segment_id','backend','policy'):
        require(frame[key] == metadata[key], 'state_epochs', 'Frame differs from segment identity: '+key)
    time_ns = int(frame['simulation_time_ns'])
    state = frame['state']
    require(digest(state) == frame['state_sha256'], 'cdr_hashes', 'Actual decoded state CJSON hash differs')
    require(state['physical_step'] == frame['target_step'] and state['sim_time_ns'] == frame['simulation_time_ns']
            and state['epoch_id'] == frame['epoch_id'] and state['scene_generation'] == metadata['scene_generation'],
            'state_epochs', 'State does not belong to exact target physics step and scene instance')
    for key in ('state_revision','mount_revision','calibration_revision'):
        require(state[key] == frame[key], 'state_epochs', 'State revision differs')
    for key in ('mount_revision','calibration_revision'):
        require(frame[key] == registry[key] == metadata[key], 'state_epochs', 'Cross-mount or cross-calibration group')
    expected = sorted([e['sensor_id'] for k in ('cameras','lidars') for e in registry[k]])
    require(frame['expected_sensor_ids'] == expected == sorted(state['sensor_world_matrices_usd']), 'topic_set', 'State or frame has the wrong sensor selection')
    require(sorted(frame['cameras']) == sorted(c['id'] for c in registry['cameras']) and sorted(frame['lidars']) == sorted(c['id'] for c in registry['lidars']), 'topic_set', 'Missing or extra sensor evidence')
    expected_step = metadata['first_target_step'] + frame['target_index']*metadata['sampling_stride_steps']
    expected_time = int(metadata['sim_origin_ns']) + round(Fraction((frame['target_step']-metadata['physical_step_origin'])*10**9,metadata['physics_hz']))
    require(frame['target_step'] == expected_step and abs(time_ns-expected_time) <= 2, 'source_times', 'Target step or rational physics grid differs')
    for topic,typ,raw,stamp in ordinary:
        require(stamp == time_ns, 'header_times', 'MCAP log time differs from physics time')
        msg = decoded[topic]
        if hasattr(msg, 'header'):
            require(ns(msg.header.stamp) == time_ns, 'header_times', 'Header differs from target time')
    require(ns(decoded['/clock'].clock) == time_ns, 'header_times', 'Clock differs from physics time')
    translation_max = angle_max = 0.0
    delta_max = 0
    sensor_evidence = [e for k in ('cameras','lidars') for e in frame[k].values()]
    for evidence in sensor_evidence:
        sid = evidence['sensor_id']
        require(evidence['ownership'] == 'owned_cpu' and evidence['source_time_provenance']['clock_domain'] == 'physics_simulation'
                and 'ReferenceTime' in evidence['source_time_provenance']['mapping_method'], 'source_times', 'Missing same-event physical source provenance')
        actual_ns = source_ns(evidence['source_time_s'])
        error_ns = actual_ns-time_ns
        require(str(actual_ns) == evidence['source_time_ns'] and str(error_ns) == evidence['source_time_error_ns'] and abs(error_ns) <= 2,
                'source_times', 'Raw source seconds, integer conversion or exact physical target differ')
        require(evidence['to_world'] == state['sensor_world_matrices_usd'][sid], 'tf_consistency', 'Evidence does not use immutable historical actual sensor state')
        require(int(state['snapshot_monotonic_ns']) <= int(evidence['received_monotonic_ns']) <= int(evidence['copy_completed_monotonic_ns']),
                'state_epochs', 'Invalid state/completion/owned-copy phase order')
        tr, angle = pose_error(evidence['to_world'], evidence['rendered_to_world'])
        require(tr <= .001 and angle <= .0001, 'tf_consistency', 'Recomputed rendered pose error exceeds the contract')
        require(abs(tr-evidence['translation_error_m']) <= 1e-9 and abs(angle-evidence['rotation_error_rad']) <= 1e-9,
                'tf_consistency', 'Producer pose error differs from independent recomputation')
        ref = evidence['native_ref']
        require(ref['kind'] == 'rational_time' and int(ref['denominator']) > 0 and bool(ref['scope']), 'freshness', 'Unsupported or malformed native reference')
        native_time = Fraction(int(ref['numerator']),int(ref['denominator']))
        key = (frame['epoch_id'], sid, ref['scope'])
        require(key not in previous_refs or native_time > previous_refs[key], 'freshness', 'Duplicate or old native event')
        previous_refs[key] = native_time
        delta_max, translation_max, angle_max = max(delta_max,abs(error_ns)), max(translation_max,tr), max(angle_max,angle)
    children = {}
    transforms = decoded['/tf'].transforms
    require(len(transforms) == 2+len(expected), 'tf_consistency', 'Wrong TF cardinality')
    for transform in transforms:
        require(ns(transform.header.stamp) == time_ns and transform.child_frame_id not in children, 'tf_consistency', 'Duplicate TF child or wrong stamp')
        children[transform.child_frame_id] = (transform.header.frame_id, ros_transform(transform.transform))
    world = registry['world_frame']
    require(children[registry['horizontal_frame']][0]==world and children[registry['root_frame']][0]==registry['horizontal_frame'],
            'tf_consistency','TF must use world -> horizontal -> root')
    require(all(children[e['frame_id']][0]==registry['root_frame'] for k in ('cameras','lidars') for e in registry[k]),'tf_consistency','Sensor TF parent must be actual robot root')
    def world_matrix(frame_id, visited=None):
        if frame_id == world:
            return np.eye(4)
        visited = set() if visited is None else visited
        require(frame_id not in visited and frame_id in children, 'tf_consistency', 'TF cycle or missing parent')
        visited.add(frame_id)
        parent, matrix = children[frame_id]
        return world_matrix(parent,visited)@matrix
    expected_root = column_pose(state['root']['position_m'], state['root']['orientation_xyzw'])
    require(np.allclose(world_matrix(registry['root_frame']), expected_root, atol=1e-6, rtol=0), 'tf_consistency', 'TF root differs from actual root state')
    require(np.allclose(ros_pose(decoded['/excavator/root_pose'].pose),expected_root,atol=1e-6,rtol=0), 'tf_consistency', 'Root PoseStamped differs from actual root')
    require(np.allclose(world_matrix(registry['horizontal_frame']),column_pose(state['horizontal']['position_m'],state['horizontal']['orientation_xyzw']),atol=1e-6,rtol=0), 'tf_consistency', 'Horizontal actual state differs')
    joints = decoded['/joint_states']
    for field, state_field in (('name','names'),('position','position'),('velocity','velocity'),('effort','effort')):
        require(list(getattr(joints,field)) == state['joints'][state_field], 'tf_consistency', 'Joint actual state differs')
    for camera in registry['cameras']:
        short, prefix = camera['id'], camera['topic_prefix']
        e = frame['cameras'][short]
        msg = decoded[prefix+'/image_raw/compressed']
        image_bytes = bytes(msg.data)
        require(msg.format == 'rgb8; png compressed rgb8' and msg.header.frame_id == camera['frame_id'], 'calibration', 'Wrong image format or optical frame')
        require(hashlib.sha256(image_bytes).hexdigest() == e['encoded_payload_sha256'] and len(image_bytes) == e['encoded_nbytes'], 'payload_hashes', 'PNG bytes differ')
        with Image.open(io.BytesIO(image_bytes)) as image:
            require(image.format == 'PNG' and image.mode == 'RGB', 'payload_hashes', 'Payload must be lossless RGB PNG')
            pixels = np.asarray(image)
            require(list(pixels.shape) == e['shape'] == [1080,1920,3] and pixels.dtype == np.uint8,
                    'calibration', 'Actual PNG dimensions or channel order differ')
            require(hashlib.sha256(pixels.tobytes()).hexdigest() == e['raw_payload_sha256'] and pixels.nbytes == e['raw_nbytes'], 'payload_hashes', 'Decoded RGB pixels differ from owned raw hash')
        cal, info = camera['calibration'], decoded[prefix+'/camera_info']
        v = cal['intrinsics']
        require(info.width == cal['width'] and info.height == cal['height'] and info.distortion_model == 'equidistant'
                and list(info.d) == [v['k%d'%i] for i in range(1,5)] and list(info.k) == [v['fx'],0.,v['cx'],0.,v['fy'],v['cy'],0.,0.,1.], 'calibration', 'CameraInfo differs from actual fisheye calibration')
        optical_world = np.asarray(e['to_world']).T@np.diag([1.,-1.,-1.,1.])
        require(np.allclose(world_matrix(camera['frame_id']),optical_world,atol=1e-6,rtol=0)
                and np.allclose(ros_pose(decoded[prefix+'/pose'].pose),optical_world,atol=1e-6,rtol=0), 'tf_consistency', 'Optical TF/pose differs from historical USD camera convention')
    for lidar in registry['lidars']:
        e, msg = frame['lidars'][lidar['id']], decoded[lidar['topic']]
        raw = bytes(msg.data)
        require(msg.height == 1 and msg.width == e['points'] and msg.point_step == 12 and msg.row_step == msg.width*12
                and not msg.is_bigendian and msg.is_dense and len(raw) == msg.row_step == e['raw_nbytes'], 'point_layout', 'PointCloud2 layout differs')
        require([(f.name,f.offset,f.datatype,f.count) for f in msg.fields] == [('x',0,7,1),('y',4,7,1),('z',8,7,1)], 'point_layout', 'Unexpected point field or padding')
        require(np.isfinite(np.frombuffer(raw,dtype='<f4')).all() and hashlib.sha256(raw).hexdigest() == e['raw_payload_sha256'], 'payload_hashes', 'Decoded XYZ differs or is nonfinite')
        require(msg.header.frame_id == lidar['frame_id'] and np.allclose(world_matrix(lidar['frame_id']),np.asarray(e['to_world']).T,atol=1e-6,rtol=0), 'tf_consistency', 'LiDAR local/world transform differs')
    checks=frame['sync_checks']
    require(all(checks.get(k) is True for k in ('all_sensors_present','source_time_ok','pose_ok','freshness_ok','state_epoch_ok'))
            and checks['max_abs_source_time_error_ns']==str(delta_max)
            and abs(checks['max_translation_error_m']-translation_max)<=1e-9
            and abs(checks['max_rotation_error_rad']-angle_max)<=1e-9,'source_times','Producer synchronization summary differs from independent recomputation')
    return frame, {'source_ns':delta_max, 'translation_m':translation_max, 'rotation_rad':angle_max},decoded


def validate_recording(directory):
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from std_msgs.msg import String
    directory = Path(directory)
    started = utc()
    session_path=directory/('readback_session_input.json' if (directory/'readback_session_input.json').exists() else 'session.json')
    session = json.loads(session_path.read_text())
    job = json.loads((directory/'job_spec.json').read_text())
    errors, frames, input_files = [], [], []
    previous_refs = {}
    checks = {k:{'passed':None,'checked_items':0,'failed_items':0,'reason':'not yet executed','evidence_paths':[]} for k in CHECKS}
    message_count = commits_seen = 0
    maximum = {'source_ns':0,'translation_m':0.0,'rotation_rad':0.0}
    segment_reports = []
    first_root=None
    motion_max_translation=motion_max_rotation=0.
    geometry_rows=[]
    geometry_spec=json.loads((directory/'diagnostic_geometry.json').read_text()) if (directory/'diagnostic_geometry.json').exists() else None
    diagnostic_history={}
    if geometry_spec and (directory/'diagnostic_states.jsonl').exists():
        with (directory/'diagnostic_states.jsonl').open() as file:
            for line in file:
                state=json.loads(line)['data']
                diagnostic_history[state['physical_step']]=state
    def summary(frame):
        return {k:frame[k] for k in ('recording_id','epoch_id','segment_id','group_id','target_index','target_step','simulation_time_ns','mount_revision','calibration_revision')}
    for bag in sorted(directory.glob('epochs/*/segments/*/bag_unified')):
        ordinary, metadata, registry, segment_frames = [], None, None, []
        segment_messages=0
        segment_maximum={'source_ns':0,'translation_m':0.0,'rotation_rad':0.0}
        reader = rosbag2_py.SequentialReader()
        try:
            reader.open(rosbag2_py.StorageOptions(uri=str(bag),storage_id='mcap'),rosbag2_py.ConverterOptions('',''))
            types = {t.name:t.type for t in reader.get_all_topics_and_types()}
            while reader.has_next():
                topic, raw, timestamp = reader.read_next()
                message_count += 1
                segment_messages += 1
                if topic in ('/sensor_visualizer/run_metadata','/sensor_visualizer/camera_metadata'):
                    require(not ordinary and not segment_frames, 'state_epochs', 'Segment metadata must occur once before the first group')
                    value = json.loads(deserialize_message(raw,String).data)
                    if topic.endswith('/run_metadata'):
                        require(metadata is None and value['schema_version'] == 3, 'state_epochs', 'Duplicate or unknown run metadata')
                        metadata = value
                        for field,filename in [('job_spec_sha256','job_spec.json'),('capabilities_sha256','capabilities.json'),('source_manifest_sha256','source_manifest.json'),('asset_manifest_sha256','asset_manifest.json'),('render_profile_sha256','render_profile.json')]:
                            require(metadata[field]==file_hash(directory/filename),'cdr_hashes','Segment metadata file hash differs: '+filename)
                    else:
                        require(registry is None and value['schema_version'] == 3, 'calibration', 'Duplicate or unknown sensor registry')
                        registry = value
                        require(metadata is not None and digest(registry)==metadata['registry_snapshot_sha256'],'calibration','Actual registry snapshot hash differs')
                    continue
                if topic == '/sensor_visualizer/group_commit':
                    commits_seen += 1
                    require(metadata is not None and registry is not None, 'commit_presence', 'Group lacks actual segment metadata')
                    commit = json.loads(deserialize_message(raw,String).data)
                    require(timestamp == int(commit['simulation_time_ns']), 'header_times', 'Commit log time differs')
                    frame, error,decoded = validate_group(ordinary,commit,registry,metadata,previous_refs,len(frames))
                    root=column_pose(frame['state']['root']['position_m'],frame['state']['root']['orientation_xyzw']).T
                    if first_root is None:first_root=root
                    tr,ang=pose_error(first_root,root)
                    motion_max_translation=max(motion_max_translation,tr)
                    motion_max_rotation=max(motion_max_rotation,ang)
                    if geometry_spec:
                        from .geometry_diagnostics import measure
                        measurement=measure(frame,decoded,registry,geometry_spec)
                        previous=diagnostic_history.get(frame['target_step']-1)
                        if previous:
                            wrong=dict(frame,state=previous)
                            measurement['one_physical_step_shift']=measure(wrong,decoded,registry,geometry_spec)
                        geometry_rows.append(measurement)
                    frames.append(summary(frame))
                    segment_frames.append(summary(frame))
                    for k in CHECKS[:-1]:
                        checks[k].update(passed=True, checked_items=checks[k]['checked_items']+1, reason='independently recomputed from actual closed MCAP CDR and decoded payloads')
                    maximum = {k:max(maximum[k],error[k]) for k in maximum}
                    segment_maximum={k:max(segment_maximum[k],error[k]) for k in segment_maximum}
                    ordinary = []
                else:
                    ordinary.append((topic,types[topic],raw,timestamp))
            require(not ordinary, 'commit_presence', 'MCAP ended with an incomplete uncommitted group')
            segment_reports.append({'bag':bag.relative_to(directory).as_posix(), 'groups':len(segment_frames), 'frames':segment_frames,
                                    'messages':segment_messages,'maximum':segment_maximum})
        except Exception as exc:
            code = getattr(exc,'code','readback_error')
            if code in checks:
                checks[code].update(passed=False,failed_items=checks[code]['failed_items']+1,reason=str(exc))
            errors.append({'code':code,'message':str(exc),'group':None,'sensor_id':None,'topic':None,'evidence_paths':[bag.relative_to(directory).as_posix()]})
        finally:
            del reader
        for p in sorted(bag.rglob('*')):
            if p.is_file():
                input_files.append({'path':p.relative_to(directory).as_posix(),'format':'mcap' if p.suffix=='.mcap' else 'yaml',
                                    'size_bytes':p.stat().st_size,'sha256':file_hash(p),'produced_by':'P6'})
    scheduled = [json.loads(line)['data'] for line in (directory/'schedule.jsonl').read_text().splitlines()
                 if json.loads(line)['event_type']=='scheduled']
    requested = job['capture']['requested_groups']
    complete = len(frames) == len(scheduled) == requested and session['counts']['written'] == requested
    require_order = [f['target_index'] for f in frames] == list(range(requested))
    schedule_fields=('recording_id','epoch_id','segment_id','group_id','target_index','target_step','simulation_time_ns')
    matching=len(scheduled)==len(frames) and all(all(s[k]==f[k] for k in schedule_fields) for s,f in zip(scheduled,frames))
    complete = complete and require_order and matching and session['counts']['dropped'] == 0
    complete=complete and session['counts']['validated']==len(frames) and all(n==len(frames) for n in session['counts']['received_by_sensor'].values())
    checks['schedule_completeness'].update(passed=complete,checked_items=len(frames),failed_items=0 if complete else 1,
                    reason='Independent target indexes, pre-reserved schedules, request count and actual commits compared')
    if not complete and job['capture']['policy']=='strict_complete':
        errors.append({'code':'schedule_completeness','message':'Requested, scheduled and independently verified targets do not all agree',
                       'group':None,'sensor_id':None,'topic':None,'evidence_paths':['schedule.jsonl','session.json']})
    motion={'declared_mode':job.get('motion_mode'),'max_root_translation_from_first_m':motion_max_translation,
            'max_root_rotation_from_first_rad':motion_max_rotation,
            'static_ok':bool(frames) and motion_max_translation<=1e-5 and motion_max_rotation<=1e-5,
            'moving_ok':bool(frames) and (motion_max_translation>.01 or motion_max_rotation>.01),
            'scope':'actual independently decoded physical root readback across all committed groups'}
    if motion['declared_mode']=='static' and not motion['static_ok']:
        errors.append({'code':'motion_mode','message':'Declared static case moved in actual decoded root state','evidence_paths':['job_spec.json']})
    if motion['declared_mode']=='moving' and not motion['moving_ok']:
        errors.append({'code':'motion_mode','message':'Declared moving case has no actual meaningful root motion','evidence_paths':['job_spec.json']})
    sync = bool(frames) and not any(e['code']!='schedule_completeness' for e in errors)
    geometry={'executed':False,'passed':None,'reprojection_p95_px':None,'point_plane_p95_m':None,'evidence_paths':[]}
    if geometry_spec:
        pixels=[r['error_px'] for g in geometry_rows for r in g['reprojection']]
        planes=[r['point_plane_p95_m'] for g in geometry_rows for r in g['planes'] if r['point_plane_p95_m'] is not None]
        shifted=[r['error_px'] for g in geometry_rows for r in g.get('one_physical_step_shift',{}).get('reprojection',[])]
        def p95(values):return float(np.quantile(values,.95,method='higher')) if values else None
        px,metre,wrong=p95(pixels),p95(planes),p95(shifted)
        passed=len(pixels)>=20 and len(planes)>=20 and px<=1. and metre<=.005 and wrong is not None and wrong>1.
        geometry=dict(executed=True,passed=passed,reprojection_p95_px=px,point_plane_p95_m=metre,
                      feature_extractor_source_sha256=file_hash(Path(__file__).parent/'geometry_diagnostics.py'),
                      evidence_paths=['diagnostic_geometry.json','diagnostic_states.jsonl','geometry_diagnostics.json'],
                      feature_samples=len(pixels),plane_group_samples=len(planes),one_physical_step_shift_reprojection_p95_px=wrong,
                      one_physical_step_shift_detected=wrong is not None and wrong>1.)
        if not (directory/'READY').exists():
            save_json(directory/'geometry_diagnostics.json',{'schema_version':1,'geometry_diagnostics':geometry,'groups':geometry_rows})
    report = {'schema_version':1,'validator_run_id':'validator_'+uuid.uuid4().hex,'recording_id':session['recording_id'],
        'scope':'recording','epoch_id':None,'segment_id':None,'backend':session['backend'],'policy':session['policy'],
        'environment_path':'environment.json','validator_source_sha256':file_hash(Path(__file__)),
        'started_utc':started,'finished_utc':utc(),'input_files':input_files,
        'counts':{'groups_seen':commits_seen,'commits_seen':commits_seen,'groups_verified':len(frames),'messages_seen':message_count,
                  'incomplete_groups':max(0,commits_seen-len(frames)),'gap_groups':session['counts']['gap_groups']},
        'checks':checks,'max_abs_source_time_error_ns':str(maximum['source_ns']) if frames else None,
        'max_translation_error_m':maximum['translation_m'] if frames else None,'max_rotation_error_rad':maximum['rotation_rad'] if frames else None,
        'geometry_diagnostics':geometry,'motion_evidence':motion,
        'sync_ok':sync,'completeness_ok':complete and session['policy']=='strict_complete','file_integrity_ok':sync,
        'quality_ok':None,'performance_ok':None,'errors':errors}
    for filename in (session_path.name,'job_spec.json','capabilities.json','source_manifest.json','asset_manifest.json','render_profile.json','schedule.jsonl','sensor_registry.json','diagnostic_geometry.json','diagnostic_states.jsonl'):
        path=directory/filename
        if path.exists():
            report['input_files'].append({'path':filename,'format':'jsonl' if path.suffix=='.jsonl' else 'json',
                    'size_bytes':path.stat().st_size,'sha256':file_hash(path),'produced_by':'P7'})
    if not (directory/'READY').exists():
        save_json(directory/'validation.json', report)
    return report, segment_reports
