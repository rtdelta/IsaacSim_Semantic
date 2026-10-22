import json,os,subprocess,urllib.request
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/261013Rviz2Viewer')
latest=json.loads((root/'reports/latest_capture.json').read_text());capture=Path(latest['directory'])/'capture';result=json.loads((capture/'result.json').read_text());session=Path(result['capture']['session'])
env=os.environ.copy();env['DISPLAY']=':20'
result={}
for args in [['xwininfo','-root','-tree'],['xprop','-root','_NET_CURRENT_DESKTOP','_NET_ACTIVE_WINDOW'],['xwininfo','-id','0x2a00072'],['xprop','-id','0x2a00072','WM_STATE','_NET_WM_DESKTOP','_NET_WM_PID']]:
    p=subprocess.run(args,env=env,capture_output=True,text=True,timeout=10);result[str(args)]=p.stdout[-10000:]+p.stderr
result['status']=json.load(urllib.request.urlopen('http://127.0.0.1:8767/api/status',timeout=5))
logs=sorted((session/'viewer_logs').glob('*/rviz.log'));result['rviz_log']=logs[-1].read_text()[-4000:]
events=[json.loads(x) for x in (logs[-1].parent/'playback_events.jsonl').read_text().splitlines()]
play=[i for i,e in enumerate(events) if e['event']=='command' and e['command']['action']=='play']
if play:
    section=events[play[-1]+1:];groups=[e for e in section if e['event']=='group_started'];completed=[e for e in section if e['event']=='group_complete']
    intervals=[(b['monotonic_ns']-a['monotonic_ns'])/1e6 for a,b in zip(groups,groups[1:])]
    def quantile(values,p):
        v=sorted(values);n=(len(v)-1)*p;i=int(n);return v[i]+(v[min(i+1,len(v)-1)]-v[i])*(n-i) if v else None
    result['benchmark']={'played_groups':len(groups),'completed_groups':len(completed),'last_group':completed[-1]['group'] if completed else None,'interval_median_ms':quantile(intervals,.5),'interval_p95_ms':quantile(intervals,.95),'interval_max_ms':max(intervals) if intervals else None,'send_duration_median_ms':quantile([e['duration_ns']/1e6 for e in completed],.5),'late_p95_ms':quantile([e['late_ns']/1e6 for e in groups],.95),'rviz_enabled_lidars':1,'scope':'Publisher starts with real RViz open; RViz display completion is not measured','event_log':str(logs[-1].parent/'playback_events.jsonl')}
    (root/'reports/gui_benchmark.json').write_text(json.dumps(result['benchmark'],indent=2))
print(json.dumps(result))
