"""Serial independent-process comparison. No shared render loop or data publisher."""
import hashlib,json,os,shutil,signal,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent;OUTPUT=Path('/root/gpufree-data/semantic/output/capture_comparison_004')
def write(p,v):
 t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(v,indent=2));t.replace(p)
def alive_kit():
 found=[]
 for p in Path('/proc').glob('[0-9]*/cmdline'):
  try:
   if p.read_bytes().split(b'\0')[0].endswith(b'/kit/kit'):found.append(int(p.parent.name))
  except OSError:pass
 return found
def run():
 suite=json.loads((ROOT/'config/suite.json').read_text());scene=Path(suite['scene'])
 if hashlib.sha256(scene.read_bytes()).hexdigest()!=suite['scene_sha256']:raise RuntimeError('Scene differs from approved baseline')
 if alive_kit():raise RuntimeError('Existing Isaac process; it was not stopped')
 out=OUTPUT/('comparison_'+time.strftime('%Y%m%d_%H%M%S',time.gmtime()));out.mkdir(parents=True,exist_ok=False)
 write(ROOT/'reports/latest_suite.json',{'pid':os.getpid(),'directory':str(out)})
 write(out/'suite_spec.json',suite);write(out/'suite_sources.json',{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.rglob('*') if p.is_file() and not any(x in p.relative_to(ROOT).parts for x in ('reports','backups','deploy_history','__pycache__'))})
 source=Path(suite['source_trajectory']);traj=out/'input_trajectory';traj.mkdir()
 states=[json.loads(l) for l in (source/'states.jsonl').read_text().splitlines() if l.strip()];first=states[0]
 for s in states:
  for key in ('position_world_m','quaternion_xyzw','mount_revision'):s[key]=first[key]
  s['joints_deg']={n:0. for n in s['joints_deg']}
 (traj/'states.jsonl').write_text(''.join(json.dumps(s)+'\n' for s in states));meta=json.loads((source/'metadata.json').read_text());write(traj/'metadata.json',meta)
 progress={'state':'running','directory':str(out),'planned_cases':suite['rounds']*len(suite['configurations']),'completed_cases':[],'current':None,'started_utc_ns':time.time_ns()}
 write(out/'progress.json',progress)
 child=None
 def stop(signum,frame):
  (out/'stop.request').write_text(str(signum))
  if child and child.poll() is None:child.send_signal(signal.SIGINT)
 for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,stop)
 try:
  for repeat in range(suite['rounds']):
   configs=suite['configurations'];shift=repeat*3%len(configs);order=configs[shift:]+configs[:shift]
   for config in order:
    if (out/'stop.request').exists():break
    if shutil.disk_usage(OUTPUT).free/1024**3<suite['minimum_free_gib']:raise RuntimeError('Insufficient free space; no data removed')
    if alive_kit():raise RuntimeError('Previous or unrelated Kit still active')
    case=out/config['id']/f'round_{repeat+1:02d}';case.mkdir(parents=True,exist_ok=False)
    cfg=dict(config,repeat=repeat,requested_groups=suite['groups'],source_scene_sha256=suite['scene_sha256'])
    write(case/'config.json',cfg);capture=case/'capture'
    if config['family']=='v06':
     spec={'name':config['id'],'pose':'static','trajectory':str(traj),'groups':suite['groups'],'timeout_s':900,'policy':config['policy']}
     write(case/'input_spec.json',spec);args=['/usr/bin/python3','-u','-m','lab.runner','--spec',str(case/'input_spec.json'),'--output',str(capture)];cwd=BASE/'single06_lab'
    else:
     engine=ROOT/'engines'/config['engine'];spec=json.loads((engine/'config/baseline.json').read_text())
     spec.update(scene=suite['scene'],scene_sha256=suite['scene_sha256'],trajectory=str(traj/'states.jsonl'),measure_frames=suite['groups'],warmup_frames=8,render_mode=config['renderer'],motion='static',multi_tick=False,trace=False,mode='record',repeat=repeat,pt_total_spp=1024,pt_spp=32,pt_bounces=8,export_quality_images=False,extra_capture_png=False,bypass_native_simulation_gate=config['bypass'],gate_products_between_groups=False,native_preview_initialization=False,timeout_s=1800)
     spec['experiment']='continuous_pt' if config['engine']=='continuous_pt' else None if config['engine']=='continuous_rt' else 'comparison_static'
     spec['schedule']='continuous' if config['engine']=='continuous_rt' else 'native_run' if config['engine']=='continuous_pt' else 'frozen'
     write(case/'input_spec.json',spec);args=['/usr/bin/python3','-u',str(engine/'run.py'),'--config',str(case/'input_spec.json'),'--output',str(capture)];cwd=engine
    began=time.monotonic_ns();progress['current']={'id':config['id'],'round':repeat+1,'directory':str(case),'started_monotonic_ns':began};write(out/'progress.json',progress)
    with (case/'supervisor.log').open('xb') as log:
     child=subprocess.Popen(args,cwd=cwd,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True);progress['current']['pid']=child.pid;write(out/'progress.json',progress)
     while child.poll() is None:time.sleep(1)
    record={'id':config['id'],'round':repeat+1,'directory':str(case),'exit_code':child.returncode,'supervisor_wall_s':(time.monotonic_ns()-began)/1e9}
    child=None;progress['completed_cases'].append(record);progress['current']=None;write(out/'progress.json',progress)
    # Decode only after the engine and recorder have both completed.
    decoder=ROOT/'tools/decode_case.py'
    if decoder.exists():
     p=subprocess.run(['/bin/bash','-c','source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 "$1" "$2"','nc004',str(decoder),str(case)],capture_output=True,text=True,timeout=900)
     (case/'decode.log').write_text(p.stdout+p.stderr);record['decode_exit']=p.returncode;write(out/'progress.json',progress)
    if alive_kit():raise RuntimeError('Kit left active after case completion')
   if (out/'stop.request').exists():break
  progress['state']='stopped' if (out/'stop.request').exists() else 'completed';progress['finished_utc_ns']=time.time_ns();write(out/'progress.json',progress)
 except BaseException as exc:
  progress['state']='failed';progress['error']=type(exc).__name__+': '+str(exc);write(out/'progress.json',progress);raise
 return out
if __name__=='__main__':print(run())
