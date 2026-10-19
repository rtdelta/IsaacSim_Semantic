"""Exact snapshots: no interpolation, nearest-neighbour or timestamp shift."""
from tools.experiments.storage import rows,save,digest,verify


def export(directory):
    verify(directory)
    targets=rows(directory/'targets.jsonl')
    spec=__import__('json').loads((directory/'experiment_spec.json').read_text())
    result=__import__('json').loads((directory/'run_result.json').read_text())
    lookup={row['target_index']:row for row in targets}
    if len(lookup)!=len(targets):raise ValueError('Duplicate actual target states')
    entries=[]
    for index in range(spec['targets']):
        row=lookup.get(index)
        entries.append({'target_index':index,'source_epoch':result['source_epoch'],
            'source_target_step':result['first_physical_step']+index*spec['stride'],
            'actual_state_available':row is not None,'target':row})
    value={'schema_version':1,'source_targets_sha256':digest(directory/'targets.jsonl'),
        'mapping':'exact immutable physics POST_STEP snapshots; F clock epoch remains independent',
        'requested_targets':spec['targets'],'entries':entries}
    save(directory.parent/'pair_trajectory.json',value)
    return value
