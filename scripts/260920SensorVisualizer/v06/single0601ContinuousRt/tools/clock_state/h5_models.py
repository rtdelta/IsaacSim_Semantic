"""Preregistered explanatory float32 models, never an SDK implementation claim."""
import hashlib,json,sys
from pathlib import Path
import numpy as np
PROJECT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(PROJECT))
from tools.experiments.storage import rows,save,digest


def dot_models(a,b):
    a=np.asarray(a,dtype=np.float32);b=np.asarray(b,dtype=np.float32);products=a*b
    total=np.float32(0.)
    for p in products:total=np.float32(total+p)
    pair=np.float32(np.float32(products[0]+products[1])+np.float32(products[2]+products[3]))
    wide=np.float32(np.sum(a.astype(float)*b.astype(float)))
    return {'float32_products_float32_sequential_sum':float(total),'float32_products_pairwise_sum':float(pair),
        'float64_products_sum_then_float32':float(wide)}


def analyze(parent):
    parent=Path(parent);spec=json.loads((parent/'experiment_spec.json').read_text())
    registration=json.loads((PROJECT/'reports/clock_state_consistency/h5_model_registration.json').read_text())
    rules_path=PROJECT/'config/clock_state/h5_numerical_models_v1.json'
    if digest(rules_path)!=registration['rules_sha256']:raise ValueError('Preregistered H5 rule hash changed')
    rules=json.loads(rules_path.read_text());states={r['physical_step']:r for r in rows(parent/'continuous/actual_states.jsonl')}
    components=json.loads((parent/'analysis/component_delay.json').read_text());observations=[]
    for c in components:
        step=c['physical_step'];current=states.get(step);previous=states.get(step-1)
        observable=c['interpretation_qualified'] and c['rotation_delay_identifiable'] and c['rotation_lag_steps'] is not None and len(c['rotation_lag_steps'])==1
        if not current or not previous:observable=False
        values=dot_models(previous['root']['orientation_xyzw'],current['root']['orientation_xyzw']) if current and previous else None
        observations.append({'target_index':c['target_index'],'physical_step':step,'rotation_delay_observable':observable,
            'rotation_lag_steps':c['rotation_lag_steps'][0] if observable else None,'input_dot_models':values})
    eps=float(np.finfo(np.float32).eps);thresholds={'1':1.,'1-eps/2':1.-eps/2,'1-eps':1.-eps,'1-2eps':1.-2*eps}
    evaluated=[r for r in observations if r['rotation_delay_observable']];models=[]
    for name in rules['dot_models']:
        for threshold_name in rules['float32_thresholds']:
            threshold=thresholds[threshold_name]
            for op in rules['comparisons']:
                predictions=[1. if (r['input_dot_models'][name]>threshold if op=='>' else r['input_dot_models'][name]>=threshold) else .5 for r in evaluated]
                errors=[r['target_index'] for r,p in zip(evaluated,predictions) if r['rotation_lag_steps']!=p]
                models.append({'dot_model':name,'threshold':threshold_name,'threshold_value':threshold,'comparison':op,
                    'correct':len(evaluated)-len(errors),'evaluable':len(evaluated),'correct_fraction':1-len(errors)/len(evaluated) if evaluated else None,
                    'mismatched_target_indices':errors})
    baselines={str(lag):sum(r['rotation_lag_steps']==lag for r in evaluated)/len(evaluated) if evaluated else None for lag in (.5,1.)}
    result={'schema_version':1,'model_registration':registration,'analyzer_sha256':digest(Path(__file__)),
        'condition':spec['condition'],'repeat':spec['repeat'],'planned_targets':spec['targets'],'evaluable_rotation_delays':len(evaluated),
        'unavailable_or_unobservable_targets':spec['targets']-len(evaluated),'constant_lag_baseline_correct_fraction':baselines,
        'models':models,'observations':observations,
        'interpretation':'Association only. Actual GPU quaternion representation, normalization, reduction order and interpolation branch are unobserved. Native output endpoints are not used as GPU input ground truth.'}
    save(parent/'analysis/h5_numerical_models.json',result)
    print(json.dumps({'condition':spec['condition'],'repeat':spec['repeat'],'evaluable':len(evaluated),'baselines':baselines,
        'best_correct_fraction':max((m['correct_fraction'] for m in models if m['correct_fraction'] is not None),default=None)}));return result


if __name__=='__main__':analyze(sys.argv[1])
