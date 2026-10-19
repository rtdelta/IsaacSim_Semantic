import datetime,hashlib,json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
data='{\n  "schema_version": 1,\n  "hypothesis": "Exploratory float32 small-angle branch models, preregistered before fresh T2 100-target and T4 captures; not a claim about installed GPU implementation",\n  "input": "actual POST root quaternion at source step and previous step, converted to float32; GPU normalization and reduction order are unobserved",\n  "float32_thresholds": [\n    "1",\n    "1-eps/2",\n    "1-eps",\n    "1-2eps"\n  ],\n  "comparisons": [\n    ">",\n    ">="\n  ],\n  "dot_models": [\n    "float32_products_float32_sequential_sum",\n    "float32_products_pairwise_sum",\n    "float64_products_sum_then_float32"\n  ],\n  "predicted_rotation_lag_steps": {\n    "branch_true": 1,\n    "branch_false": 0.5\n  },\n  "baselines": [\n    "constant_half_step",\n    "constant_previous_step"\n  ],\n  "denominator": "all planned targets; report unavailable/unobservable separately, never infer position delay in pure rotation",\n  "validation_runs": [\n    "T2_Rplus/r01-r03",\n    "T2_Rminus/r01-r03",\n    "T4_B120_3/r01-r03",\n    "T4_C120_6/r01-r03"\n  ],\n  "interpretation": "Association only. Native endpoints are output, not proof of the GPU input; no source clock or point changes."\n}\n'
path=root/'config/clock_state/h5_numerical_models_v1.json'
record=root/'reports/clock_state_consistency/h5_model_registration.json'
if record.exists():
    assert path.read_text()==data
    print(record.read_text())
else:
    base=root/'reports/clock_state_consistency/clock_20261014_v1'
    assert not (base/'T2_Rplus/repeats/r01').exists()
    assert not (base/'T4_B120_3/repeats/r01').exists()
    path.write_text(data)
    result={'schema_version':1,'registered_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'rules_sha256':hashlib.sha256(data.encode()).hexdigest(),'registered_before_T2_100_target_and_T4':True,'available_calibration_data':'T0 and short T2 qualifiers; planned 100-target T2 and T4 remain prospective','rules':json.loads(data)}
    record.write_text(json.dumps(result,indent=2));print(json.dumps(result))
