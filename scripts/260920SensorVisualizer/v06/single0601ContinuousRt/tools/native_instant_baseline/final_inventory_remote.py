"""Final preserved-result inventory and frozen-code check; no simulator launch."""
import collections,hashlib,json,shutil
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt');base=root/'reports/native_instant_baseline'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
order=json.loads((root/'config/native_instant_baseline/run_order.json').read_text());suite=base/order['experiment_id']
status=json.loads((suite/'sequence_status.json').read_text())
if status['state']=='running':raise RuntimeError('Sequence still running')
lock=json.loads((root/'config/native_instant_baseline/main_code_lock.json').read_text());changed=[r['path'] for r in lock['files'] if sha(root/r['path'])!=r['sha256']]
records=[]
for p in sorted(suite.glob('**/analysis/summary.json')):
    s=json.loads(p.read_text());c=p.parent.parent/'continuous';m=json.loads((c/'file_manifest.json').read_text())
    records.append({'path':str(p.relative_to(root)),'targets':s['planned_targets'],'raw_events':s['raw_events'],'full_GMO_independently_decoded':s['readback']['full_GMO_independently_decoded'],
        'measurement_qualified':s['measurement_qualified'],'cleanup_ok':s['cleanup_ok'],'evidence_files':len(m['files']),
        'evidence_bytes':sum(x['bytes'] for x in m['files']),'queue_peak_bytes':m['queue_peak_bytes'],'raw_reserved_disk_bytes':m['reserved_disk_bytes'],
        'unassigned_events':s['unassigned_events'],'target_missing':s['target_missing'],'target_duplicate':s['target_duplicate']})
comparisons={p.stem:json.loads(p.read_text())['all_measurement_and_pair_qualified'] for p in suite.glob('*_comparison.json') if 'all_measurement_and_pair_qualified' in json.loads(p.read_text())}
result={'sequence_state':status['state'],'source_lock_files':len(lock['files']),'source_lock_mismatches':changed,'comparison_gates':comparisons,
    'all_preserved_runs':len(records),'all_preserved_targets':sum(r['targets'] for r in records),'all_raw_events':sum(r['raw_events'] for r in records),
    'all_evidence_files':sum(r['evidence_files'] for r in records),'all_evidence_bytes':sum(r['evidence_bytes'] for r in records),
    'max_queue_peak_bytes':max(r['queue_peak_bytes'] for r in records),'max_reserved_disk_bytes':max(r['raw_reserved_disk_bytes'] for r in records),
    'free_bytes':shutil.disk_usage(root).free,'runs':records}
corrected=json.loads((suite/'M_E/S0/r01/q01/corrected_decoder_readback.json').read_text())
result['full_GMO_decoded_including_corrected_q01']=sum(r['full_GMO_independently_decoded'] for r in records)+corrected['full_GMO_decoded']
result['all_raw_GMO_readback_complete']=result['full_GMO_decoded_including_corrected_q01']==result['all_raw_events'] and not corrected['errors']
(suite/'final_inventory.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='runs'}))
