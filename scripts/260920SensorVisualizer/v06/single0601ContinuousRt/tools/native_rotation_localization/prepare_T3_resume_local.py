import copy,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];CFG=ROOT/'config/native_rotation_localization/v1'
old=json.loads((CFG/'extension_T3_q01_sequence.json').read_text());rows=copy.deepcopy(old['runs'])
for row in rows:
 if row['condition']=='C1':row['capability']='blocked_accumulation_false_changes_warmup_native_cadence; C1_S0_actual_failed_prefix_preserved'
new=dict(old,id='extension_T3_resume_q01',runs=rows,revision_reason='Do not rerun C1 or decimate outputs: first C1 warmup violates fixed stride contract. Record all C1 planned profiles blocked; continue predeclared independent C2 using unchanged specs and capture lock.')
for name,data in [('extension_T3_resume_q01_sequence.json',new),('T3_resume_release.json',{'sequence':'extension_T3_resume_q01','original_sequence':'extension_T3_q01','C1_failure_path':'reports/native_rotation_localization/native007_20261015_v1/C1/S0/r01/cq01','reason':'fixed warmup native tick phase unqualified; complete prefix inspected independently','C2_specs_unchanged':True})]:
 p=CFG/name
 if p.exists():raise RuntimeError('Refuse overwrite '+name)
 p.write_text(json.dumps(data,indent=2)+'\n')
print({'resume_rows':len(rows),'executable_C2':4})
