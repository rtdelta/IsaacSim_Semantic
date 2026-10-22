"""Freeze planned repetitions/controls before observing their outputs."""
import json
from pathlib import Path
from tools.experiments.storage import save
ROOT=Path(__file__).resolve().parents[2]
base=json.loads((ROOT/'config/experiments/e0_scene18.json').read_text())
paths=[]
for repeat in ('r01','r02','r03'):
    spec=dict(base,experiment_id='paired_20261014_e1_scene18_mixed',repeat=repeat,targets=100,
        block='mixed_10s',wall_timeout_s=600,frozen_timeout_s=900,disk_bytes=2*1024**3,
        scope='E1 selected mixed 0.3m/s +3deg/s block, 10s planned coverage, three independent C/F Kit initializations; other recommended blocks separate',
        planned_gmo_full_indices=[0,50,99])
    path=ROOT/('config/experiments/e1_scene18_'+repeat+'.json');save(path,spec);paths.append(path.relative_to(ROOT).as_posix())
spec=dict(base,experiment_id='paired_20261014_e0_room',repeat='r03',scene='room',targets=12,block='room_mixed_short_e0',
    full_gmo_all=True,scope='E0 known-room frozen reference qualification, distinct from original v06 scene18')
save(ROOT/'config/experiments/e0_room.json',spec)
save(ROOT/'config/experiments/e1_scene18_batch.json',{'specs':paths,'continue_after_failed_case':False})
aligned=dict(base,experiment_id='paired_20261014_e0_scene18_lighting',repeat='r01',align_v06_lighting=True,
    scope='E0 controlled same single DomeLight, short exact-state pair; distinguish image lighting confound')
save(ROOT/'config/experiments/e0_scene18_lighting.json',aligned)
paths=[]
for repeat in ('r01','r02','r03'):
    spec=dict(base,experiment_id='paired_20261014_e2_room_mixed',repeat=repeat,scene='room',targets=100,block='room_mixed_10s',
        full_gmo_all=True,disk_bytes=2*1024**3,wall_timeout_s=600,frozen_timeout_s=900,
        scope='E2 mixed 10s known no-noise room; three independent paired repetitions, all GMO retained; original v06 scene18 is separate')
    path=ROOT/('config/experiments/e2_room_'+repeat+'.json');save(path,spec);paths.append(path.relative_to(ROOT).as_posix())
save(ROOT/'config/experiments/e2_room_batch.json',{'specs':paths,'continue_after_failed_case':False})
