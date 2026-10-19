"""Bounded parallel codec pipeline with one ROS 2 MCAP writer."""
from concurrent.futures import ThreadPoolExecutor
from collections import Counter, deque
import argparse
import hashlib
import io
import json
import mmap
import os
from pathlib import Path
import queue
import select
import socket
import sys
import threading
import time
import traceback

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = 'sensor_visualizer_v05'
from .buffers import array_view, receive_message, send_message
from .contracts import write_json
from .diagnostics import RunDiagnostics


def run(socket_path):
    import rosbag2_py
    from PIL import Image
    from rclpy.serialization import serialize_message, deserialize_message
    from std_msgs.msg import String
    from .messages import topics, type_name, build_messages
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(socket_path)
    hello = receive_message(sock)
    if hello.get('protocol') != 3: raise ValueError('Unsupported capture IPC protocol')
    job, registry = hello['job'], hello['registry']
    session = Path(hello['session'])
    diag=RunDiagnostics(job['output_directory'],job['diagnostics'],role='writer',run_id=hello['run_id'],directory=hello['diagnostics_directory'])
    diag.context(capture_id=hello['job_id'])
    def correlation(bundle):
        return {k:bundle.get(k) for k in ('capture_id','group_id','request_id','attempt_id','stage_generation','simulation_time_ns')}
    config = job['pipeline']
    slot_dir = Path(hello['slot_directory']).resolve()
    streams, mappings = [], []
    for i in range(config['slots']):
        stream = (slot_dir/f'slot_{i}.bin').open('rb')
        if os.fstat(stream.fileno()).st_size != config['slot_bytes']: raise ValueError('Wrong slot size')
        streams.append(stream); mappings.append(mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ))
    send_lock = threading.Lock()
    def send(message):
        with send_lock: send_message(sock, message)
    errors, stopping = queue.Queue(), threading.Event()
    incoming = queue.Queue(maxsize=config['slots'])
    encoded = queue.Queue(maxsize=2)
    counts = Counter(); hashes = {}; groups = 0
    stats = {'encode_s': deque(maxlen=4096), 'write_s': deque(maxlen=4096), 'groups': 0,
             'encode_total_s':0.,'write_total_s':0.,'preview_errors':[]}
    all_topics = topics(registry)
    writer = rosbag2_py.SequentialWriter()
    writer.open(rosbag2_py.StorageOptions(uri=str(session/'bag_unified'), storage_id='mcap', max_cache_size=0), rosbag2_py.ConverterOptions('', ''))
    for i, (name, cls) in enumerate(all_topics.items(), 1):
        writer.create_topic(rosbag2_py.TopicMetadata(id=i, name=name, type=type_name(cls), serialization_format='cdr'))
    preview_node = None; publishers = {}
    if job['preview']['enabled']:
        import rclpy
        from rclpy.qos import qos_profile_sensor_data
        rclpy.init(domain_id=job['preview']['ros_domain_id'])
        preview_node = rclpy.create_node('sensor_visualizer_v05_'+hello['job_id'][:8])
        for name, cls in all_topics.items():
            if name.startswith('/sensor_visualizer/'): continue
            publishers[name] = preview_node.create_publisher(cls, name, 20 if name in ('/tf','/clock') else qos_profile_sensor_data)
    log = (session/'capture_index.jsonl').open('a', encoding='utf-8', buffering=1)
    executor = ThreadPoolExecutor(max_workers=config['encoder_workers'], thread_name_prefix='sv05-png')
    def encode_image(array,cid,queued_ns,context):
        diag.event('png_started',sensor_id=cid,queue_wait_ns=time.monotonic_ns()-queued_ns,**context)
        with diag.span('png_encode',sensor_id=cid,**context):
            output = io.BytesIO()
            Image.fromarray(array[:, :, :3]).save(output, format='PNG', compress_level=config['png_compress_level'])
        return output.getvalue()
    def fail():
        diag.warning('writer_failed',traceback.format_exc())
        errors.put(traceback.format_exc()); stopping.set()
    def put(q, item):
        started=time.monotonic_ns()
        while not stopping.is_set():
            try:
                q.put(item, timeout=0.2)
                diag.event('worker_queue_put',queue='incoming' if q is incoming else 'encoded',depth=q.qsize(),wait_ns=time.monotonic_ns()-started)
                return
            except queue.Full: pass
        raise RuntimeError('Record pipeline stopped')
    def get(q):
        while not stopping.is_set():
            try: return q.get(timeout=0.2)
            except queue.Empty: pass
        raise RuntimeError('Record pipeline stopped')
    def encoder():
        expected = 0
        try:
            while True:
                bundle = get(incoming)
                if bundle is None:
                    put(encoded, None); return
                if bundle['group_id'] != expected: raise ValueError('Nonsequential input group')
                expected += 1
                begin = time.perf_counter()
                desc = bundle['buffer']; slot = desc['slot']
                if type(slot) is not int or not 0 <= slot < len(mappings): raise ValueError('Invalid slot')
                arrays = {name:array_view(mappings[slot], info) for name, info in desc['arrays'].items()}
                context=correlation(bundle)
                diag.event('encode_group_started',**context)
                futures = {c['id']:executor.submit(encode_image, arrays['camera/'+c['id']],c['id'],time.monotonic_ns(),context) for c in registry['cameras']}
                pngs = {cid:future.result() for cid,future in futures.items()}
                clouds = {s['id']:arrays['lidar/'+s['id']] for s in registry['lidars']}
                with diag.span('message_build_and_cdr',**context):
                    messages = build_messages(bundle, registry, clouds, pngs,diag)
                if sum(len(data) for _,data in messages) > config['slot_bytes']*2:
                    raise BufferError('Encoded group exceeds bounded queue budget')
                # No background view survives this acknowledgement.
                del arrays, clouds, futures, pngs
                send({'event':'release', 'slot':slot, 'group_id':bundle['group_id'], 'generation':desc['generation'],'capture_id':bundle['capture_id']})
                diag.event('release_ack_sent',slot_id=slot,slot_generation=desc['generation'],**context)
                elapsed=time.perf_counter()-begin
                stats['encode_s'].append(elapsed); stats['encode_total_s']+=elapsed
                put(encoded, (bundle, messages))
        except Exception: fail()
    def sink():
        nonlocal groups, preview_node
        last_preview = -float('inf')
        try:
            while True:
                item = get(encoded)
                if item is None: return
                bundle, messages = item
                stamp = bundle['simulation_time_ns']; group = bundle['group_id']; context=correlation(bundle)
                if group % config['segment_groups'] == 0:
                    if group:
                        with diag.span('mcap_split',**context): writer.split_bagfile()
                        log.write(json.dumps({'event':'segment_closed','through_group':group-1})+'\n')
                    metadata = {'schema_version':2, 'job':job, 'registry':registry, 'render':hello['render'],
                                'clock':'Isaac SimulationManager; frozen during sample; integer nanoseconds',
                                'images':'raw distorted OpenCV fisheye RGB PNG', 'optical_axes':'X right Y down Z forward'}
                    writer.write('/sensor_visualizer/run_metadata', serialize_message(String(data=json.dumps(metadata))), stamp)
                    writer.write('/sensor_visualizer/camera_metadata', serialize_message(String(data=json.dumps({'schema_version':2,
                        'calibrations':{c['id']:c['calibration'] for c in registry['cameras']}}))), stamp)
                begin = time.perf_counter()
                for topic, data in messages:
                    with diag.span('mcap_write_api',topic=topic,bytes=len(data),**context):
                        writer.write(topic, data, stamp)
                    counts[topic] += 1
                    with diag.span('digest',topic=topic,**context):
                        hashes.setdefault(topic, hashlib.sha256()).update(int(stamp).to_bytes(8,'little')+data)
                groups += 1; stats['groups'] = groups
                elapsed=time.perf_counter()-begin
                stats['write_s'].append(elapsed); stats['write_total_s']+=elapsed
                log.write(json.dumps({'event':'group_written', 'group_id':group, 'simulation_time_ns':stamp,
                                      'point_counts':{k:v['points'] for k,v in bundle['lidars'].items()}})+'\n')
                diag.event('group_written',critical=True,**context)
                send({'event':'written', 'group_id':group, 'groups':groups})
                now = time.monotonic()
                if preview_node and now-last_preview >= 1/job['preview']['wall_hz']:
                    try:
                        for topic, data in messages:
                            if topic in publishers:
                                with diag.span('ros_deserialize',topic=topic,**context): message=deserialize_message(data,all_topics[topic])
                                with diag.span('ros_publish',topic=topic,**context): publishers[topic].publish(message)
                    except Exception as exc:
                        diag.warning('ros_preview_failed',str(exc),**context)
                        stats['preview_errors'].append(str(exc))
                        preview_node.destroy_node(); preview_node=None
                        print('ROS preview disabled after publish failure: '+str(exc),flush=True)
                    last_preview = now
        except Exception: fail()
    threads = [threading.Thread(target=encoder, name='sv05-encoder'), threading.Thread(target=sink, name='sv05-writer')]
    for thread in threads: thread.start()
    send({'event':'ready','pid':os.getpid()})
    try:
        while not stopping.is_set():
            if not select.select([sock], [], [], 1)[0]: continue
            command = receive_message(sock)
            if command['event'] == 'finish':
                put(incoming, None); break
            if command['event'] != 'group': raise ValueError('Unsupported record command')
            if command['bundle'].get('capture_id')!=hello['job_id']: raise ValueError('Wrong capture identity')
            diag.event('group_received',**correlation(command['bundle']))
            put(incoming, command['bundle'])
        for thread in threads:
            thread.join(timeout=config['timeout_s'])
            if thread.is_alive(): raise TimeoutError('Record drain timeout')
        if not errors.empty(): raise RuntimeError(errors.get())
        with diag.span('mcap_close'): writer.close()
        writer = None
        log.write(json.dumps({'event':'bag_closed','through_group':groups-1})+'\n')
        with diag.span('index_fsync'):
            log.flush(); os.fsync(log.fileno())
        result = {'state':'finished','groups':groups,'counts':dict(counts),
                  'digests':{k:v.hexdigest() for k,v in hashes.items()},
                  'timings':{k:list(v) if isinstance(v,deque) else v for k,v in stats.items()}}
        write_json(session/'writer_report.json', result)
        send({'event':'finished','groups':groups})
    except Exception:
        stopping.set()
        error = traceback.format_exc()
        write_json(session/'writer_report.json', {'state':'failed', 'groups':groups, 'error':error})
        try: send({'event':'error','error':error})
        except Exception: pass
        raise
    finally:
        stopping.set()
        for thread in threads: thread.join(timeout=5)
        executor.shutdown(wait=True, cancel_futures=True)
        if writer is not None: writer.close()
        log.close()
        for mapping in mappings: mapping.close()
        for stream in streams: stream.close()
        if preview_node:
            preview_node.destroy_node()
            rclpy.shutdown()
        sock.close(); diag.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--socket', required=True)
    run(parser.parse_args().socket)
