# -*- coding: utf-8 -*-
"""Turn the final measured evidence into a short, reproducible Chinese report."""
import csv,hashlib,json,os,statistics,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def fmt(v):return '—' if v is None else f'{v:.3f}'
def med(v):return statistics.median(v) if v else None
def run(out,report_target=None):
 out=Path(out);data=load(out/'analysis/comparison.json')
 if data['suite_state']!='completed' or data['analyzed_cases']!=data['planned_cases']:
  raise RuntimeError('A final report requires the completed suite and all case analyses')
 integrity=load(out/'final_integrity.json');common=load(out/'analysis/common_inputs.json');ranges=load(out/'analysis/lidar_ranges.json')
 aa={a['id']:a for a in data['aggregates']};cc=data['cases'];by={(c['id'],c['round']):c for c in cc}
 target=Path(report_target) if report_target else ROOT/'docs/NC-004_execution_report.md'
 links=Path(os.path.relpath(out/'analysis',target.parent)).as_posix()+'/'
 valid=sum(c['valid'] for c in cc);images=sum(c['images'] for c in cc);valid_images=sum(c['valid_images'] for c in cc)
 a,b=aa['01_v06_gated'],aa['02_v06_keepalive'];gated=a['payload_s']['median'];kept=b['payload_s']['median']
 reduction=(1-kept/gated)*100
 paired=[(1-by[('02_v06_keepalive',n)]['capture_window_s']/by[('01_v06_gated',n)]['capture_window_s'])*100 for n in (1,2,3)]
 report=['# NC-004 执行结果与分析','', '日期：2026-10-12。实验：`'+out.name+'`。', '',
  '环境来自本轮 engine.log：单卡 NVIDIA L40，驱动 580.126.09，Vulkan；Isaac Sim 6.0.1-rc.7，Ubuntu 24.04.4。引擎报告 CPU 为 Xeon Platinum 8358、容器 Core Usage Quota=14，内存 122880 MB；宿主机逻辑核数不等于容器可用核数。四路 1920×1080 鱼眼、13 路 Instant LiDAR，固定 combine_scene_16_terrain_fisheye.usda，视口更新关闭。本轮测量离线采集，不是操作面板响应延迟。','',
  f'已完成 **24/24 次独立运行**：8 种配置 × 3 轮 × 6 个目标组。**{valid} 次录包通过，{24-valid} 次未通过**。从实际 MCAP 导出 **{images} 张 PNG**，其中 {valid_images} 张有效、{images-valid_images} 张诊断图片。目标总数为 576；缺失图片不补渲染、不伪造。','',
  f'[完整统计报告]({links}NC-004_report.md) · [图片浏览器]({links}gallery.html) · [逐轮 CSV]({links}comparison.csv) · [逐图指标]({links}image_metrics.csv)','',
  '## 最重要的结果','',
  f'1. **首先保留传感器资源常驻。**相同 v06 基线、RT2 16＋2 子帧下，整组观察范围中位数从 {gated:.3f} 秒降至 {kept:.3f} 秒，缩短 {reduction:.1f}%。三轮 capture 窗口分别缩短 '+ '、'.join(f'{x:.1f}%' for x in paired)+'。这是本轮最直接的同框架变量对照。','',
  '2. **默认 Helper 足以完成本轮冻结采集。**原生冻结 RT2 与 PT 的默认/诊断门控均通过；本场景静止条件下，没有证据支持必须改接 Helper 执行边。耗时差异需看三轮范围，不能以一次小差值认定显著优势。','',
  '3. **原生连续 RT2 很快，但工作量不同。**它没有逐组 16＋2 预热/正式子帧，也没有冻结组的完整载荷哈希观察范围。这里只能作为低等待、不同累积预算的对照，不能宣布同画质几十倍提速。','',
  '4. **高采样 PT 主要在持续计算。**1024 目标 SPP 的冻结 PT 明显增加耗时，GPU busy 长时间保持高位。提高利用率不等于提高有效数据产出速度。','',
  '5. **原生连续 PT 仍不能作为合格交付链路。**原生调度/预算检查和最终 MCAP 对齐是两件事。其失败结果保留为诊断证据，未修改消息时间或放宽容差使其通过。','',
  '## 一组与一轮分别用了多久','',
  '| 配置 | 通过轮次 | 一组观察/更新中位数 s | 首组 s | 后续组 s | 6 组 capture 窗口中位数 s |',
  '|---|---:|---:|---:|---:|---:|']
 for x in data['aggregates']:
  primary=x['payload_s'].get('median',x['update_s'].get('median'))
  report.append(f'| {x["label"]} | {x["valid_rounds"]}/3 | {fmt(primary)} | {fmt(x["first_payload_s"].get("median"))} | {fmt(x["subsequent_payload_s"].get("median"))} | {fmt(x["window_s"].get("median"))} |')
 report+=['','v06 的观察范围为推进时钟开始至独立载荷持有完成；原生冻结为准备开始至 RGB/XYZ 哈希观察完成，两者数据持有和校验成本不同。连续 RT2 列的是单次应用更新；连续 PT 范围可能交叠且录包失败，其数字只表示诊断成本。窗口不包含相同的尾部工作，因此另保存进程总耗时，详见完整报告。','',
  '每项只有三次独立进程运行；18 个组内样本不是 18 次独立实验。静止测试的初始化、时域累积及资源历史会影响首组和后续组，不能忽略首组成本。','',
  '## 时间消耗落在哪些阶段','',
  '| 配置 | 阶段 | 阶段墙钟中位数 s | 阶段内 GPU busy 样本均值 % | Kit CPU 样本均值 % |',
  '|---|---|---:|---:|---:|']
 for cid in ('01_v06_gated','02_v06_keepalive','05_native_frozen_rt_default','07_native_frozen_pt_default'):
  stages=[]
  for n in (1,2,3):stages+=load(out/cid/f'round_{n:02d}'/'timing.json')['stages']
  names=('lab.SceneStepper.advance_clock','lab.SceneStepper.apply_snapshot','lab.SensorDrivers.warm_cameras','lab.SensorDrivers.acquire','lab.RecordPipeline.submit') if cid.startswith(('01','02')) else ('advance','warm','formal','evidence')
  for name in names:
   selected=[s for s in stages if s['stage']==name]
   def weighted(key):
    v=[s['resources'][key] for s in selected if s['resources'][key].get('n',0)]
    return sum(x['mean']*x['n'] for x in v)/sum(x['n'] for x in v) if v else None
   report.append(f'| {cid} | {name} | {fmt(med([s["wall_s"] for s in selected]))} | {fmt(weighted("gpu_percent"))} | {fmt(weighted("kit_cpu_percent"))} |')
 report+=['','上表为不同链路自身的阶段，名称相似不保证内部工作相同。GPU 是约 1 Hz 的整卡 busy 样本，不是 CUDA/RT/Tensor Core 利用率；CPU 100% 表示一个核，只统计差分区间完整落在阶段内的样本。短阶段无可靠 CPU 样本时留空，不推断为零。','',
  'v06 常驻的主要收益出现在预热范围；首组仍承担初始化，而后续组缩短。常驻也会让推进阶段发生额外渲染，故个别阶段变慢不矛盾。本轮对照支持资源启停影响总耗时，但没有新增驱动调用栈或 GPU 指令级跟踪，不能把所有节省时间都断言成模块卸载/重载。','',
  '冻结 PT 的 advance 阶段也有明显 GPU 工作，准备步骤包含引擎更新，不能把整个 advance 都叫作 CPU 更新变换。SDK step 的完成范围也不是纯 GPU kernel 时间。','',
  '## 资源占用与间歇问题','',
  '| 配置 | 三轮 GPU 均值范围 % | GPU≤5% 的样本比例范围 | GPU≥90% 的样本比例范围 | 显存峰值 GiB | Kit RSS 峰值 GiB |',
  '|---|---:|---:|---:|---:|---:|']
 for cid in aa:
  selected=[c for c in cc if c['id']==cid];rs=[c['resources'] for c in selected]
  def span(vals,percent=False):
   vals=[v for v in vals if v is not None]
   if not vals:return '—'
   factor=100 if percent else 1
   return f'{min(vals)*factor:.1f}–{max(vals)*factor:.1f}'+('%' if percent else '')
  report.append(f'| {cid} | '+span([r['gpu_percent'].get('mean') for r in rs])+' | '+span([r.get('gpu_sample_fraction_at_most_5_percent') for r in rs],True)+' | '+span([r.get('gpu_sample_fraction_at_least_90_percent') for r in rs],True)+' | '+fmt(max((r['vram_gib']['max'] for r in rs if r['vram_gib'].get('n')),default=None))+' | '+fmt(max((r['ram_gib']['max'] for r in rs if r['ram_gib'].get('n')),default=None))+' |')
 report+=['','连续 RT2 的六组窗口不足或接近一秒，约 1 Hz 监控只有极少样本，其均值和比例不能用于判断持续利用率；完整报告和曲线标注了样本数。PT 的较长窗口较容易观察持续负载。这里没有 SM occupancy、RT Core 活跃周期或 PCIe 全链路带宽实测，不能从 busy 推算这些指标。','',
  '## 图片、公共输入与数据组织','',
  f'全部有效采集的 17 路传感器实际 MCAP TF 与公共雷达参数对照结果：**{common["all_valid_captures_input_aligned"]}**。相机内参、光学世界变换和受控关节另外逐图核对。最大矩阵误差：{max(r["max_world_matrix_error"] for r in common["cases"] if r["capture_valid"] and r["max_world_matrix_error"] is not None):.9g}。不同链路的时间原点与步长保持原样；同组号表示同一静止输入，并非同一绝对仿真时间。','',
  '全部 PNG 来自实际 MCAP，没有重新渲染替代数据。图片浏览器包含四方向原图和三轮并排图；局部裁剪保留原像素，没有锐化。选定的前向地面/机体区域中，PT 与 RT2 的亮度差异明显，而地面仍保留类似的模糊纹理。1024 SPP 不能保证补回资产本身的细节；该观察也不足以确认 3DGS 未加载完成，需要专门的加载完成信号、纹理/3DGS 层级和相机对照实验。','',
  '图像 MAE/PSNR 是相对于 05 默认冻结 RT2 的差异，并非绝对画质分数。与自己比较为零也不能证明“最好”。四路鱼眼黑边参与整图指标；局部对照用于辅助肉眼判断。','',
  '原生使用 ROS Image，v06 使用 PNG CompressedImage；原生可能录到预热、正式和尾部的额外发布。因此相同 24 张选定图片不等于 MCAP 大小相同。额外发布量、CDR 字节数与点数范围见每项 decoded.json。','',
  '```text','results/'+out.name+'/', '  01_v06_gated/ … 08_native_continuous_pt/', '    round_01/ … round_03/', '      images/<front|back|left|right>/       # 通过校验的图片', '      diagnostic_images/...              # 失败链路证据', '      frames.csv / frame_metadata.json    # 时间、内参、TF、关节', '      decoded.json                        # 消息计数、点数、解码校验', '      timing.csv / phase_timing.csv        # 逐组、逐阶段时间与采样', '      capture/                            # 原始日志、配置、资源采样', '  analysis/                              # 汇总、差分、图片索引、资源曲线', '  final_integrity.json                    # 旧代码及根 USD 哈希和进程检查', '```','',
  'MCAP 保留在云端同名输出目录，每个原生 capture/bag/ 内，v06 在 capture/captures/<session>/bag_unified/ 内。本地下载的是解码图片和分析证据，未额外复制全部 MCAP。','',
  '## 未通过的连续 PT','']
 for c in cc:
  if c['id']!='08_native_continuous_pt':continue
  rows=[]
  with (out/c['id']/f'round_{c["round"]:02d}'/'frames.csv').open(encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
  offsets=sorted(set(int(x['header_stamp_ns'])-int(x['group_stamp_ns']) for x in rows))
  d=load(out/c['id']/f'round_{c["round"]:02d}'/'decoded.json')
  report.append(f'- 第 {c["round"]} 轮：通过={c["valid"]}，导出 {c["images"]} 张诊断图片；消息相对目标时间偏移 {offsets} ns；缺失项 `{json.dumps(d["errors"],ensure_ascii=False)}`。')
 report+=['','约 16.145833 ms 的偏移在数值上接近 (31/32)×(1/60 s)，提示原生子帧与 ROS 发布的时钟相位值得追查，但数值吻合不是根因证明。不能只改 header 让图像与 TF 看似对齐；后续应对照最终渲染回调、IsaacReadSimulationTime、发布执行边和 ROS 录包顺序。','',
  '## warning 的处理结论','',
  '- `omni.hydratexture.plugin` 接口重复获取/释放警告：保留原始计数，结合常驻 A/B 结果支持继续研究资源生命周期；它不等价于每组 pip 安装/卸载插件。',
  '- ROS PoseTree `getObjectType eInvalid`：默认和诊断原生配置均出现；本轮实际 TF 数值可核对，但不能据此忽略警告。应将 Fabric/目标 Prim 解析与发布数据来源分开确认。',
  '- `getSimulationTimeMonotonicAtTime ... returning current sim time`：涉及时间映射回退，连续 PT 对齐问题中应优先追查；目前只有关联证据。',
  '- `rendervar copy from texture directly to host buffer is counter-performant`：原生读回路径的性能提示，本轮保留该原生行为，没有擅自替换其 GPU→CPU 拷贝实现。',
  '- MotionBVH 关闭提示：本轮是静止姿态、Instant LiDAR，测试不覆盖运动畸变效果。PerfSDK 不可用等启动提示也原样记录，没有下载组件或改系统消除警告。','',
  '## 保留与复现','',
  f'远端检查：保留的 {integrity["preserved_source_count"]} 份旧源码变更列表 `{integrity["preserved_source_changes"]}`；本次运行 engine/suite/config/decoder 变更列表 `{integrity["runtime_source_changes"]}`；根 USD 未改：{integrity["root_usd_unchanged"]}；剩余实验自有进程：`{integrity["remaining_owned_processes"]}`。这只是指定文件和进程的核对，不是整机安全审计。','',
  '旧源码 ZIP 和哈希清单在项目 backups/ 与 reports/。未新增下载或更新依赖。短暂 SSH 断连仅影响本地读取，远端独立 supervisor 持续运行，恢复连接后继续取回已有结果，没有重复启动矩阵。首次轨迹适配错误在正式矩阵启动前修正，失败日志保留。','',
  '下一步优先保留 v06 资源常驻这一已验证优化；将原生默认 Helper 冻结采集作为替代候选，完成点云等价性核对后再决定是否切换。连续 PT 的发布时序需要单独实验。若目标是交互流畅，仍须另测控制输入延迟，不能用离线每组时间代替界面体感验收。']
 volume=[];points=[]
 for c in cc:
  decoded=load(out/c['id']/f'round_{c["round"]:02d}'/'decoded.json')
  image_topics={t:v for t,v in decoded['topics'].items() if t.endswith(('/image_raw','/image_raw/compressed'))}
  volume.append({'id':c['id'],'round':c['round'],'valid':c['valid'],'selected_images':c['images'],
   'bag_mib':c['bag_bytes']/1024**2,'image_messages':sum(v['messages'] for v in image_topics.values()),
   'image_messages_per_camera_min':min(v['messages'] for v in image_topics.values()),
   'image_messages_per_camera_max':max(v['messages'] for v in image_topics.values()),
   'image_cdr_bytes':sum(v['cdr_bytes'] for v in image_topics.values()),'topic_count':len(decoded['topics'])})
  for topic,v in decoded['point_counts'].items():points.append({'id':c['id'],'round':c['round'],'topic':topic,**v})
 for name,rows in (('data_volume.csv',volume),('point_counts.csv',points)):
  with (out/'analysis'/name).open('w',newline='',encoding='utf-8-sig') as f:
   w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 table=['## 数据量对照','', '| 配置 | 三轮 MCAP 大小范围 MiB | 每路相机实际消息数范围 | 每轮选定 PNG 数范围 |', '|---|---:|---:|---:|']
 for cid in aa:
  rows=[r for r in volume if r['id']==cid]
  table.append(f'| {cid} | {min(r["bag_mib"] for r in rows):.2f}–{max(r["bag_mib"] for r in rows):.2f} | {min(r["image_messages_per_camera_min"] for r in rows)}–{max(r["image_messages_per_camera_max"] for r in rows)} | {min(r["selected_images"] for r in rows)}–{max(r["selected_images"] for r in rows)} |')
 table+=['','逐项字节数、消息数见 data_volume.csv；各路雷达点数范围见 point_counts.csv。点数统计覆盖包内该话题全部消息，包括可能存在的预热/尾部消息；它不是按相同目标组逐点匹配的误差指标。','']
 at=report.index('## 未通过的连续 PT');report[at:at]=table
 near=['## 点云一致性仍有一项未解释','',
  '录包时序通过不等于跨链路几何结果逐点相同。v06 与原生链路的部分 NZ3 点数存在稳定差异；以下是第一轮第一目标组的实际 MCAP XYZ 距离统计：','',
  '| 配置 / MyNZ3_left | 总点数 | 距离≤0.5 m | 距离≤1 m | 距离≤2 m |', '|---|---:|---:|---:|---:|']
 for r in ranges['rows']:
  if r['round']==1 and r['topic']=='/lidar/MyNZ3_left/points':near.append(f'| {r["id"]} | {r["points"]} | {r["count_distance_le_0.5m"]} | {r["count_distance_le_1m"]} | {r["count_distance_le_2m"]} |')
 near+=['',f'对 v06 gated、keepalive、原生默认冻结 RT2 的三轮首组，共 {len(ranges["rows"])} 个传感器样本检查：非有限点 {sum(r["points"]-r["finite_points"] for r in ranges["rows"])}，零 XYZ 点 {sum(r["zero_xyz"] for r in ranges["rows"])}，缺失样本 `{ranges["missing"]}`。逐路分位数见 lidar_ranges.csv。','',
  '差距主要集中在近距离，但本轮尚不能确定是近处几何在 RTX 中的状态、射线发射/噪声时序，还是 CPU/GPU 提取路径的行为不同。已发布 TF 相同也不能单独证明 RTX 内部所有遮挡几何完全相同。不要把这一差异直接称为随机噪声，也不要将原生更少的点自动判成更准确。','',
  '后续应固定发射状态与时钟，核对 RTX 传感器的实际变换及近场遮挡几何，再同时比较 CPU/GPU 提取器的同一次原始结果。上表第一轮首组的 v06 gated/keepalive 距离统计一致，但第二轮也有差异；本轮未固定噪声随机种子，不宣称逐点一致。跨链路点云的完全等价性仍未证明。','']
 at=report.index('## 未通过的连续 PT');report[at:at]=near
 # Late cloud-only MCAP checks are attached after local image processing finishes.
 data['common_inputs_alignment']=common
 data['post_validation_attachment']={'tool_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
  'common_inputs_sha256':hashlib.sha256((out/'analysis/common_inputs.json').read_bytes()).hexdigest(),
  'lidar_ranges_sha256':hashlib.sha256((out/'analysis/lidar_ranges.json').read_bytes()).hexdigest()}
 (out/'analysis/comparison.json').write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
 detail=out/'analysis/NC-004_report.md';text=detail.read_text(encoding='utf-8');marker='\n## 采集结束后的公共输入与点云核对\n'
 if marker in text:text=text.split(marker)[0]
 text+=marker+'\n全部有效采集的 17 路传感器实际 TF 与双方共同记录参数对齐：**'+str(common['all_valid_captures_input_aligned'])+'**。原始核对见 common_inputs.json。\n\n'+'\n'.join(near)+'\n'
 detail.write_text(text,encoding='utf-8')
 target.write_text('\n'.join(report)+'\n',encoding='utf-8');print(str(target))
if __name__=='__main__':run(sys.argv[1],sys.argv[2] if len(sys.argv)>2 else None)
