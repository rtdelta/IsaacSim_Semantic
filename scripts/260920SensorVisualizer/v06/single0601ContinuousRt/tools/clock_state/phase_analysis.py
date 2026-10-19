"""CPU-stage observations, explicitly not GPU execution-order evidence."""
import collections,json,sys
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(PROJECT))
from tools.experiments.storage import rows,save
from tools.experiments.compare_paired_outputs import quantiles
from single0601_continuous_rt.sensor_backend import pose_error


def analyze(parent):
    parent=Path(parent);directory=parent/'continuous';trace=rows(directory/'phase_clock_trace.jsonl');by_phase=collections.defaultdict(list)
    for row in trace:by_phase[row['phase']].append(row)
    report={'schema_version':1,'evidence_layer':'A: CPU callback sequence and current USD/Fabric readback only',
        'fabric_history_api':'unavailable: no installed public read interface verified','GPU_ray_pose':'unavailable',
        'stage_probe_enabled':bool(trace),'stages':{},'global_sequence_strictly_increasing':all(b['stage_seq']>a['stage_seq'] for a,b in zip(trace,trace[1:])) if trace else None,
        'external_time_comparison':'unavailable until native attribute units/semantics independently verified'}
    contract_path=PROJECT/'config/clock_state/installed_timing_contract.json'
    contract=json.loads(contract_path.read_text()) if contract_path.exists() else None
    if contract:
        report['installed_timing_contract']=contract
        report['external_time_comparison']='seconds, qualified by installed simulation-manager test and declarations; raw records kept unchanged'
    for phase,values in by_phase.items():
        pe=[];re=[];external=[];errors=[];timeline=[];external_delta=[]
        for row in values:
            usd=row['usd_world'].get('lidar/MyAiry_front');fabric=row['fabric_current_world'].get('lidar/MyAiry_front')
            if usd and fabric:
                p,r=pose_error(usd,fabric);pe.append(p);re.append(r)
            if row.get('fabric_error'):errors.append(row['fabric_error'])
            if row.get('external_simulation_time_typed'):
                external.append(row['external_simulation_time_typed'])
                v=row['external_simulation_time_typed']['value']
                if contract and isinstance(v,(int,float)):external_delta.append(round(v*1e9)-int(row['simulation_time_ns']))
            timeline.append(row['timeline_time_s']-int(row['simulation_time_ns'])/1e9)
        report['stages'][phase]={'count':len(values),'USD_Fabric_translation_m':quantiles(pe),'USD_Fabric_rotation_rad':quantiles(re),
            'external_minus_physics_ns':quantiles(external_delta),
            'timeline_minus_physics_s_descriptive_only':quantiles(timeline),'fabric_errors':dict(collections.Counter(errors)),
            'external_time_first':external[0] if external else None,'external_time_last':external[-1] if external else None}
    order=collections.defaultdict(list)
    for row in trace:order[row['app_update_id']].append(row['phase'])
    report['observed_phase_order_patterns']=dict(collections.Counter(' -> '.join(v) for v in order.values()))
    save(parent/'analysis/phase_summary.json',report);return report


if __name__=='__main__':print(json.dumps(analyze(sys.argv[1])))
