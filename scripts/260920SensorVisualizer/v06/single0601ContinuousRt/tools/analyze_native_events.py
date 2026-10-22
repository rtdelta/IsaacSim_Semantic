"""Offline analysis of owned native evidence; no SDK, inferred clock or pose repair."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from single0601_continuous_rt.sensor_backend import pose_error
from single0601_continuous_rt.common import save_json
from single0601_continuous_rt.native_header import decode_header


def analyze(directory):
    directory=Path(directory).resolve()
    rows=[json.loads(line)['data'] for line in (directory/'native_events.jsonl').read_text().splitlines()]
    result={'schema_version':1,'scope':'Offline frozen native trace; no formal acceptance promotion',
            'input_sha256':hashlib.sha256((directory/'native_events.jsonl').read_bytes()).hexdigest(),'sensors':[]}
    for sid in sorted({r['sensor_id'] for r in rows}):
        group=[r for r in rows if r['sensor_id']==sid]
        candidates={};deltas={};frame_ids=[];offsets=[];packet_hashes=[];header_matches=[]
        for r in group:
            e=r.get('native_event')
            if not e:continue
            frame_ids.append(e['native_frame_id']);offsets.append(e['point_time_offsets'])
            for name in ('timestamp_ns','frame_start','frame_end'):
                stamp=e[name] if name=='timestamp_ns' else e[name]['timestamp_ns']
                deltas.setdefault(name,[]).append(int(stamp)-int(r['source_time_ns']))
            for point in ('frame_start','frame_end'):
                for order,matrix in e[point]['diagnostic_matrix_candidates'].items():
                    tr,rot=pose_error(r['historical_to_world'],matrix)
                    candidates.setdefault(point+'/'+order,[]).append((tr,rot))
            relative=e.get('packet_path') or e.get('packet_prefix_path')
            path=(directory/relative).resolve()
            if directory not in path.parents:raise ValueError('Packet path escaped frozen trace')
            wanted=e['packet_sha256'] if e.get('packet_path') else e['packet_prefix_sha256']
            packet=path.read_bytes()
            packet_hashes.append(hashlib.sha256(packet).hexdigest()==wanted)
            header=decode_header(packet)
            matched=all(header[k]==e[k] for k in ('structure_version','native_frame_id','timestamp_ns','num_elements','model_to_app_transform_raw'))
            matched=matched and all(header[f][k]==e[f][k] for f in ('frame_start','frame_end') for k in ('timestamp_ns','orientation_raw','position_m'))
            header_matches.append(matched)
        result['sensors'].append({'sensor_id':sid,'events':len(group),
            'extractor_pose_bad':sum(r['translation_error_m']>.001 or r['rotation_error_rad']>.0001 for r in group),
            'extractor_translation_max_m':max(r['translation_error_m'] for r in group),
            'extractor_rotation_max_rad':max(r['rotation_error_rad'] for r in group),
            'native_gmo_events':len(frame_ids),'native_frame_ids_unique':len(set(frame_ids)),
            'retained_packet_or_prefix_hashes_all_match':all(packet_hashes) if packet_hashes else None,
            'independent_packed_header_matches_metadata':all(header_matches) if header_matches else None,
            'raw_native_timestamp_delta_to_physics_ns':{key:{'min':str(min(values)),'max':str(max(values)),'unique':sorted({str(v) for v in values})} for key,values in deltas.items()},
            'point_offset_ranges':{'min_ns':min((int(o['min_ns']) for o in offsets if o['count']),default=None),
                                   'max_ns':max((int(o['max_ns']) for o in offsets if o['count']),default=None)},
            'raw_gmo_pose_candidates':{key:{'translation_max_m':max(v[0] for v in values),'rotation_max_rad':max(v[1] for v in values),
                        'bad':sum(tr>.001 or rot>.0001 for tr,rot in values)} for key,values in candidates.items()},
            'frame_of_reference':sorted({r['native_event']['frame_of_reference'] for r in group if 'native_event' in r}),
            'motion_compensation_state':sorted({r['native_event']['motion_compensation_state'] for r in group if 'native_event' in r})})
    states=[json.loads(line)['data'] for line in (directory/'phase_states.jsonl').read_text().splitlines()]
    checks={}
    for state in states:
        for sid,matrix in state['fabric_current_world'].items():
            tr,rot=pose_error(state['usd_world'][sid],matrix)
            checks.setdefault(state['phase'],[]).append((tr,rot))
    result['fabric_vs_usd']={key:{'samples':len(values),'translation_max_m':max(v[0] for v in values),
        'rotation_max_rad':max(v[1] for v in values),'bad':sum(tr>.001 or rot>.0001 for tr,rot in values)} for key,values in checks.items()}
    result['fabric_read_errors']=sorted({s['fabric_error'] for s in states if s['fabric_error']})
    result['conclusion']='Actual ray geometry and native timing semantics require independent verification; no correction inferred from matching a matrix candidate'
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory');p.add_argument('--report',required=True)
    args=p.parse_args();report=analyze(args.directory);save_json(args.report,report)
    print(json.dumps(report,ensure_ascii=False,indent=2))
