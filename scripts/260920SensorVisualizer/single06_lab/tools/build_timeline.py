"""Self-contained metric timeline, no CDN / plotting dependencies required."""
import argparse,json,sqlite3,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from lab.analysis import align_anchors
p=argparse.ArgumentParser();p.add_argument('directory');a=p.parse_args();directory=Path(a.directory)
db=sqlite3.connect(directory/'native.sqlite');db.row_factory=sqlite3.Row
nvtx=[dict(r) for r in db.execute('SELECT n.start,n.end,COALESCE(n.text,s.value) label FROM NVTX_EVENTS n LEFT JOIN StringIds s ON s.id=n.textId')]
window=next(r for r in nvtx if r['label']=='SL06_WINDOW' and r['end']);start,end=window['start'],window['end']
catalog=[dict(r) for r in db.execute('SELECT * FROM TARGET_INFO_GPU_METRICS')]
chosen=['SMs Active [Throughput %]','SM Issue [Throughput %]','Tensor Active [Throughput %]',
        'GR Active [Throughput %]','DRAM Read Bandwidth [Throughput %]','DRAM Write Bandwidth [Throughput %]',
        'PCIe RX Throughput [Throughput %]','PCIe TX Throughput [Throughput %]',
        'SM Throughput [Throughput %]','RTCORE Throughput [Throughput %]',
        'VRAM Throughput [Throughput %]','L1 Throughput [Throughput %]','L2 Throughput [Throughput %]',
        'PCIe Throughput [Throughput %]','Compute Warps [Throughput %]',
        'Unallocated Warps in Active SMs [Throughput %]','Idle SM Unused Warp Slots [Throughput %]']
series=[]
for name in chosen:
    metric=next((r for r in catalog if r['metricName']==name),None)
    if metric is None:continue
    samples=[[(r[0]-start)/1e9,r[1]] for r in db.execute('SELECT timestamp,value FROM GPU_METRICS WHERE typeId=? AND metricId=? AND timestamp BETWEEN ? AND ? ORDER BY timestamp',
        (metric['typeId'],metric['metricId'],start,end))]
    # 10 ms buckets retain mean and max; raw 1 kHz samples remain in SQLite.
    buckets={}
    for t,v in samples:buckets.setdefault(int(t*100),[]).append(v)
    series.append({'name':name,'data':[[b/100,sum(v)/len(v),max(v)] for b,v in sorted(buckets.items())]})
ranges=[{'name':r['label'].split(' g=')[0],'start':max(0,(r['start']-start)/1e9),
         'end':min((end-start)/1e9,(r['end']-start)/1e9)} for r in nvtx if r['end'] and r['start']<end and r['end']>start
          and (r['label'] or '').startswith(('SV06 render_wait ','SV06 lab.SensorDrivers.warm_cameras ','SV06 lab.SensorDrivers.acquire '))]
data={'duration':(end-start)/1e9,'series':series,'ranges':ranges}
template='''<!doctype html><meta charset="utf-8"><title>single06 native timeline</title>
<style>body{font:15px system-ui;background:#131923;color:#e1e9f7;margin:24px}canvas{width:100%;background:#1c2533;margin:10px 0;border-radius:8px}p{max-width:1000px;line-height:1.6}#tip{position:fixed;right:25px;top:20px;background:#30465b;padding:12px;white-space:pre-line;pointer-events:none}</style>
<h1>single06 原生设备指标时间线</h1><p>包含追踪开销的短窗口。实线为 10 ms 桶平均，浅线为桶内最大值；原始样本保留在 SQLite，通用窗口 1 kHz，图形窗口 10 kHz。指标覆盖整张 GPU，不能直接归给一个进程。SM Active、SM Issue、Tensor Active 含义不同，不能相加；图形集的 RTCORE Throughput 是计数器导出的吞吐指标，不是逐个 RT Core 的忙闲状态。</p><div id="plots"></div><div id="tip">在图上移动鼠标读取数据</div>
<script>const data=DATA;const holder=document.querySelector('#plots');
function plot(title,values,ranges=false){let h=document.createElement('div');h.textContent=title;holder.append(h);let c=document.createElement('canvas');c.width=1600;c.height=ranges?values.length*38+65:220;holder.append(c);let g=c.getContext('2d'),left=65,right=1560,w=right-left;
function X(t){return left+t/data.duration*w}g.font='15px system-ui';g.strokeStyle='#3a465b';g.fillStyle='#a9b8cb';
for(let i=0;i<=10;i++){let x=left+i*w/10;g.beginPath();g.moveTo(x,15);g.lineTo(x,c.height-35);g.stroke();g.fillText((data.duration*i/10).toFixed(2)+'s',x-15,c.height-10)}
if(ranges){values.forEach((r,i)=>{let y=22+i*38;g.fillStyle=i%2?'#6ba6da':'#68bea3';g.fillRect(X(r.start),y,X(r.end)-X(r.start),23);g.fillStyle='#e1e9f7';g.fillText(r.name,Math.min(X(r.start)+5,right-280),y+16)})}
else{for(let i=0;i<=4;i++)g.fillText(100-i*25+'%',3,22+i*40);for(let col of [2,1]){g.strokeStyle=col==2?'#50657c':'#7bddbd';g.beginPath();values.forEach((p,i)=>{let x=X(p[0]),y=175-p[col]*1.5;if(i)g.lineTo(x,y);else g.moveTo(x,y)});g.stroke()}}
c.onmousemove=e=>{let t=Math.max(0,Math.min(data.duration,((e.clientX-c.getBoundingClientRect().left)/c.getBoundingClientRect().width*c.width-left)/w*data.duration));let s=title+'\\n'+t.toFixed(3)+' 秒';if(!ranges&&values.length){let p=values.reduce((a,b)=>Math.abs(a[0]-t)<Math.abs(b[0]-t)?a:b);s+='\\n桶平均 '+p[1].toFixed(2)+'%\\n桶最大 '+p[2]+'%'}document.querySelector('#tip').textContent=s}}
plot('SDK 包含性阶段范围',data.ranges,true);for(let s of data.series)plot(s.name,s.data);
</script>'''
output=directory/'timeline.html';output.write_text(template.replace('DATA',json.dumps(data)),encoding='utf-8')
db.close();print(output)
