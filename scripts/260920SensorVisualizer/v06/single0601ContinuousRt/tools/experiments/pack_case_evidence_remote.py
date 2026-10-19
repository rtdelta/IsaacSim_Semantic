"""Copy a declared compact evidence subset; all original raw files stay remote."""
import argparse,json,re,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.experiments.storage import digest,rows,save


def pack(experiment):
    if not re.fullmatch(r'paired_20261014_[a-z0-9_]+',experiment):raise ValueError('Unexpected experiment identity')
    source=ROOT/'reports/paired_capture_experiments'/experiment
    target=ROOT/'reports/paired_delivery_evidence'/experiment
    if target.exists():raise ValueError('Evidence subset already exists')
    target.mkdir(parents=True);files=[]
    def copy(path):
        rel=path.relative_to(source);out=target/rel
        if out.exists():return
        out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,out)
        source_hash=digest(path)
        if digest(out)!=source_hash:raise ValueError('Evidence subset copy mismatch')
        files.append({'path':rel.as_posix(),'source':str(path),'bytes':path.stat().st_size,'sha256':source_hash})
    for repeat in sorted((source/'repeats').iterdir()):
        status=repeat/'coordinator_status.json'
        if not status.exists() or json.loads(status.read_text()).get('state') not in ('COMPLETE','FAILED'):raise ValueError('Experiment still running')
        for path in repeat.glob('*.json'):copy(path)
        for path in (repeat/'analysis').glob('*'):
            if path.is_file():copy(path)
        for side in ('continuous','frozen_v06','frozen_room'):
            directory=repeat/side
            if not directory.exists():continue
            for path in directory.glob('*'):
                if path.suffix in ('.json','.jsonl') and path.is_file():
                    if path.name=='sensor_registry.json' and repeat.name!='r01' and source.name!='paired_20261014_e0_scene18':continue
                    copy(path)
            spec=json.loads((repeat/'experiment_spec.json').read_text());indices={0,spec['targets']//2,spec['targets']-1}
            for row in rows(directory/'native_events.jsonl'):
                if row['target_index'] not in indices:continue
                copy(directory/row['payload_path'])
                meta=row.get('native_event',{})
                if meta.get('packet_prefix_path'):copy(directory/meta['packet_prefix_path'])
                if repeat.name=='r01' and meta.get('packet_path'):copy(directory/meta['packet_path'])
    value={'schema_version':1,'scope':'compact subset: all metadata/metrics, fixed first-middle-last payloads, first-repeat full GMO; complete original raw evidence stays at source',
        'source':str(source),'files':files,'bytes':sum(f['bytes'] for f in files)}
    save(target/'delivery_manifest.json',value);print(json.dumps({'directory':str(target),'files':len(files),'bytes':value['bytes']}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('experiment');args=parser.parse_args();pack(args.experiment)
