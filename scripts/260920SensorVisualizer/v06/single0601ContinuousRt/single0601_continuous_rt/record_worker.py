"""Independent CPU encoding, exact CDR commit, MCAP write and distinct ACKs."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import io
import json
import mmap
import importlib.metadata
from pathlib import Path
import sys
import subprocess
import time
import traceback
import numpy as np
from .common import cjson, ContractError, save_json
from .diagnostics import EvidenceLog, statistics,process_resources


def send(value):
    sys.stdout.buffer.write(cjson(value)+b'\n')
    sys.stdout.buffer.flush()


def run(hello_path):
    import rosbag2_py
    from PIL import Image
    from rclpy.serialization import serialize_message
    from std_msgs.msg import String
    from .messages import encode_group, topics, type_name
    hello = json.loads(Path(hello_path).read_text())
    job, registry = hello['job'], hello['registry']
    session = Path(hello['session'])
    recording = registry['recording_id']
    logs = EvidenceLog(session, recording)
    writer, segment = None, None
    groups = 0
    mappings = {}
    executor = ThreadPoolExecutor(max_workers=job['pipeline']['encoder_workers']) if registry['cameras'] else None
    latencies = {k:[] for k in ('png_encode','cdr_serialize','write','group_pipeline')}
    def ack(kind, ticket, **extra):
        return dict(schema_version=1, type=kind, recording_id=recording,
                    epoch_id=ticket['epoch_id'], segment_id=ticket['segment_id'], group_id=ticket['group_id'],
                    monotonic_ns=str(time.monotonic_ns()), **extra)
    def close_segment():
        nonlocal writer
        if writer is not None:
            writer.close()
            writer = None
            directory = session/'epochs'/segment['epoch_id']/'segments'/segment['segment_id']
            files = [p.relative_to(session).as_posix() for p in directory.rglob('*') if p.is_file()]
            send({'schema_version':1, 'type':'segment_closed', 'recording_id':recording,
                  'epoch_id':segment['epoch_id'], 'segment_id':segment['segment_id'],
                  'closed_monotonic_ns':str(time.monotonic_ns()), 'files':files, 'success':True, 'error':None})
    def png(array):
        start = time.monotonic_ns()
        out = io.BytesIO()
        Image.fromarray(array, 'RGB').save(out, format='PNG', compress_level=job['pipeline']['png_compress_level'])
        return out.getvalue(), (time.monotonic_ns()-start)/1e6
    def package_version(name):
        try:
            return importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            native={'rosbag2-py':'ros-jazzy-rosbag2-py','rosbag2-storage-mcap':'ros-jazzy-rosbag2-storage-mcap'}[name]
            result=subprocess.run(['dpkg-query','-W','-f=${Version}',native],capture_output=True,text=True,timeout=5)
            return result.stdout.strip() if result.returncode==0 else None
    send({'schema_version':1, 'type':'ready', 'recording_id':recording, 'monotonic_ns':str(time.monotonic_ns()),
          'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
          'versions':{'rosbag2':package_version('rosbag2-py'),'mcap_storage':package_version('rosbag2-storage-mcap')}})
    current_ticket = None
    try:
        for raw in sys.stdin.buffer:
            request = json.loads(raw)
            if request['type'] == 'close':
                close_segment()
                logs.close()
                if executor:
                    executor.shutdown(wait=True)
                for mapped, f in mappings.values():
                    mapped.close()
                    f.close()
                save_json(session/'worker_report.json', {'schema_version':1, 'groups_written':groups,
                          'latencies':{k:statistics(v,k) for k,v in latencies.items()},'resources_after_close':process_resources()})
                send({'schema_version':1, 'type':'worker_closed', 'recording_id':recording, 'groups_written':groups})
                return
            if request['type'] != 'group':
                raise ContractError('worker_protocol', 'Unknown worker request')
            current_ticket = ticket = request['ticket']
            fault=job.get('diagnostics',{}).get('worker_fault',{})
            if fault.get('kind')=='slow_worker':
                delay=float(fault.get('delay_s',0))
                if not 0<=delay<=10:
                    raise ContractError('fault_config','Diagnostic delay must be bounded to ten seconds')
                time.sleep(delay)
            if ticket['group_id'] != groups or ticket['recording_id'] != recording:
                raise ContractError('worker_group_order', 'Groups must be submitted in recorded output order')
            desc = request['buffer']
            identity = [recording, ticket['epoch_id'], ticket['group_id']]
            if desc['identity'] != identity or (desc['slot'], desc['generation']) != (ticket['slot'], ticket['generation']):
                raise ContractError('worker_slot_identity', 'Mmap descriptor identity and generation differ from ticket')
            path = Path(desc['path']).resolve()
            if path.parent != (session/'.ipc').resolve() or path.name != 'slot_%03d.mmap'%desc['slot']:
                raise ContractError('worker_slot_path', 'Mmap must belong to this recording')
            if str(path) not in mappings:
                f = path.open('rb')
                if path.stat().st_size != desc['slot_bytes']:
                    raise ContractError('worker_slot_size', 'Mmap size mismatch')
                mappings[str(path)] = (mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ), f)
            mapped = mappings[str(path)][0]
            arrays = {}
            for sid, item in desc['arrays'].items():
                if item['offset'] < 0 or item['offset']+item['nbytes'] > len(mapped):
                    raise ContractError('worker_payload_bounds', 'Array lies outside mmap slot')
                array = np.ndarray(item['shape'], dtype=np.dtype(item['dtype']), buffer=mapped, offset=item['offset'])
                if array.nbytes != item['nbytes']:
                    raise ContractError('worker_payload_size', 'Descriptor shape/byte-size mismatch')
                arrays[sid] = array
            if set(arrays) != set(ticket['expected_sensor_ids']):
                raise ContractError('worker_sensor_set', 'Mmap contains the wrong selection')
            pngs = {}
            if executor:
                futures = {c['id']:executor.submit(png, arrays[c['sensor_id']]) for c in registry['cameras']}
                for cid, future in futures.items():
                    value, elapsed = future.result()
                    pngs[cid] = value
                    latencies['png_encode'].append(elapsed)
                del futures, future
            start = time.monotonic_ns()
            frame, commit, messages = encode_group(request, registry, arrays, pngs, hello['backend'], job['capture']['policy'])
            latencies['cdr_serialize'].append((time.monotonic_ns()-start)/1e6)
            if sum(len(x[2]) for x in messages) > job['pipeline']['slot_bytes']:
                raise ContractError('encoded_budget', 'Encoded messages exceed reserved complete-group credit')
            del arrays, array, pngs
            send(ack('release', ticket, slot=ticket['slot'], generation=ticket['generation']))
            logs.event('groups_worker.jsonl', 'encoded', {'group':{k:ticket[k] for k in ('recording_id','epoch_id','segment_id','group_id','target_index','target_step','simulation_time_ns')},
                       'frame_index':frame, 'commit':commit}, ticket['epoch_id'], ticket['segment_id'])
            if segment is None or segment['segment_id'] != ticket['segment_id'] or segment['epoch_id'] != ticket['epoch_id']:
                close_segment()
                segment = ticket
                bag = session/'epochs'/ticket['epoch_id']/'segments'/ticket['segment_id']/'bag_unified'
                bag.parent.mkdir(parents=True, exist_ok=True)
                writer = rosbag2_py.SequentialWriter()
                writer.open(rosbag2_py.StorageOptions(uri=str(bag), storage_id='mcap', max_cache_size=0), rosbag2_py.ConverterOptions('', ''))
                for i, (topic, cls) in enumerate(topics(registry).items(), 1):
                    writer.create_topic(rosbag2_py.TopicMetadata(id=i, name=topic, type=type_name(cls), serialization_format='cdr'))
                metadata = dict(hello['run_metadata'], epoch_id=ticket['epoch_id'], segment_id=ticket['segment_id'])
                writer.write('/sensor_visualizer/run_metadata', serialize_message(String(data=cjson(metadata).decode())), int(ticket['simulation_time_ns']))
                writer.write('/sensor_visualizer/camera_metadata', serialize_message(String(data=cjson(registry).decode())), int(ticket['simulation_time_ns']))
            start = time.monotonic_ns()
            for ordinal,(topic, typ, raw) in enumerate(messages):
                if fault.get('kind')=='disk_full' and ticket['group_id']==fault.get('group_id',1) and ordinal==3:
                    import errno
                    raise OSError(errno.ENOSPC,'Explicit diagnostic disk-full injection before group_commit')
                writer.write(topic, raw, int(ticket['simulation_time_ns']))
            latencies['write'].append((time.monotonic_ns()-start)/1e6)
            groups += 1
            result = ack('written', ticket, slot=ticket['slot'],generation=ticket['generation'],group_hash=commit['group_hash'], message_count=commit['message_count'])
            send(result)
            latencies['group_pipeline'].append((time.monotonic_ns()-int(min(e['received_monotonic_ns'] for e in request['evidence'].values())))/1e6)
            current_ticket = None
    except Exception as exc:
        send({'schema_version':1, 'type':'failed', 'recording_id':recording,
              'error':{'code':getattr(exc,'code','worker_error'), 'message':str(exc), 'evidence_paths':['logs/worker_stderr.log']},
              'group_id': current_ticket['group_id'] if current_ticket else None})
        traceback.print_exc(file=sys.stderr)
        logs.close()
        if writer:
            writer.close()
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--hello', required=True)
    run(parser.parse_args().hello)
