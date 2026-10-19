"""Local supervisor for this one authorized suite; audited reads and SFTP only."""
import datetime,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OPS=Path('C:/Users/15452/.codex/skills/cloud-instance-ops/scripts/ops.py')
PROFILE=ROOT.parent/'migrations/20261010_dual_gpu/targets.json'
EXPECTED='comparison_20261012_070140'
OUT=ROOT/'results'/EXPECTED
def run():
 OUT.mkdir(parents=True,exist_ok=True);iteration=0;downloaded=set();connection_failures=0
 while True:
  iteration+=1;now=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S')
  p=subprocess.run([sys.executable,'-X','utf8',str(OPS),'--config',str(PROFILE),'exec','--target','isaac-new','--task','NC004','--purpose','Check this comparison suite and retrieve completed generated evidence','--script',str(ROOT/'tools/status_remote.py'),'--intent','read','--timeout','60'],capture_output=True,text=True,encoding='utf-8',timeout=85)
  log=ROOT/'reports'/f'watch_status_{now}_{iteration:03d}.json';log.write_text(p.stdout,encoding='utf-8')
  if p.stderr:(ROOT/'reports'/f'watch_status_{now}_{iteration:03d}.stderr.log').write_text(p.stderr,encoding='utf-8')
  if p.returncode:
   connection_failures+=1
   print(json.dumps({'status_read_failed':str(log),'consecutive_failures':connection_failures,'cloud_suite_action':'none'}),flush=True)
   if connection_failures>=3:raise RuntimeError('Three audited status attempts failed; suite not stopped. Inspect '+str(log))
   time.sleep(20*connection_failures);continue
  connection_failures=0
  audit=json.loads(p.stdout);r=audit['result']
  if r['exit_code']:raise RuntimeError('Remote status failed: '+str(log))
  status=json.loads(r['stdout'])
  if Path(status['suite']['directory']).name!=EXPECTED:raise RuntimeError('Latest suite changed; refused to follow another job')
  progress={'state':status['state'],'planned_cases':status['planned'],'completed_cases':status['cases'],'current':status['current'],'error':status.get('error')}
  (OUT/'progress.json').write_text(json.dumps(progress,indent=2),encoding='utf-8')
  for c in status['cases']:
   key=(c['id'],c['round'])
   if key in downloaded or 'decode_exit' not in c:continue
   dest=OUT/c['id']/f'round_{c["round"]:02d}'
   # Existing fully transferred captures are immutable. Analysis files are local products.
   if (dest/'transfer_manifest.json').exists() and (dest/'decoded.json').exists():downloaded.add(key);continue
   q=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'tools/pull_evidence.py'),c['directory'],'--destination',str(dest),'--exclude-name','timing.csv','--exclude-name','timing.json'],capture_output=True,text=True,encoding='utf-8',timeout=900)
   (ROOT/'reports'/f'transfer_{c["id"]}_round_{c["round"]:02d}.log').write_text(q.stdout+q.stderr,encoding='utf-8')
   if q.returncode:raise RuntimeError('Completed-case transfer failed; cloud suite continues: '+str(key))
   downloaded.add(key);print(json.dumps({'downloaded':list(key),'count':len(downloaded)}),flush=True)
  note={'observed_at_utc':now,'state':status['state'],'completed':status['completed'],'downloaded':len(downloaded),'current':status['current'],'elapsed_s':status.get('elapsed_s'),'groups_current':status.get('groups.jsonl_count')}
  (ROOT/'reports/local_watch_status.json').write_text(json.dumps(note,indent=2),encoding='utf-8');print(json.dumps(note),flush=True)
  if status['state'] in ('completed','failed','stopped'):
   for name in ('analyze_suite.py','plot_resources.py'):
    q=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'tools'/name),str(OUT)],capture_output=True,text=True,encoding='utf-8',timeout=900)
    (ROOT/'reports'/(name+'.log')).write_text(q.stdout+q.stderr,encoding='utf-8')
    if q.returncode:raise RuntimeError('Postprocessing failed: '+name)
    print(q.stdout,flush=True)
   print('COMPLETE: cloud suite ended; all completed artifacts transferred and analyzed.',flush=True);return
  time.sleep(50)
if __name__=='__main__':run()
