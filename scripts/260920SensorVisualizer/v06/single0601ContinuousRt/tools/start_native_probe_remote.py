"""Start one owned offline Kit native diagnostic; refuse another Kit instance."""
import argparse,hashlib,json,os,subprocess,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
for proc in Path('/proc').iterdir():
    if proc.name.isdigit():
        try:
            if b'/kit/kit' in (proc/'cmdline').read_bytes():raise RuntimeError('Another Kit is running; no duplicate or unrelated stop')
        except FileNotFoundError:pass
parser=argparse.ArgumentParser()
parser.add_argument('--profile',choices=['static','translation','rotation','mixed'],default='mixed')
parser.add_argument('--scene',choices=['scene18','room'],default='scene18')
parser.add_argument('--sync',choices=['default','zero_delay'],default='default')
parser.add_argument('--rig',choices=['mounted','usd_rig'],default='mounted')
parser.add_argument('--motion-history',choices=['default','off'],default='default')
parser.add_argument('--tlas',choices=['sensor','frame'],default='sensor')
args=parser.parse_args()
if args.motion_history=='off' and args.scene!='room':raise ValueError('Motion-history off comparison is implemented for the minimal room only')
if args.tlas=='frame' and args.scene!='room':raise ValueError('Frame-TLAS comparison is implemented for the minimal room only')
env=os.environ.copy();env.update(DISPLAY=':20',S0601_NATIVE_PROFILE=args.profile,S0601_NATIVE_SCENE=args.scene,S0601_RECOVERY_SYNC=args.sync,S0601_NATIVE_RIG=args.rig,S0601_NATIVE_MOTION_HISTORY=args.motion_history)
env.pop('S0601_FORCE_BARRIER',None)
env['S0601_NATIVE_TLAS']=args.tlas
stamp=time.strftime('%Y%m%d_%H%M%S')
log=root/'reports'/('native_launch_'+stamp+'.log')
with log.open('xb') as stream:
    proc=subprocess.Popen(['/usr/bin/python3','-B',str(root/'run_capture.py'),'--job',str(root/'config/mixed_pair.json'),'--native-probe'],cwd=root,env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
receipt={'pid':proc.pid,'log':str(log),'profile':args.profile,'scene_mode':args.scene,'sync':args.sync,'rig':args.rig,'motion_history':args.motion_history,'tlas':args.tlas,'entrypoint':str(root/'tools/probe_native_events.py'),'source_sha256':hashlib.sha256((root/'tools/probe_native_events.py').read_bytes()).hexdigest()}
(root/'reports/native_probe_process.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps(receipt))
