"""Close only the completed, owned offline-parser Kit after cancellable quit did not exit."""
import hashlib,json,os,signal,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt');suite=root/'reports/native_rotation_localization/native007_20261015_v1'
result=json.loads((suite/'final_metadata_crosscheck.json').read_text())
if not result['passed'] or not result['decoded_files']:raise RuntimeError('Verified parser result unavailable')
entry=str(root/'tools/native_rotation_localization/final_metadata_crosscheck.py').encode();owned=[]
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:
  cmd=(p/'cmdline').read_bytes()
  if b'/root/isaacsim/kit/kit\0' in cmd and entry in cmd:owned.append(int(p.name))
 except OSError:pass
if len(owned)!=1:raise RuntimeError('Expected exactly one owned parser Kit')
pid=owned[0]
if os.getpgid(pid)!=pid:raise RuntimeError('Owned parser session identity mismatch')
receipt={'pid':pid,'reason':'All 3730 metadata payload checks saved and passed; cancellable post_quit did not terminate owned offline-parser GUI. Capture stages had already ended; no experiment data changed.',
 'entry_sha256':hashlib.sha256(Path(entry.decode()).read_bytes()).hexdigest(),'result_sha256':hashlib.sha256((suite/'final_metadata_crosscheck.json').read_bytes()).hexdigest(),'actions':['SIGTERM to verified owned process group']}
os.killpg(pid,signal.SIGTERM)
for _ in range(100):
 if not Path('/proc',str(pid)).exists():break
 time.sleep(.1)
if Path('/proc',str(pid)).exists():os.killpg(pid,signal.SIGKILL);receipt['actions'].append('SIGKILL after 10 second owned-process grace')
time.sleep(.2);receipt['process_absent']=not Path('/proc',str(pid)).exists()
(suite/'final_metadata_parser_cleanup.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
