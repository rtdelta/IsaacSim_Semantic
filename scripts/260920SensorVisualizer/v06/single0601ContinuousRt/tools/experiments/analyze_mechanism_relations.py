"""Native GMO vs extractor, emitter identities and analytic room ranges.

Derived calculations never alter the original points, clocks or snapshots.
The ray model is restricted to zero emitter offsets/corrections and identity
model transform, independently qualified by the frozen reference.
"""
import argparse,hashlib,json,math,sys
from pathlib import Path
import numpy as np
PROJECT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(PROJECT),str(PROJECT.parent)]
from tools.experiments.storage import rows,save,digest
from tools.experiments.decode_gmo import decode
from tools.experiments.compare_paired_outputs import payload,quantiles


def ray_ranges(directions,matrix,walls):
    matrix=np.asarray(matrix);world=directions@matrix[:3,:3];values=[]
    for wall in walls:
        axis=wall['axis'];den=world[:,axis];valid=np.abs(den)>1e-12
        distance=np.full(len(world),np.inf)
        distance[valid]=(wall['coordinate_m']-matrix[3,axis])/den[valid]
        distance[distance<=0]=np.inf;values.append(distance)
    return np.min(values,axis=0)


def analyze_side(directory):
    directory=Path(directory);registry=json.loads((directory/'sensor_registry.json').read_text())
    render=json.loads((directory/'render_profile.json').read_text());walls=render.get('room_geometry');groups=[]
    states={r['physical_step']:r for r in rows(directory/'actual_states.jsonl')}
    if not states:
        for row in rows(directory/'phase_states.jsonl'):
            if row.get('actual_state') is not None:states[row['physical_step']]=row['actual_state']
    for row in rows(directory/'native_events.jsonl'):
        meta=row.get('native_event',{});packet_path=meta.get('packet_path')
        if row['kind']!='lidar' or not packet_path:continue
        packet=(directory/packet_path).read_bytes()
        if hashlib.sha256(packet).hexdigest()!=meta['packet_sha256']:raise ValueError('Original GMO SHA differs')
        header,arrays,auxiliary,xyz=decode(packet)
        extracted=payload(directory,row)
        # The extraction mapping is established through VALID flags, not row assumptions across C/F.
        valid=(arrays['flags']&64)!=0;decoded=xyz[valid]
        same=decoded.shape==extracted.shape and np.array_equal(decoded.astype('<f4'),extracted)
        group={'source_target_step':row['physical_step'],'target_index':row.get('target_index'),'receipt_seq':row['receipt_seq'],
            'original_gmo_sha256':meta['packet_sha256'],'serialized_array_count':len(xyz),'valid_count':int(valid.sum()),
            'extractor_points':len(extracted),'decoded_valid_cartesian_equal_extractor':same,
            'header':header,'auxiliary':auxiliary,'auxiliary_arrays_present':list(arrays)}
        if walls and all(k in arrays for k in ('emitter_id','channel_id','tick_id','echo_id')):
            parameters=registry['lidars'][0]['parameters']
            def setting(name):
                value=parameters[name]
                return value['value'] if isinstance(value,dict) and 'value' in value else value
            offsets=['horOffsetM','vertOffsetM','distanceCorrectionM','fireTimeNs']
            for name in offsets:
                if np.any(np.asarray(setting('omni:sensor:Core:emitterState:s001:'+name))!=0):raise ValueError('Ray model requires declared zero '+name)
            if header['coordinates_type_code']!=0 or header['frame_of_reference_code']!=0 or not np.array_equal(np.array(header['model_to_app_transform_raw']).reshape(4,4),np.eye(4)):
                raise ValueError('Ray mechanism model not qualified for these GMO coordinates')
            az=np.deg2rad(np.asarray(setting('omni:sensor:Core:emitterState:s001:azimuthDeg'),dtype=float))
            el=np.deg2rad(np.asarray(setting('omni:sensor:Core:emitterState:s001:elevationDeg'),dtype=float))
            # This asset's firing angles use clockwise azimuth. Qualification is
            # still conditional on F's absolute room geometry/ranges, not assumed.
            nominal=np.column_stack([np.cos(el)*np.cos(az),-np.cos(el)*np.sin(az),np.sin(el)])[arrays['emitter_id'][valid]]
            observed=decoded.astype(float);ranges=np.linalg.norm(observed,axis=1);matrix=np.array(row['historical_to_world'])
            predicted=ray_ranges(nominal,matrix,walls)
            direction_delta=np.arctan2(observed[:,1],observed[:,0])-np.arctan2(nominal[:,1],nominal[:,0])
            direction_delta=(direction_delta+np.pi)%(2*np.pi)-np.pi
            horizontal=np.abs(nominal[:,2])<.9
            candidate={}
            previous=states.get(row['physical_step']-1)
            if previous:
                old=np.array(previous['sensor_world_matrices_usd'][row['sensor_id']])
                candidate['previous_actual_step']=quantiles(np.abs(ray_ranges(nominal,old,walls)-ranges))
                hybrid=matrix.copy();hybrid[:3,:3]=old[:3,:3]
                candidate['previous_rotation_current_position_SYNTHETIC']=quantiles(np.abs(ray_ranges(nominal,hybrid,walls)-ranges))
                from single0601_continuous_rt.geometry import matrix_from_pose,rigid_pose
                from sensor_visualizer_v06.trajectory import slerp
                half=matrix_from_pose(matrix[3,:3],slerp(rigid_pose(old)[1],rigid_pose(matrix)[1],.5))
                candidate['half_rotation_current_position_SYNTHETIC']=quantiles(np.abs(ray_ranges(nominal,half,walls)-ranges))
            # Native endpoints are separately labelled; they do not become corrected output.
            for point in ('frame_start','frame_end'):
                m=meta.get(point,{}).get('diagnostic_matrix_candidates',{}).get('xyzw')
                if m is not None:candidate[point+'_xyzw_diagnostic']=quantiles(np.abs(ray_ranges(nominal,m,walls)-ranges))
            ids=np.column_stack([arrays[k][valid] for k in ('emitter_id','channel_id','tick_id','echo_id')])
            group.update(emitter_identity_unique_count=len(np.unique(ids,axis=0)),
                output_direction_minus_authored_rad=quantiles(direction_delta[horizontal]),
                nominal_ray_actual_pose_range_residual_m=quantiles(np.abs(predicted-ranges)),
                candidate_pose_range_residual_m=candidate,
                point_time_offset_ns=quantiles(arrays['time_offset_ns'][valid]),
                ray_model_scope='analytic 6-plane zero-offset emitter rays; coordinate convention must be confirmed by paired F')
        groups.append(group)
    return {'schema_version':1,'analyzer_sha256':digest(Path(__file__)),'groups':groups,
        'sampled_complete_gmo_count':len(groups),'all_decoded_valid_xyz_equal_extractor':all(g['decoded_valid_cartesian_equal_extractor'] for g in groups) if groups else None}


def analyze(parent):
    parent=Path(parent);result={'schema_version':1,'scope':'read-only diagnostic calculations, no pose fit corrections'}
    for side in ('continuous','frozen_v06','frozen_room'):
        directory=parent/side
        if directory.exists():result[side]=analyze_side(directory)
    save(parent/'analysis/mechanism_relations.json',result);return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory');parser.add_argument('--legacy-report');args=parser.parse_args()
    if args.legacy_report:result=analyze_side(args.directory);save(args.legacy_report,result)
    else:result=analyze(args.directory)
    print(json.dumps(result))
