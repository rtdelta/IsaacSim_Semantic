"""Lock the bounded POST and paired HOLD mechanism controls before native runs."""
import datetime,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
folder=ROOT/'config/clock_state'
base=json.loads((folder/'T0_B_r01.json').read_text())
conditions={
    'T5_PRE':{'write_phase':'PRE'},'T5_POST':{'write_phase':'POST'},
    'T6_HOLD2_WRITE':{'hold_pattern':'HOLD2','hold_write_policy':'WRITE_SAME'},
    'T6_HOLD2_SKIP':{'hold_pattern':'HOLD2','hold_write_policy':'SKIP_WRITE'},
    'T6_ALT_WRITE':{'hold_pattern':'HOLD_ALT','hold_write_policy':'WRITE_SAME'},
    'T6_ALT_SKIP':{'hold_pattern':'HOLD_ALT','hold_write_policy':'SKIP_WRITE'}}
created=[]
def save(name,data):
    path=folder/name
    if path.exists():raise RuntimeError('Refuse overwrite '+str(path))
    path.write_bytes((json.dumps(data,indent=2,ensure_ascii=False)+'\n').encode('utf-8'));created.append(path)
for name,settings in conditions.items():
    for repeat,targets,qual in [('r01',12,True),('r01',100,False),('r02',100,False),('r03',100,False)]:
        condition=name+('_qualification' if qual else '')
        spec=dict(base,experiment_id='clock_20261014_v2',condition=condition,block=condition,repeat=repeat,targets=targets,
            measurement_revision=3,compress_gmo=True,write_phase='PRE',hold_pattern='HOLD0',hold_write_policy='WRITE_SAME')
        spec.update(settings)
        spec['branch_reason']='T1 transient USD/Fabric phase mismatch and repeatable rotation-only lag support testing submission phase; paired HOLD2/ALT directly test keep-writing versus no authoring under continuing physical updates.'
        spec['scope']='003 v1.1 bounded T5 and T6 mechanism controls. Full original GMO retained losslessly; no formal acceptance or payload freshness claim.'
        spec['mechanism_path_policy']='Unchanged per-moving-step increment. Average speed and target path differ across HOLD patterns; WRITE/SKIP same pattern must have identical actual tables.'
        save(condition+'_'+repeat+'.json',spec)
def batch(name,pairs,reason):
    specs=['config/clock_state/'+condition+'_'+repeat+'.json' for condition,repeat in pairs]
    save(name+'_batch.json',{'schema_version':1,'batch_id':'clock_20261014_'+name,'specs':specs,'planned_order':specs,
        'max_pairs':6,'disk_budget_bytes':len(specs)*4*1024**3,'free_reserve_bytes':8*1024**3,
        'stop_on_failed_measurement_qualification':True,'rules':base['analysis_rules'],'reason':reason})
batch('branches_qualification',[(c+'_qualification','r01') for c in conditions],
    'All six selected conditions first qualify 12 targets; main runs only after all measurement qualifications pass.')
batch('t5',[(c,r) for c,r in [('T5_PRE','r01'),('T5_POST','r01'),('T5_POST','r02'),('T5_PRE','r02'),('T5_PRE','r03'),('T5_POST','r03')]],
    'Same v2 recorder/storage on PRE and POST; PRE is also the single shared HOLD0 baseline.')
hold=list(conditions)[2:]
for i,repeat in enumerate(('r01','r02','r03'),1):
    order=hold if i!=2 else [hold[1],hold[0],hold[3],hold[2]]
    batch('t6_'+repeat,[(c,repeat) for c in order],'Locked paired HOLD2 and HOLD_ALT mechanism set; original moving-step increment, no application speed compensation.')
save('branch_selection_v2.json',{'schema_version':1,'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'enabled':['T5 PRE/POST','T6 HOLD2 WRITE/SKIP','T6 HOLD_ALT WRITE/SKIP'],
    'shared_HOLD0':'T5_PRE; not counted twice as an independent repeat',
    'not_run':{'T3':'No initial-yaw/phase sweep in this bounded branch; internal history is unobservable.',
        'T6 HOLD1/HOLD3':'Prospectively reduced to requested two practical patterns and both authoring controls to bound raw evidence/time budget.',
        'T6 application trajectories':'Separate same-boundary trajectory qualification needed; this branch answers only mechanism/geometry.',
        'T7':'Requires selected mode qualification including currently unavailable payload freshness; no automatic promotion.'},
    'qualification_targets':12,'main_targets':100,'independent_repeats':3,
    'mandatory_keep_failed_conditions':True,'retention':'Keep all previous and failed data; never delete to free space',
    'files':[{'path':p.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in created]})
print(json.dumps({'files':len(created),'manifest':str(folder/'branch_selection_v2.json')}))
