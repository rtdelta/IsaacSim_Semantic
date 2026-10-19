"""Freeze 005 E and full mandatory order before any qualification capture."""
import datetime,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.native_instant_baseline.io import save,sha
from tools.native_instant_baseline.runtime import E_SETTINGS

def generate():
    cfg=ROOT/'config/native_instant_baseline';cfg.mkdir(exist_ok=False)
    observed=json.loads((ROOT/'reports/native005_effective_E_probe_r02_20261015.json').read_text())['fingerprint']
    if not all(observed['effective']['settings'][k]==v for k,v in E_SETTINGS.items()):raise ValueError('Requested E does not match fresh observed E')
    frozen={'schema_version':1,'frozen_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'requested_settings':E_SETTINGS,'observed':observed,
        'probe':'reports/native005_effective_E_probe_r02_20261015.json','probe_sha256':sha(ROOT/'reports/native005_effective_E_probe_r02_20261015.json')}
    save(cfg/'effective_E.json',frozen)
    rules={'schema_version':1,'source_tolerance_ns':2,'input_translation_m':1e-5,'input_rotation_rad':1e-6,'physical_and_scan_increment_rad':2e-6,
      'native_translation_m':.001,'native_rotation_rad':1e-4,'ray_p95_m':1e-5,'plane_p95_m':.005,'geometry_yaw_rad':1e-4,
      'fit_wall_margin_m':.05,'fit_min_points':100,'fit_min_per_nonparallel_wall':32,'fit_min_information_m2':1.,'fit_iterations':4,'fit_range_deg':.2,
      'candidate_ids':['current','half','previous1','previous2'],'equivalence_translation_m':1e-8,'equivalence_rotation_rad':1e-8,
      'candidate_ratio_min':10.,'candidate_gap_min_m':2e-5,'quantiles':'nearest_rank','formal_continuous_acceptance':False,
      'common_orientations_deg':[.6*i for i in range(1,51)],'common_orientation_indices_R3P':list(range(1,100,2)),'common_orientation_indices_R6P':list(range(50))}
    save(cfg/'analysis_rules_v1.json',rules)
    profiles={'S0':(0.,0.),'S5':(0.,5.),'R3P':(3.,0.),'R3N':(-3.,0.),'R6P':(6.,0.)}
    experiment='native005_20261015_v1';all_specs=[]
    def spec(group,profile,repeat,run_id,N):
        speed,initial=profiles[profile];name='%s_%s_%s_%s'%(group,profile,repeat,run_id)
        s={'schema_version':1,'native_instant_baseline':True,'suite':'native_instant_baseline_v1','experiment_id':experiment,'group':group,'profile':profile,
          'condition':profile,'block':profile,'repeat':repeat,'run_id':run_id,'targets':N,'physics_hz':60,'stride':6,'speed_m_s':0.,'yaw_rate_deg_s':speed,
          'initial_yaw_deg':initial,'stage_probe':False,'warmup_updates':24,'drain_cycles':2,'queue_bytes':256*1024**2,'disk_bytes':2*1024**3,
          'init_timeout_s':180,'wall_timeout_s':600,'compress_gmo':True,'table_write':True,'write_phase':'PRE','scene':'room',
          'scene_asset':'/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_18_terrain_fisheye_mesh.usda','source_prim':'/World/Excavator/swing_link/MyAiry_front/sensor',
          'requested_settings':E_SETTINGS,'configuration_sha256':sha(cfg/'effective_E.json'),'analysis_rules_sha256':sha(cfg/'analysis_rules_v1.json'),
          'entry':'tools/native_instant_baseline/run_minimal.py' if group=='M_E' else 'tools/clock_state/run_continuous.py',
          'output_relative':'reports/native_instant_baseline/%s/%s/%s/%s/%s'%(experiment,group,profile,repeat,run_id)}
        rel='config/native_instant_baseline/specs/'+name+'.json';save(ROOT/rel,s);all_specs.append(rel);return rel
    qualify=[spec(g,p,'r01','q01',12) for p in ('S0','S5','R3P') for g in ('M_E','P_E')]
    main=[spec(g,p,r,'main_v1',100) for p in ('S0','R3P','R3N','R6P') for g,r in [('M_E','r01'),('P_E','r01'),('P_E','r02'),('M_E','r02'),('M_E','r03'),('P_E','r03')]]
    batches=[]
    for name,items,phase in [('q_static',qualify[:4],'qualification'),('q_rotation',qualify[4:],'qualification')]+[('main_%02d'%(i//4+1),main[i:i+4],'main') for i in range(0,len(main),4)]:
        bid='native005_'+name+'_v1';relative='config/native_instant_baseline/'+bid+'.json'
        save(ROOT/relative,{'batch_id':bid,'experiment_id':experiment,'phase':phase,'specs':items,'free_reserve_bytes':8*1024**3,'previous_batch':batches[-1] if batches else None,
          'budget_rule':'maximum four runs; qualification observed bytes/event estimate plus 8 GiB reserve; per-run uncompressed hard bound 2 GiB'})
        batches.append(bid)
    save(cfg/'run_order.json',{'experiment_id':experiment,'qualification':qualify,'main':main,'batches':batches,'D_status':'pending installed-default reconnaissance; no D sample may precede separate frozen declaration'})
    print(json.dumps({'specs':len(all_specs),'batches':batches,'E_sha256':sha(cfg/'effective_E.json')}))
if __name__=='__main__':generate()
