# -*- coding: utf-8 -*-
"""Post-capture evidence analysis. Reads decoded MCAP images; never re-renders."""
import collections,csv,hashlib,html,json,math,re,statistics,sys
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont

CAMERAS=('front','back','left','right')
LABELS={'01_v06_gated':'v06 gated RT2 16+2','02_v06_keepalive':'v06 keepalive RT2 16+2',
 '03_native_continuous_rt':'native continuous RT2','04_native_frozen_rt_diagnostic':'native frozen RT2 diagnostic',
 '05_native_frozen_rt_default':'native frozen RT2 default','06_native_frozen_pt_diagnostic':'native frozen PT diagnostic',
 '07_native_frozen_pt_default':'native frozen PT default','08_native_continuous_pt':'native continuous PT'}
def read(p,default=None):return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default
def lines(p):return [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines() if s.strip()] if p.exists() else []
def summary(values):
 v=[float(x) for x in values if x is not None and math.isfinite(float(x))]
 return dict(n=len(v),mean=statistics.mean(v),median=statistics.median(v),min=min(v),max=max(v),stdev=statistics.stdev(v) if len(v)>1 else None) if v else {'n':0}
def write(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
def csvout(p,rows,fields=None):
 fields=fields or list(dict.fromkeys(k for r in rows for k in r))
 with p.open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def fmt(v):return '—' if v is None else f'{v:.3f}'
def resource_samples(capture,legacy):
 source=capture/('system_resources.jsonl' if legacy else 'resources.jsonl');raw=lines(source);rows=[];prev={}
 for s in raw:
  t=s.get('host_monotonic_ns');gpu=s.get('gpu',{});kit=s.get('process' if legacy else 'kit',{}) or {};rec=s.get('recorder',{}) or {}
  row={'t':t,'gpu_percent':gpu.get('gpu_percent' if legacy else 'utilization.gpu'),
   'vram_gib':gpu.get('memory_used_bytes',0)/1024**3 if legacy else gpu.get('memory.used',0)/1024,
   'ram_gib':kit.get('rss_pages',0)*kit.get('page_size',4096)/1024**3 if legacy else kit.get('rss_bytes',0)/1024**3,
   'power_w':gpu.get('power.draw'),'memory_busy_percent':gpu.get('memory_busy_percent' if legacy else 'utilization.memory')}
  for name,p in (('kit_cpu_percent',kit),('recorder_cpu_percent',rec)):
   q=prev.get(name);row[name]=None;row[name+'_interval_begin']=q[0] if q else None
   if p and q and p.get('start_ticks')==q[1].get('start_ticks') and t>q[0]:
    dt=(t-q[0])/1e9;hz=p.get('clock_ticks_per_second',p.get('ticks_per_second',100))
    delta=p.get('user_ticks',0)+p.get('system_ticks',0)-q[1].get('user_ticks',0)-q[1].get('system_ticks',0)
    row[name]=100*delta/hz/dt
   if p:prev[name]=(t,p)
  rows.append(row)
 return rows
def in_scope(samples,begin,end):
 selected=[s for s in samples if begin<=s['t']<=end]
 valid_gpu=[s['gpu_percent'] for s in selected if s.get('gpu_percent') is not None]
 return {'samples':len(selected),'gpu_sample_fraction_at_most_5_percent':sum(x<=5 for x in valid_gpu)/len(valid_gpu) if valid_gpu else None,
  'gpu_sample_fraction_at_least_90_percent':sum(x>=90 for x in valid_gpu)/len(valid_gpu) if valid_gpu else None,
  **{k:summary([s.get(k) for s in selected if not k.endswith('cpu_percent') or s.get(k+'_interval_begin') is not None and s[k+'_interval_begin']>=begin]) for k in ('gpu_percent','kit_cpu_percent','recorder_cpu_percent','vram_gib','ram_gib','power_w','memory_busy_percent')}}
def warnings(capture):
 source=capture/'engine.log';counts=collections.Counter();examples=collections.defaultdict(list)
 for line in source.read_text(encoding='utf-8',errors='replace').splitlines() if source.exists() else []:
  m=re.search(r'\[(Warning|Error)\]\s*\[([^]]+)\]\s*(.*)',line)
  if not m:continue
  level,component,msg=m.groups();key=level+'/'+component;counts[key]+=1
  if len(examples[key])<3 and msg[:500] not in examples[key]:examples[key].append(msg[:500])
 normalized=collections.Counter()
 for line in source.read_text(encoding='utf-8',errors='replace').splitlines() if source.exists() else []:
  m=re.search(r'\[(Warning|Error)\]\s*\[([^]]+)\]\s*(.*)',line)
  if m:
   msg=re.sub(r'0x[0-9a-f]+','<address>',m.group(3));msg=re.sub(r'\b\d+\b','<n>',msg)
   normalized[m.group(1)+'/'+m.group(2)+': '+msg]+=1
 return {'source':'capture/engine.log','counts':dict(counts),'examples':dict(examples),'normalized_messages':dict(normalized),'limits':'Counts only this engine log; not a claim about whole-system warnings.'}
def case_stats(case,record):
 cfg=read(case/'config.json');capture=case/'capture';r=read(capture/'result.json',{});decoded=read(case/'decoded.json',{});legacy=cfg['family']=='v06';groups=[];stages=[]
 if legacy:
  events=[]
  for p in capture.glob('captures/runs/*/diagnostics/events_*.jsonl'):events.extend(lines(p))
  by=collections.defaultdict(list)
  for e in events:
   if e.get('event')=='span_end' and e.get('group_id') is not None:by[e['group_id']].append(e)
  for gid,ev in sorted(by.items()):
   begin=next((e['start_ns'] for e in ev if e.get('name')=='lab.SceneStepper.advance_clock'),None)
   acq=next((e for e in ev if e.get('name')=='lab.SensorDrivers.acquire'),None)
   if begin is None or acq is None:continue
   end=acq['start_ns']+acq['duration_ns'];warm=sum(e['duration_ns']/1e9 for e in ev if e.get('name')=='render_wait' and e.get('phase')=='warmup')
   formal=sum(e['duration_ns']/1e9 for e in ev if e.get('name')=='render_wait' and e.get('phase')=='capture')
   groups.append({'group':gid,'start_ns':begin,'end_ns':end,'payload_scope_s':(end-begin)/1e9,'sdk_warm_s':warm,'sdk_formal_s':formal,'sdk_render_s':warm+formal,'scope':'advance_clock through owned acquire; before worker write completion'})
   for e in ev:
    if e.get('name') in ('lab.SceneStepper.advance_clock','lab.SceneStepper.apply_snapshot','lab.SensorDrivers.warm_cameras','lab.SensorDrivers.acquire','lab.RecordPipeline.submit'):
     stages.append({'group':gid,'stage':e['name'],'start_ns':e['start_ns'],'end_ns':e['start_ns']+e['duration_ns'],'wall_s':e['duration_ns']/1e9})
 else:
  native=lines(capture/'groups.jsonl') or lines(capture/'frames.jsonl')
  for i,g in enumerate(native):
   begin=g['start_ns'];end=begin+round(g.get('payload_observed_scope_s',(g['end_ns']-begin)/1e9)*1e9)
   frozen='warm_s' in g
   row={'group':g.get('group',g.get('frame',i)),'start_ns':begin,'end_ns':end,
    'payload_scope_s':g.get('payload_observed_scope_s'),'sdk_warm_s':g.get('warm_s'),'sdk_formal_s':g.get('formal_s'),
    'sdk_render_s':g.get('warm_s',0)+g.get('formal_s',0) if frozen else None,'update_s':(g['end_ns']-begin)/1e9 if not frozen and 'payload_observed_scope_s' not in g else None,
    'advance_s':g.get('advance_s'),'evidence_s':g.get('evidence_s'),'native_frame_scheduled_s':g.get('native_frame_scheduled_s'),
    'capture_to_observation_s':g.get('capture_to_observation_s'),
    'scope':'prepare through hash observation' if frozen else 'native trigger through observation; intervals may overlap' if 'payload_observed_scope_s' in g else 'one native application update; no final-payload hash observer'}
   groups.append(row)
   if frozen:
    cursor=begin
    for name,key in (('advance','advance_s'),('warm','warm_s'),('formal','formal_s'),('evidence','evidence_s')):
     stop=cursor+round(g[key]*1e9);stages.append({'group':row['group'],'stage':name,'start_ns':cursor,'end_ns':stop,'wall_s':g[key]});cursor=stop
   else:stages.append({'group':row['group'],'stage':'native_continuous','start_ns':begin,'end_ns':end,'wall_s':(end-begin)/1e9})
 samples=resource_samples(capture,legacy);all_resources=in_scope(samples,groups[0]['start_ns'],groups[-1]['end_ns']) if groups else {'samples':0}
 for g in groups:
  g['id']=cfg['id'];g['round']=cfg['repeat']+1
  g['resources']=in_scope(samples,g['start_ns'],g['end_ns'])
 for s in stages:s['resources']=in_scope(samples,s['start_ns'],s['end_ns'])
 valid=decoded.get('all_expected_images_valid',False)
 errors=r.get('group_validation',{}).get('errors',[]) or r.get('validation',{}).get('errors',[])
 item={'id':cfg['id'],'round':cfg['repeat']+1,'label':LABELS[cfg['id']],'directory':str(case),'config':cfg,
  'valid':valid,'exit_code':record.get('exit_code'),'decode_exit':record.get('decode_exit'),
  'images':decoded.get('images',0),'valid_images':decoded.get('valid_images',0),'groups_observed':len(groups),
  'capture_window_s':r.get('capture',{}).get('wall_s'),'process_wall_s':r.get('process_wall_s'),'supervisor_wall_s':record.get('supervisor_wall_s'),
  'native_final_drain_s':r.get('capture',{}).get('native_final_drain_s'),
  'bag_bytes':decoded.get('bag_bytes'),'bag_path':decoded.get('bag_path'),'topics':decoded.get('topics',{}),
  'error_examples':errors[:12],'payload_scope_s':summary([g.get('payload_scope_s') for g in groups]),
  'sdk_render_s':summary([g.get('sdk_render_s') for g in groups]),'update_s':summary([g.get('update_s') for g in groups]),
  'resources':all_resources,'warnings':warnings(capture),'stage_stats_s':{name:summary([s['wall_s'] for s in stages if s['stage']==name]) for name in {s['stage'] for s in stages}},
  'preserved_root_usd':r.get('root_usd_unchanged',r.get('validation',{}).get('root_unchanged'))}
 write(case/'timing.json',{'case':item,'groups':groups,'stages':stages})
 flat=[]
 for g in groups:
  row={k:v for k,v in g.items() if k!='resources'}
  row.update(resource_samples=g['resources']['samples'],gpu_mean=g['resources']['gpu_percent'].get('mean'),kit_cpu_mean=g['resources']['kit_cpu_percent'].get('mean'),vram_peak_gib=g['resources']['vram_gib'].get('max'),ram_peak_gib=g['resources']['ram_gib'].get('max'));flat.append(row)
 csvout(case/'timing.csv',flat)
 phase_rows=[]
 for s in stages:
  res=s['resources'];phase_rows.append({'id':cfg['id'],'round':cfg['repeat']+1,**{k:v for k,v in s.items() if k!='resources'},'resource_samples':res['samples'],
   'gpu_mean_percent':res['gpu_percent'].get('mean'),'gpu_max_percent':res['gpu_percent'].get('max'),'kit_cpu_mean_percent':res['kit_cpu_percent'].get('mean'),'vram_peak_gib':res['vram_gib'].get('max'),'ram_peak_gib':res['ram_gib'].get('max')})
 csvout(case/'phase_timing.csv',phase_rows)
 return item,groups,stages
def pair_metrics(case,ref,output):
 a=read(case/'frame_metadata.json',{});b=read(ref/'frame_metadata.json',{});ar=list(csv.DictReader((case/'frames.csv').open()));br={ (v['group'],v['camera']):v for v in csv.DictReader((ref/'frames.csv').open())};rows=[]
 for x in ar:
  y=br.get((x['group'],x['camera']));key=x['group']+'/'+x['camera']
  if y is None:continue
  am=a.get(key,{});bm=b.get(key,{});ap=am.get('optical_world_matrix');bp=bm.get('optical_world_matrix');ac=am.get('camera_info');bc=bm.get('camera_info')
  pose_err=float(np.max(np.abs(np.asarray(ap)-np.asarray(bp)))) if ap is not None and bp is not None else None
  calibration_match=ac is not None and bc is not None and all(ac.get(k)==bc.get(k) for k in ('width','height','model','k','d'))
  joint_match=am.get('joints_rad') is not None and bm.get('joints_rad') is not None and set(am['joints_rad'])==set(bm['joints_rad']) and max(abs(am['joints_rad'][k]-bm['joints_rad'][k]) for k in am['joints_rad'])<=1e-6
  eligible=x['valid']=='True' and y['valid']=='True' and pose_err is not None and pose_err<=2e-3 and calibration_match and joint_match
  row={'id':case.parent.name,'round':int(case.name[-2:]),'group':int(x['group']),'camera':x['camera'],'reference':ref.parent.name,'eligible':eligible,'pose_matrix_max_abs_error':pose_err,'calibration_match':calibration_match,'joint_match':joint_match,'mae_rgb':None,'psnr_db':None,'mse_rgb':None,'mean_rgb':float(x['rgb_mean']),'reference_mean_rgb':float(y['rgb_mean'])}
  if eligible:
   rgb=np.asarray(Image.open(case/x['image']).convert('RGB'),dtype=np.float32);reference=np.asarray(Image.open(ref/y['image']).convert('RGB'),dtype=np.float32)
   d=rgb-reference;mse=float(np.mean(d*d));row.update(mae_rgb=float(np.mean(np.abs(d))),mse_rgb=mse,psnr_db=10*math.log10(255**2/mse) if mse>0 else None,pixel_identical=mse==0)
   if row['group']==1:
    p=output/'differences'/case.name/x['camera']/(case.parent.name+'.png');p.parent.mkdir(parents=True,exist_ok=True)
    Image.fromarray(np.clip(np.abs(d)*4,0,255).astype('uint8')).save(p)
  rows.append(row)
 return rows
def image_index(case):return {(int(v['group']),v['camera']):v for v in csv.DictReader((case/'frames.csv').open())} if (case/'frames.csv').exists() else {}
def static_stability(case):
 index=image_index(case);rows=[]
 for camera in CAMERAS:
  selected=sorted((g,v) for (g,c),v in index.items() if c==camera and v['valid']=='True')
  if len(selected)<2:continue
  first=np.asarray(Image.open(case/selected[0][1]['image']).convert('RGB'),dtype=np.float32)
  last=np.asarray(Image.open(case/selected[-1][1]['image']).convert('RGB'),dtype=np.float32)
  rows.append({'id':case.parent.name,'round':int(case.name[-2:]),'camera':camera,'first_group':selected[0][0],'last_group':selected[-1][0],
   'first_to_last_mae_rgb':float(np.mean(np.abs(first-last))),'first_mean_rgb':float(first.mean()),'last_mean_rgb':float(last.mean()),
   'limits':'Static-pose temporal variation; not a direct test of asset-loader completion.'})
 return rows
def visualizations(root,cases,out):
 try:font=ImageFont.truetype('DejaVuSans.ttf',16)
 except OSError:font=ImageFont.load_default()
 paths=[];crop_paths=[]
 for repeat in sorted({c['round'] for c in cases}):
  members={c['id']:Path(c['directory']) for c in cases if c['round']==repeat};ids=list(LABELS)
  sheet=Image.new('RGB',(len(ids)*480,4*320),(18,22,28));draw=ImageDraw.Draw(sheet)
  for col,cid in enumerate(ids):
   case=members.get(cid);index=image_index(case) if case else {}
   for row,camera in enumerate(CAMERAS):
    info=index.get((1,camera));left=col*480;top=row*320
    draw.text((left+8,top+5),f'{cid[:2]} {camera} | round {repeat} | group 1',font=font,fill='white')
    draw.text((left+8,top+27),LABELS[cid].removeprefix('native '),font=font,fill='#aebbd0')
    if info:
     im=Image.open(case/info['image']).convert('RGB');im.thumbnail((480,270),Image.Resampling.LANCZOS);sheet.paste(im,(left,top+50))
     if info['valid']!='True':draw.rectangle((left,top+50,left+478,top+319),outline='#ff5757',width=4);draw.text((left+9,top+56),'DIAGNOSTIC / invalid capture',font=font,fill='#ff5757')
    else:draw.text((left+10,top+145),'No matching MCAP image',font=font,fill='#ff5757')
  path=out/f'contact_round_{repeat:02d}.png';sheet.save(path);paths.append(path.name)
  for roi_name,box in (('front_ground',(640,560,1120,830)),('front_machine',(1000,200,1480,470))):
   sheet=Image.new('RGB',(len(ids)*480,330),(18,22,28));draw=ImageDraw.Draw(sheet)
   for col,cid in enumerate(ids):
    case=members.get(cid);info=image_index(case).get((1,'front')) if case else None;left=col*480
    draw.text((left+8,6),f'{cid[:2]} | round {repeat} | group 1 | original pixels',font=font,fill='white')
    draw.text((left+8,28),roi_name+' '+str(box),font=font,fill='#aebbd0')
    if info:
     crop=Image.open(case/info['image']).convert('RGB').crop(box);sheet.paste(crop,(left,60))
     if info['valid']!='True':draw.rectangle((left,60,left+479,329),outline='#ff5757',width=4)
   path=out/f'crop_{roi_name}_round_{repeat:02d}.png';sheet.save(path);crop_paths.append(path.name)
 cards=[]
 for c in cases:
  case=Path(c['directory']);index=image_index(case);links=[]
  for camera in CAMERAS:
   info=index.get((1,camera))
   if info:
    rel=(case/info['image']).relative_to(root).as_posix();src='../'+rel
    links.append(f'<figure><a href="{html.escape(src)}"><img loading="lazy" src="{html.escape(src)}"></a><figcaption>{camera} · group 1 · valid={info["valid"]}</figcaption></figure>')
  cards.append(f'<section><h2>{html.escape(c["label"])} · round {c["round"]}</h2><p>capture valid={c["valid"]}; selected PNG={c["images"]}; bag={c["bag_bytes"]} bytes</p><div>{"".join(links)}</div></section>')
 markup='<!doctype html><meta charset="utf-8"><title>NC-004 MCAP image comparison</title><style>body{background:#10151e;color:#e6edf7;font:16px system-ui;max-width:1800px;margin:28px auto}section{margin:28px 0;padding:18px;background:#1c2533}div{display:flex;flex-wrap:wrap}figure{margin:8px;width:calc(25% - 16px)}img{width:100%}a{color:#93c5fd}h2{font-size:20px}figcaption{font-size:14px}</style><h1>NC-004 · actual MCAP images</h1><p>Click any preview for its original 1920×1080 PNG. Red diagnostic results are excluded from valid speed and image-quality comparisons. Difference images are absolute RGB differences multiplied by 4, not original images.</p>'+''.join(f'<p><a href="{p}">Image comparison {p}</a></p>' for p in paths+crop_paths)+''.join(cards)
 (out/'gallery.html').write_text(markup,encoding='utf-8');return paths
def analyze(root):
 root=Path(root);out=root/'analysis';out.mkdir(exist_ok=True);p=read(root/'progress.json');cases=[];allgroups=[]
 for record in p['completed_cases']:
  case=root/record['id']/f'round_{record["round"]:02d}'
  if not (case/'decoded.json').exists():continue
  item,groups,stages=case_stats(case,record);cases.append(item);allgroups.extend(groups)
 pairs=[]
 for c in cases:
  case=Path(c['directory']);ref=root/'05_native_frozen_rt_default'/case.name
  if (ref/'frames.csv').exists():pairs.extend(pair_metrics(case,ref,out))
 comparison=[]
 for c in cases:
  n=c['groups_observed'];res=c['resources'];comparison.append({'id':c['id'],'round':c['round'],'capture_valid':c['valid'],'groups_observed':n,'images':c['images'],'valid_images':c['valid_images'],'window_s':c['capture_window_s'],'window_per_requested_group_s':c['capture_window_s']/6 if c['capture_window_s'] is not None else None,'payload_median_s':c['payload_scope_s'].get('median'),'sdk_render_median_s':c['sdk_render_s'].get('median'),'app_update_median_s':c['update_s'].get('median'),'process_wall_s':c['process_wall_s'],'supervisor_wall_s':c['supervisor_wall_s'],'bag_bytes':c['bag_bytes'],'resource_samples':res['samples'],'gpu_mean_percent':res.get('gpu_percent',{}).get('mean'),'gpu_max_percent':res.get('gpu_percent',{}).get('max'),'kit_cpu_mean_percent':res.get('kit_cpu_percent',{}).get('mean'),'vram_max_gib':res.get('vram_gib',{}).get('max'),'ram_max_gib':res.get('ram_gib',{}).get('max'),'native_final_drain_s':c['native_final_drain_s']})
 stability=[v for c in cases for v in static_stability(Path(c['directory']))];csvout(out/'static_stability.csv',stability)
 aggregates=[]
 for cid in LABELS:
  cc=[c for c in cases if c['id']==cid];gg=[g for g in allgroups if g['id']==cid];valid=[c for c in cc if c['valid']]
  aggregates.append({'id':cid,'label':LABELS[cid],'attempted_rounds':len(cc),'valid_rounds':len(valid),'images':sum(c['images'] for c in cc),'valid_images':sum(c['valid_images'] for c in cc),'window_s':summary([c['capture_window_s'] for c in cc]),'valid_window_s':summary([c['capture_window_s'] for c in valid]),'payload_s':summary([g.get('payload_scope_s') for g in gg]),'first_payload_s':summary([g.get('payload_scope_s') for g in gg if g['group']==0]),'subsequent_payload_s':summary([g.get('payload_scope_s') for g in gg if g['group']>0]),'sdk_render_s':summary([g.get('sdk_render_s') for g in gg]),'update_s':summary([g.get('update_s') for g in gg]),'bag_bytes':summary([c['bag_bytes'] for c in cc]),'gpu_mean_percent':summary([c['resources'].get('gpu_percent',{}).get('mean') for c in cc])})
 common=read(out/'common_inputs.json')
 result={'suite_state':p['state'],'completed_cases':len(p['completed_cases']),'analyzed_cases':len(cases),'planned_cases':p['planned_cases'],'cases':cases,'aggregates':aggregates,'alignment_and_image_metrics':pairs,'static_stability':stability,'common_inputs_alignment':common,'analyzer_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
 write(out/'comparison.json',result);csvout(out/'comparison.csv',comparison);csvout(out/'image_metrics.csv',pairs)
 sheets=visualizations(root,cases,out)
 report=['# NC-004 八种采集配置统一复跑报告','',f'套件状态：**{p["state"]}**；完成 {len(p["completed_cases"])} / {p["planned_cases"]} 项，已分析 {len(cases)} 项。图片全部由实际 MCAP 解码，采集时没有额外 RGB PNG 输出。','',f'有效运行 {sum(c["valid"] for c in cases)} 项；目标图像已导出 {sum(c["images"] for c in cases)} 张，其中有效图像 {sum(c["valid_images"] for c in cases)} 张。','',
 '## 配置聚合','', '| 配置 | 有效轮/已分析轮 | capture 窗口中位数 s | 每组完整观察范围中位数 s | SDK 渲染范围中位数 s | 应用更新中位数 s |', '|---|---:|---:|---:|---:|---:|']
 for a in aggregates:report.append(f'| {a["label"]} | {a["valid_rounds"]}/{a["attempted_rounds"]} | {fmt(a["window_s"].get("median"))} | {fmt(a["payload_s"].get("median"))} | {fmt(a["sdk_render_s"].get("median"))} | {fmt(a["update_s"].get("median"))} |')
 report+=['','窗口为各链路自己的 capture 边界，见下面限制。失败配置的时间只表示诊断成本，不能参与有效吞吐排名。24 次运行分三轮独立进程；每轮六组。三轮统计样本较少，组内 18 个样本不是 18 次独立启动。','',
 '## 首组与后续组','', '| 配置 | 首组完整观察范围中位数 s | 后续组中位数 s |', '|---|---:|---:|']
 for a in aggregates:report.append(f'| {a["label"]} | {fmt(a["first_payload_s"].get("median"))} | {fmt(a["subsequent_payload_s"].get("median"))} |')
 report+=['', '组间变化可能包括初始化、资源准备和时间累积历史。这里只陈述测量，不把全部差额归为某个未经本轮底层跟踪的驱动调用。','',
 '## 逐轮耗时与资源','', '| 配置/轮 | 有效 | capture s | 整进程 s | GPU 均值 % | GPU 峰值 % | Kit CPU 均值 % | 显存峰值 GiB | Kit RSS 峰值 GiB | 样本数 |', '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
 for c in comparison:report.append(f'| {c["id"]}/{c["round"]} | {c["capture_valid"]} | {fmt(c["window_s"])} | {fmt(c["process_wall_s"])} | {fmt(c["gpu_mean_percent"])} | {fmt(c["gpu_max_percent"])} | {fmt(c["kit_cpu_mean_percent"])} | {fmt(c["vram_max_gib"])} | {fmt(c["ram_max_gib"])} | {c["resource_samples"]} |')
 report+=['','GPU/RAM 范围是首目标组开始到最后目标组观察结束。约 1 Hz 样本存在覆盖和边界误差；CPU 是累计 ticks 差分、100% 表示一个核，只统计差分区间完全落在目标范围的样本。GPU 为全卡 busy，不是 SM occupancy。显存为全设备，RSS 仅 Kit；ROS recorder/独立编码进程不能据此说成整机 CPU。','',
 '## 同姿态图像与对齐','',f'以每轮 05 原生冻结 RT2 默认 Helper 的同组同方向图片为参考；正式比较 {sum(x["eligible"] for x in pairs)} 对，排除 {sum(not x["eligible"] for x in pairs)} 对。相机内参逐项匹配，光学 TF 世界矩阵容差 2e-3，关节弧度容差 1e-6。具体最大误差见 image_metrics.csv。','',
 '[打开本地图片索引](gallery.html)。点击缩略图查看原始 1920×1080 PNG。','']
 report += [f'![第 {i+1} 轮四方向对照]({name})' for i,name in enumerate(sheets)]
 report+=['','局部原像素对照（打开原图按 100% 缩放查看；没有锐化或插值）：','']+[f'- [{p.name}]({p.name})' for p in sorted(out.glob('crop_*.png'))]
 if common:
  report+=['',f'全部传感器公共输入核对：有效采集的 17 路传感器世界变换及双方清单共同列出的雷达参数对齐结果为 **{common["all_valid_captures_input_aligned"]}**。逐组误差、缺失项和参数差异见 common_inputs.json。失败采集的输入姿态相同不代表录包对齐合格。','']
 report += ['','image_metrics.csv 包含 RGB MAE、MSE、PSNR 和亮度。它们是相对参考图的差异指标，不是绝对画质或物理准确度；完全相同图像的 PSNR 记空并用 pixel_identical=True 标注。差分图仅为绝对 RGB 差乘 4 的可视化。不同渲染器、不同时间累积历史不能当成同一种算法的误差收敛实验。','',
 '| 配置 | 有效图像对数 | RGB MAE 均值 | 图像平均亮度 |', '|---|---:|---:|---:|']
 for cid in LABELS:
  selected=[v for v in pairs if v['id']==cid and v['eligible']]
  report.append(f'| {LABELS[cid]} | {len(selected)} | {fmt(summary([x["mae_rgb"] for x in selected]).get("mean"))} | {fmt(summary([x["mean_rgb"] for x in selected]).get("mean"))} |')
 report+=['', 'static_stability.csv 另外记录各配置各方向首组至末组的像素变化。稳定或不稳定本身都不能单独证明 3DGS 加载完成与否。','',
 '## 失败与 warning','']
 for c in cases:
  report += [f'### {c["id"]} / round {c["round"]}', '',f'录包有效：{c["valid"]}；退出码 {c["exit_code"]}；解码退出码 {c["decode_exit"]}。', '', '```json',json.dumps({'validation_error_examples':c['error_examples'],'engine_warning_error_counts':c['warnings']['counts']},ensure_ascii=False,indent=2),'```','']
 report += ['## 比较边界与结论使用规则','',
 '`frames.csv` 中历史字段名 `bag_receive_stamp_ns` 实际是 `SequentialReader.read_next()` 返回的包内记录时间；不是另行测量的网络接收墙钟。启用仿真时钟录包时不可当成 Unix 墙钟，不用它推算网络延迟。',
 '相同组号表示同一静止输入姿态，不表示相同绝对仿真时间。连续 RT2 普通更新间隔约 1/60 秒，冻结链路目标间隔约 0.1 秒，初始化时钟起点也不同。原始时间不作平移或重写。','',
 '1. v06 为 single06_lab/frozen_runtime 保留基线。01 与 02 固定 RT2 16＋2，仅资源生命周期改变；可用于评估常驻的实际收益。v06 写 PNG CompressedImage，原生写 Image，额外元数据话题不同。','2. 04 与 05、06 与 07 分别主要对照诊断门控与默认 Helper，诊断配置显式改接了执行边，不能称为未修改的原生 Helper。重复发布量和录包成本见 decoded.json/topics。','3. 03 原生连续 RT2 不做逐组 16＋2，只有普通逐帧更新，其速度与图像只能作为不同预算对照；不能据此宣布相同画质快多少倍。','4. 冻结组完整观察范围分别为 v06 从时钟推进到持有数据完成、原生从准备到 RGB/XYZ 哈希观察完成；持有和校验成本并不完全相同。SDK 范围是调用与等待，不是纯 GPU 时间。','5. v06 capture 窗口包含 worker 写入尾部；原生窗口不包含最终 SDK 排空与 recorder 关闭。整进程和控制器含校验总耗时另列，PNG 解码在这些计时之后。','6. 连续 PT 原生调度各组触发到观察的范围可能重叠，不能相加替代 scenario 时间。SPP 表示预算及 SDK 子帧完成证据，不是实际硬件射线计数。对齐失败时只输出诊断图片，不修改 ROS 时间戳，不进入有效排名。','7. 本轮全为静止姿态，未证明运动/安装改变条件下的对齐，也未重跑全部子帧/SPP 预算矩阵。LiDAR 参数相同不代表有相同噪声随机种子或逐点相同结果。','8. warning/error 分类计数是定位证据；数值校验通过不代表所有警告均无影响。源日志保留，进一步分析具体组件才能判断影响。','9. 保留源代码清单、根场景校验、运行配置、进程日志、解码器/分析器哈希与传输清单。实验未修改旧源码、磁盘 USD 或系统依赖。','',
 '## 数据目录','', '每个配置/round_XX：config.json、input_spec.json、capture/（远端 MCAP 与原始日志）、decoded.json、frames.csv、frame_metadata.json、timing.csv/json、images/<方向>/ 或 diagnostic_images/<方向>/。','', 'analysis/：comparison.csv/json、image_metrics.csv、contact_round_XX.png、differences/、gallery.html、本报告。MCAP 保留在远端，实际路径见每项 decoded.json/bag_path。']
 (out/'NC-004_report.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
 print(json.dumps({'suite_state':p['state'],'analyzed':len(cases),'valid_cases':sum(c['valid'] for c in cases),'images':sum(c['images'] for c in cases),'valid_images':sum(c['valid_images'] for c in cases),'eligible_image_pairs':sum(x['eligible'] for x in pairs),'output':str(out)}))
if __name__=='__main__':analyze(sys.argv[1])
