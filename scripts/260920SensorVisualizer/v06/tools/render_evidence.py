"""Build the delivery note from saved actual results, never from estimates."""
import json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
def read(name):return json.loads((root/'reports'/name).read_text(encoding='utf-8'))
r=read('performance_collected.json');validation=read('performance_validation.json');native=read('native_acceptance_collected.json')
assert native['acceptance_status']['passed'] and r['final']['result']['passed']
assert not read('linux_unit_tests.json')['exit_code']
labels={'baseline':'v05 基线','motion':'A 精确缓存','optimized':'B 轻量发布（默认首次）',
        'diagnostic':'C 附加诊断','scheduled':'D 组边界让步 50 ms','keepalive':'E 资源 keepalive','final':'最终默认复测'}
lines=['# v06 性能与交付证据（2026-10-10，北京时间）','',
'## 交付结论','',
'独立 v06 已在本地和云端保存，保留 v05 与原资产。交互线程的常态开销下降；完整正式采集的画质、13 路雷达和四路 1920×1080 相机配置保留。采集启动/结束附近的长尾仍存在，不能宣称已经消除所有卡顿。',
'','## 实验条件与测量范围','',
'单 L40（46,068 MiB，驱动 580.126.09），CPU 配额 14 核、内存 120 GiB，Isaac 6.0.1-rc.7、ROS 2 Jazzy。场景 combine_scene_16_terrain_fisheye.usda；所有对照使用同一条 61 行轨迹的前八个 10 Hz 仿真网格。正式配置 RealTimePathTracing、DLSS 2、AA 3、初始化预热 4、相机冻结预热 16、正式子帧 2。没有降低分辨率或删掉传感器。',
'',
'每次测试：启动完整 GUI 交互进程，ready 后额外预热 5 秒；仅交互约 45 秒；保持键控的同时启动独立正式采集（8 组）；关闭测试交互进程后再采集 8 组。基线和每项变量各做一轮，最终默认另复测一轮。不是随机化的大样本统计，也不是此前的 100 组长测。',
'',
'monotonic_ns 均来自同实例。keys 回执测量接受输入状态到引擎处理完成，实际运动随后在更新中积分；参数命令回执代表对应操作完成。它不包含完整浏览器、网络、远程桌面、屏幕延迟。owner_ms 是本项目同步回调耗时，frame_gap 是相邻更新回调的间隔，二者不能等同。',
'',
'下表并发的控制窗口包含正式进程初始化、采集和退出。采集 wall_s 从初始化完成及记录进程 ready 后开始，含末尾排空；不含引擎启动、资产加载及全部退出，因此不能当作点击按钮到进程完全结束的时间。',
'','## 并发控制对照','',
'| 方案 | 回执 P95 / P99 / 最大 ms | 回调 P95 / 最大 ms | 更新间隔 P95 / 最大 ms | >100 / >500 ms 间隔 | 控制窗口秒 |',
'|---|---:|---:|---:|---:|---:|']
for key in labels:
    x=r[key]['result']['concurrent'];a=x['applied_ms'];o=x['owner_ms'];g=x['frame_gap_ms'];bins=x['frame_gaps_over_ms']
    lines.append(f"| {labels[key]} | {a['p95']:.2f} / {a['p99']:.2f} / {a['max']:.2f} | {o['p95']:.2f} / {o['max']:.2f} | {g['p95']:.2f} / {g['max']:.2f} | {bins['100']} / {bins['500']} | {x['wall_s']:.1f} |")
b=r['baseline']['result']['concurrent'];f=r['final']['result']['concurrent']
lines += ['',f"最终默认复测相对 v05：回调 P95 下降 {(1-f['owner_ms']['p95']/b['owner_ms']['p95'])*100:.1f}%；输入状态回执 P95 下降 {(1-f['applied_ms']['p95']/b['applied_ms']['p95'])*100:.1f}%。两次默认结果见表；最大值仍受启动/结束干扰，不能用 P95 改善声称长尾也已解决。",'',
'## 仅交互与正式采集吞吐','',
'| 方案 | 仅交互回执 P95 ms | 仅交互回调 P95 ms | 并发 8 组秒 / 组每真实秒 | 仅采集 8 组秒 / 组每真实秒 |',
'|---|---:|---:|---:|---:|']
for key in labels:
    x=r[key]['result'];a=x['interactive_only'];cw=x['concurrent']['capture']['wall_s'];ow=x['capture_only']['capture']['wall_s']
    lines.append(f"| {labels[key]} | {a['applied_ms']['p95']:.2f} | {a['owner_ms']['p95']:.2f} | {cw:.2f} / {8/cw:.4f} | {ow:.2f} / {8/ow:.4f} |")
fast=r['keepalive']['result'];default=r['optimized']['result']
final_run=r['final']['result'];baseline_run=r['baseline']['result']
lines += ['',f"最终默认复测相对基线：并发八组时间增加 {(final_run['concurrent']['capture']['wall_s']/baseline_run['concurrent']['capture']['wall_s']-1)*100:.1f}%，仅采集八组时间增加 {(final_run['capture_only']['capture']['wall_s']/baseline_run['capture_only']['capture']['wall_s']-1)*100:.1f}%。默认优化主要改善控制开销，未证明正式采集提速；这些单次差异包含运行波动。",
'',f"keepalive 相对默认首次：并发有效吞吐增加 {(default['concurrent']['capture']['wall_s']/fast['concurrent']['capture']['wall_s']-1)*100:.1f}%，仅采集增加 {(default['capture_only']['capture']['wall_s']/fast['capture_only']['capture']['wall_s']-1)*100:.1f}%；并发回执 P95 增大 {(fast['concurrent']['applied_ms']['p95']/default['concurrent']['applied_ms']['p95']-1)*100:.1f}%，最长间隔未改善。因此保留为可配置吞吐选项，默认 gated。边界让步 50 ms 没有确定减少长尾，默认 0。",'',
'## 资源与队列','',
'| 并发方案 | 交互 Kit 平均 CPU 核 / 峰值 RSS GiB | 采集 Kit 平均 CPU 核 / 峰值 RSS GiB | 整卡平均 / P95 GPU % | 整卡峰值显存 MiB |',
'|---|---:|---:|---:|---:|']
for key in ('baseline','optimized','keepalive','final'):
    data=r[key]['resources']['concurrent'];pid=r[key]['owner_ready']['pid'];other=next(k.split('_')[1] for k in data if k.startswith('pid_') and k.split('_')[1]!=str(pid))
    owner_cpu=data[f'pid_{pid}_cpu_cores']['mean'];cap_cpu=data[f'pid_{other}_cpu_cores']['mean']
    owner_rss=data[f'pid_{pid}_rss_kib']['max']/1024**2;cap_rss=data[f'pid_{other}_rss_kib']['max']/1024**2
    lines.append(f"| {labels[key]} | {owner_cpu:.2f} / {owner_rss:.2f} | {cap_cpu:.2f} / {cap_rss:.2f} | {data['gpu_util_percent']['mean']:.1f} / {data['gpu_util_percent']['p95']:.0f} | {data['gpu_memory_mib']['max']:.0f} |")
lines += ['',
'上述进程 CPU/RSS 是拥有登记的 Kit 进程，未把记录进程的编码线程混入；整卡 GPU 属于低频采样，不是某一函数的占用率。早期 baseline/A/B/C 的资源 case 标签还包含 owner 关闭窗口，后续 D/E/最终将它单列为 owner_close；不宜精细比较旧表平均值。原始每秒样本、阶段、PID、wchan、上下文切换仍保留。',
'','| 并发方案 | 8 组编码总秒 | 8 组 MCAP 写调用总秒 | 最大槽位占用 | 最大 incoming / encoded 入队等待 ms |',
'|---|---:|---:|---:|---:|']
for key in ('baseline','optimized','keepalive','final'):
    d=r[key]['capture_diagnostics']['concurrent'];t=d['writer']['timings'];run=d['runs'][0];q=run['queues']
    lines.append(f"| {labels[key]} | {t['encode_total_s']:.3f} | {t['write_total_s']:.3f} | {run['max_slots_in_use_at_reserve']} / 3 | {q['incoming_put_wait_ms']['max']:.4f} / {q['encoded_put_wait_ms']['max']:.4f} |")
lines += ['',
'编码与渲染可重叠，上表时间不能累加到总时长。PNG 工作线程仍有几十毫秒排队，但没有观察到记录管线成为整组主瓶颈。保留三槽所有权、代数编号与晚回执拒绝，没有用丢组换速度。',
'','## 根因与改动对应','',
'- 已确认：整套状态重复构建、锁内深拷贝放大主线程/命令开销。不可变状态代、短锁引用交换、轻量快照、键盘输入和完整状态发布解耦，直接降低常态耗时。JSON 序列化原本就在锁外，本轮保持这一点。',
'- 已确认：未改变的姿态重复进入 PhysX 和 USD 同步。交互使用精确缓存、复用矩阵/数组、合并一条复合命令中的原生写入；正式采集保持完整应用姿态和验证。',
'- 已确认：一次 507 ms 回调中，PhysX→USD 同步占 500.594 ms 墙钟、500.479 ms 线程 CPU。缓存避免静止状态重复进入，但移动时必要同步仍可能产生长尾。',
'- 已确认：轻量发布首次测量最长间隔约 744 ms，但自身更新最大约 11 ms；该间隔主要在回调外并靠近采集结束。具体 GPU 驱动/上下文销毁归属仍未确定。',
'- 已确认：恢复任务的 argv 可见性与继承锁释放不是同一观察。增加 releasing_resources/cleanup_pending、启动前资源检查和网页复位保护；保留跨网页重启的采集锁，没有强杀或忽略锁。',
'- 已实测：保留活动传感器更新提高吞吐，但增加两个引擎之间的竞争；组边界让步无法抢占原生渲染。两项分别单变量测试，保持默认交互优先。',
'',
'原生 Vulkan/CUDA/NVTX/CPU 调度证据、主机分配/释放热点和 Stream/Event/C++/CUDA 取舍见 native_hotspots_and_gpu_design.md。本轮没有添加无收益证据的 CUDA 内核，也没有修改闭源插件、驱动或全局预加载。',
'','## 监控开销','']
query=r['final']['monitor_query_ms']
lines += [f"外层 1 秒采样线程的查询墙钟平均 {query['mean']:.1f} ms、P95 {query['p95']:.1f} ms，含 nvidia-smi 进程和 /proc；这不是全被测进程的额外 CPU 耗时。比较各版使用相同采样能力。",
f"附加交互诊断单次 C/B：仅交互回调 P95 增大 {(r['diagnostic']['result']['interactive_only']['owner_ms']['p95']/r['optimized']['result']['interactive_only']['owner_ms']['p95']-1)*100:.1f}%，并发增大 {(r['diagnostic']['result']['concurrent']['owner_ms']['p95']/r['optimized']['result']['concurrent']['owner_ms']['p95']-1)*100:.1f}%；包含运行波动，不能全归因诊断。详细诊断默认关闭，可单独开启。",
'Nsight 只录单组有界窗口，存在追踪开销，未测得可靠的独立净开销；原生窗口不参与普通吞吐对照。没有将 profiler 数值写成无监控运行速度。',
'','## 数据与实际回归','']
groups=sum(v[c]['groups'] for k,v in validation.items() if k!='isolation' for c in ('concurrent','capture_only'))
max_tf=max(v[c]['tf_matrix_max_abs_error'] for k,v in validation.items() if k!='isolation' for c in ('concurrent','capture_only'))
lines += [f"本轮匹配对照共 {groups} 组，逐条解码 MCAP，含 {groups*13} 个 PointCloud2、{groups*4} 张 PNG。每组 19 条 TF 关系；所有时间戳、连续组编号、原生冻结时钟、标定矩阵、点云字节布局/有限值及写入消息 SHA256 摘要均通过。TF 重建与源传感器矩阵最大绝对误差 {max_tf:.3g}。离线根姿态/关节与源轨迹一致；完整配置的 sensor_registry、render_profile 和根 USD 哈希一致。",
'真实 SDK 事件进入实际键盘订阅并验证 Articulation 状态；Direct/Target/Periodic 关节及整机俯仰/横滚、速度平移与旋转、LiDAR/相机安装调整与保存、轨迹记录、两次 Exit/Reinitialize、F8/暂停/五次 Stop/Play 均通过。网页 loopback HTTP 120 次状态查询通过，真实轨迹 ZIP 的 HTTP 导出/认证导入往返保持位姿、关节和安装关系。',
'最终真实引擎验收还验证 offline、live_latest、live_complete 各三组，任务恢复、重复采集拒绝、pause/resume、安全 Stop + Drain 和不存在 GPU 请求拒绝。输出校验见 native_acceptance_collected.json；live_latest 明确记录跳过网格，live_complete 不静默丢组。',
'Linux 60 项测试通过；Windows 本地 60 项中 57 通过、3 项 Unix 专用跳过。测试中的 test capture failure 是主动注入的错误处理用例，不是引擎报错。',
'',
'验证边界：没有重做单次 100 组/30 分钟长测；没有人工测量浏览器到屏幕的端到端体感；源 frame ID 未由 SDK 暴露，不伪造。时间与矩阵一致、配置不变不单独证明全部 3DGS/点云几何严格对齐。双卡尚无设备，只完成参数核验和显式分配准备，未宣称双卡收益。',
'','## 文件、运行与回退','',
'本地 scripts/260920SensorVisualizer/v06；远端 /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06。完整操作见 startup_and_usage.md，架构见 architecture_and_data_contract.md，warning/剩余停顿见 warnings_and_remaining_stalls.md。默认独立网页端口 17875。',
'v05 本地备份 ../backups/v05_performance_baseline_20261010_114432，远端备份 ../backups/v05_performance_baseline_20261010T034525Z；旧目录的 102 源文件逐一校验未变。关闭 v06 自有任务后直接回旧目录启动，不覆盖旧版。',
'','证据索引：performance_collected.json、performance_validation.json、native_acceptance_collected.json、native_trace_analysis.json、linux_unit_tests.json、final_state.json。实验原始日志与 MCAP 保存在远端 v06 输出目录，失败验收尝试也保留。完整审计 ID 在实例外 CloudInstanceOps 日志；没有下载外部依赖或升级系统组件。',
'','后续学习从不可变状态代、CPU/墙钟计时、mmap 所有权开始，再对照 NVTX/Vulkan 与 CUDA 事件。完整课程和额外 CUDA 实验由后续需求决定。','']
(root/'docs/performance_evidence.md').write_text('\n'.join(lines),encoding='utf-8')
print(json.dumps({'saved':str(root/'docs/performance_evidence.md'),'matched_groups':groups,'final_owner_p95_ms':f['owner_ms']['p95'],'final_receipt_p95_ms':f['applied_ms']['p95']}))
