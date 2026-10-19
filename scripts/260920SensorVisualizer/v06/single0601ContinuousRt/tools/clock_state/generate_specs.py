"""Freeze qualification and T0 observer-effect order before gathering new data."""
import json
from pathlib import Path
from tools.clock_state.candidates import RULES
from tools.experiments.storage import save
ROOT=Path(__file__).resolve().parents[2]
base=json.loads((ROOT/'config/experiments/e2_room_r01.json').read_text())
base.update(suite='clock_state_v1',experiment_id='clock_20261014_v1',condition='qualification_A',repeat='r01',targets=12,
    stage_probe=False,warmup_updates=24,block='predeclared_table_mixed',planned_gmo_full_indices=None,
    scope='003 v1.1 raw-first clock/state diagnostic; independent Kit C/F; no formal continuous acceptance',
    initial_pose='room origin, yaw 0; absolute state readback replayed by frozen reference',initial_yaw_deg=0.,
    analysis_rules=RULES,measurement_revision=1)
def write(condition,repeat,targets,probe,speed=.3,yaw=3.):
    spec=dict(base,condition=condition,repeat=repeat,targets=targets,stage_probe=probe,speed_m_s=speed,yaw_rate_deg_s=yaw)
    path=ROOT/('config/clock_state/%s_%s.json'%(condition,repeat));save(path,spec);return path.relative_to(ROOT).as_posix()
qual=[write('qualification_A','r01',12,False),write('qualification_B','r01',12,True),write('qualification_static','r01',12,True,0.,0.)]
t0=[write('T0_'+label,repeat,100,label=='B') for label,repeat in [('A','r01'),('B','r01'),('B','r02'),('A','r02'),('A','r03'),('B','r03')]]
for name,paths in [('qualification',qual),('t0',t0)]:
    save(ROOT/('config/clock_state/%s_batch.json'%name),{'schema_version':1,'batch_id':'clock_20261014_'+name,'specs':paths,
        'max_pairs':6,'disk_budget_bytes':len(paths)*4*1024**3,'free_reserve_bytes':8*1024**3,'stop_on_failed_measurement_qualification':True,
        'planned_order':paths,'rules':RULES})
