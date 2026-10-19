"""Preregister first matrix including blocked official-USD branches."""
import copy,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
CFG=ROOT/'config/native_rotation_localization/v1';CFG.mkdir(parents=True,exist_ok=True)
def save(name,data):
 p=CFG/name;p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists():raise RuntimeError('Refuse preregistration overwrite '+str(p))
 p.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
base=json.loads((ROOT/'config/native_instant_baseline/specs/M_E_S0_r01_q04.json').read_text())
rules=json.loads((ROOT/'config/native_instant_baseline/analysis_rules_v4.json').read_text());rules.update(version='native007-v1',direction_p95_rad=1e-4,direction_scope='output representation, no direct emitted-ray evidence')
save('analysis_rules.json',rules)
overrides={'omni:sensor:tickRate':10.,'omni:sensor:Core:rangeAccuracyM':0.,'omni:sensor:Core:instantLidar':True,
 'omni:sensor:Core:scanRateBaseHz':10.,'omni:sensor:Core:outputFrameOfReference':'SENSOR',
 'omni:sensor:Core:elementsCoordsType':'CARTESIAN','omni:sensor:Core:outputMotionCompensationState':'NONCOMPENSATED','omni:sensor:Core:accumulateOutputs':True}
conditions={}
for key in ('A0','A1','A2','A3','B1','B2'):
 c={'condition':key,'api':'official' if key in ('A1','A3') else 'native','asset':'official_example_usd' if key in ('A2','A3') else 'MyAiry',
   'sensor_overrides':dict(overrides),'capability':'blocked_missing_local_official_USD' if key in ('A2','A3') else 'qualification_pending'}
 if key=='B1':c['sensor_overrides']['omni:sensor:Core:outputFrameOfReference']='WORLD'
 if key=='B2':c['sensor_overrides']['omni:sensor:Core:elementsCoordsType']='SPHERICAL'
 conditions[key]=c
save('conditions.json',conditions)
save('assets.json',{'MyAiry':{'path':base['scene_asset'],'prim':base['source_prim'],'sha256':'e44ff38c21caaaccf20aa44a9b834e33d7109407e737df27198a63ad95e9fb79'},
 'official_example_usd':{'status':'blocked_missing_local_official_USD','searched_roots':['/root/isaacsim/exts','/root/isaacsim/extscache','/root/gpufree-data/IsaacSim_Asset'],
 'found_legacy_json':'Example_Rotary.json and Example_Rotary_2D.json; not substituted for official USD asset',
 'required_asset':'Isaac/Sensors/NVIDIA/Example_Rotary.usda','network_asset_loading':False}})
save('api_contracts.json',{'official_classes':'isaacsim.sensors.experimental.rtx.Lidar and LidarSensor','reference_codes':{'SENSOR':0,'WORLD':1},
 'coordinate_codes':{'CARTESIAN':0,'SPHERICAL':1},'spherical_order':['azimuth_deg','elevation_deg','distance_m'],
 'normalization':'right-handed Cartesian; identity model transform qualified separately; WORLD never reapplies sensor pose',
 'api_poll_identity':['epoch','product','frameId','timestampNs'],'api_time_proof':'same-identity same-product Writer declared bytes, then Writer source/ref unique exact physical step',
 'topology_scope':'A1/A3 official API plus official product and additional GMO annotator; bridge if results differ',
 'direct_consumption_evidence':'unavailable in inspected public Python/headers; frameStart/end are output metadata',
 'sources':['reports/native007_contracts_20261015.json','reports/native007_capabilities_20261015.json']})
order=[];q=[];m=[]
def spec(key,profile,n,repeat,phase):
 s=copy.deepcopy(base);c=conditions[key]
 s.update(suite='native_rotation_localization_v1',experiment_id='native007_20261015_v1',group='M_'+key,condition=key,profile=profile,block=profile,
   repeat=repeat,run_id='q01' if phase.startswith('Q') else 'm01',targets=n,api=c['api'],sensor_overrides=c['sensor_overrides'],
   entry='tools/native_rotation_localization/run_layers.py',analysis_rules_path='config/native_rotation_localization/v1/analysis_rules.json',
   analysis_rules_sha256=sha(CFG/'analysis_rules.json'),phase=phase,initial_yaw_deg=5. if profile=='S5' else 0.,
   yaw_rate_deg_s=6. if profile=='R6P' else 3. if profile=='R3P' else 0.,revision_reason='007 independent version; source 006 preserved')
 s.pop('configuration_sha256',None)
 s['output_relative']=f"reports/native_rotation_localization/{s['experiment_id']}/{key}/{profile}/{repeat}/{s['run_id']}"
 name=f'specs/{key}_{profile}_{repeat}_{s["run_id"]}.json';save(name,s)
 row={'spec':'config/native_rotation_localization/v1/'+name,'condition':key,'profile':profile,'repeat':repeat,'targets':n,'phase':phase,'capability':c['capability']};order.append(row)
 return row
for key in conditions:
 for profile in ('S0','S5','R6P'):q.append(spec(key,profile,12,'r01','Q1'))
for key in conditions:q.append(spec(key,'R3P',12,'r01','Q2'))
for repeat,keys in [('r01',['A0','A3','B1','B2']),('r02',['B2','B1','A3','A0']),('r03',['A3','A0','B2','B1'])]:
 for key in keys:m.append(spec(key,'R6P',100,repeat,'M1'))
save('planned_order.json',{'runs':order,'planned_runs':36,'planned_targets':1488,'blocked_runs':sum(r['capability'].startswith('blocked') for r in order),'B0':'reuse A0'})
for name,runs in [('qualification',q),('main',m)]:save(name+'_sequence.json',{'id':name+'_q01' if name=='qualification' else 'main_m01','runs':runs,'max_batch_runs':4,'reserve_bytes':8*1024**3,'requires_lock':name=='main'})
print({'runs':len(order),'targets':sum(r['targets'] for r in order),'blocked':sum(r['capability'].startswith('blocked') for r in order)})
