# -*- coding: utf-8 -*-
"""Generate evidence-based delivery report after native test completion."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1];R=ROOT/'reports'
def load(name):return json.loads((R/name).read_text(encoding='utf-8'))
m=load('performance_metrics.json')
rows=[]
for n,label in [('final_baseline','v03 同配置基线'),('final_gated','v04 严格门控'),('final_throughput','v04 离线资源保留')]:
    d=m[n];s=d['result'];g=d['group_to_owned_s']
    rows.append(f"| {label} | {s['complete_groups']} | {s['wall_capture_s']:.2f} | {s['groups_per_wall_s']:.5f} | {g['p50']:.2f} | {g['p95']:.2f} | {d['supervisor']['wall_s']:.2f} |")
base=m['final_baseline']['result']['wall_capture_s'];gated=m['final_gated']['result']['wall_capture_s'];fast=m['final_throughput']['result']['wall_capture_s']
quality=[]
for n in ('final_gated','final_throughput'):
    c=load(n+'_comparison.json');v=list(c['validation'].values())[-1];comp=next(iter(c['comparison'].values()))
    ps=[p['psnr_db'] for p in comp['images']];err=max(x['max_abs_matrix_error'] for x in comp['pose_checks'])
    quality.append(f"- {n}：{v['groups']} 组，{v['images']} 张图像，{v['points']:,} 个点，{v['topics_per_group']} 话题/组；PNG/CDR/TF/时间完整检验 passed。同组矩阵最大差 {err:.1f}；图像 PSNR {min(ps):.2f}–{max(ps):.2f} dB。")
controls=load('controls.json') if (R/'controls.json').exists() else {'state':'pending'}
tests=controls.get('acceptance',controls)
text=f'''# v04 原生诊断、性能与正确性验收

2026-10-09。基线按用户明确答复采用 v03，新建独立 v04，不覆盖 v02/v03 或原始 USD。

## 实测收益

| 版本/策略 | 有效组 | 采集及排空秒 | 组/墙钟秒 | 单组至拥有数据 P50秒 | P95秒 | 启动至退出总秒 |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

严格门控有效吞吐提高 {(base/gated-1)*100:.1f}%；离线资源保留吞吐约 {base/fast:.2f} 倍。冷启动总时间另列，不能把稳定采集收益解释为每次打开软件都快同样比例。P95 来自仅8组短对照，包含第一组预热，不代表长任务统计置信区间。

三者均为相同场景、运动轨迹、4路1920×1080鱼眼、13路Instant雷达、60Hz物理、10Hz仿真采样、16个相机预热子帧和2个正式子帧。正式采集与运动顺序执行。均明确选择同一个HDR DomeLight。无高开销Nsight追踪；保留同等级项目日志。

## 一组的顺序与主要耗时

1. 等待缓冲槽，再推进6个物理步；USD和Articulation仅在主线程操作。只有这个阶段推进仿真时间。
2. 暂停Timeline，冻结原生时钟、机器人部件、全部传感器矩阵和安装revision。
3. 同姿态预热，再手动请求全部相机与雷达Writer，正式step_async的delta_time为0。
4. 全部完成回调将GPU数据复制为独立CPU数组，校验来源时钟与渲染位姿；不依赖request_id来证明新鲜度。
5. 交给后台mmap/IPC，独立进程并行PNG、CDR、顺序MCAP写入；下一组可与后台工作重叠。
6. 暂停、结束与关闭时才全局停止/排空生成会话。严格门控阶段外关闭传感器；离线资源保留策略在活动组间产生不保存的中间渲染，以减少RTX资源再建。

最初v03基线中，正式render_wait平均6.84秒，逐组排空平均0.85秒；相机预热render_wait约2.22秒，后续预热排空约0.38秒；读取验证约0.034秒，后台打包约0.011秒。回读/编码不是当时最大关键路径，先增加PNG线程不会消除多秒的原生准备。

## 原生证据与根因分类

**已确认**：v03逐组停止会话后重新初始化。原生稳定组追踪初始化约7.138秒，其中主线程实际运行6.940秒。该区间1166次vkAllocateMemory、1101次vkGetMemoryFdKHR、20270次vkUpdateDescriptorSets，表明大量资源准备与互操作。futex累计约0.109秒、poll约0.061秒、vkWaitForFences约0.062秒；不是主要时间都在长锁等待。

**已确认**：持续会话与全部传感器回调可以通过来源时间/渲染矩阵/文件完整性验证；无需在每组停止全局生成来取得拥有的CPU数据。源帧号接口未暴露，仍为null。

**较强推测**：资源销毁/再建导致原生LiDAR、CUDA驱动、NVRTC、传感器互操作准备反复执行。原生栈中LiDAR模块约52%、CUDA驱动约33%、NVRTC约27%是inclusive采样，各栈可重叠，不能相加成耗时占比。闭源符号不足，未将剩余CPU精确拆分到每个内部算法。

**已确认配置效应**：两个DomeLight同时有效时，初版持续会话图像出现黑天空，PSNR仅4–7dB；在Session层停用近黑色地形DomeLight后，天空恢复。内部背景选择顺序/机制属于推测。新版把单DomeLight选择作为明确配置，两版公平对照采用相同选择，不将此前黑天空实验计入等质收益。

**已确认新版剩余热点**：稳定预热 step_async 的3.093秒区间内，cudaFreeHost 234次、累计1.955秒；cudaHostAlloc 234次、累计0.276秒。正式 step_async 的0.719秒区间内，两项各52次，分别累计0.426秒和0.061秒。API时间可与GPU执行重叠，并可能包含驱动等待或隐式同步，不能全归为纯分配成本，也不能与GPU时间直接相加。新版正式区间vkAllocateMemory/vkGetMemoryFdKHR均为0。详见 native_hotspots_and_depth_checks.md。

**尚未验证**：长100组稳定统计、双GPU收益、改变MultiTick/MotionBVH兼容参数的收益、GPU直接编码/异步DMA的进一步收益。本轮没有为这些推测安装工具或修改SDK。

## GPU、CPU、内存的解释

资源按阶段汇总见 docs/evidence/performance_metrics.json；原始实验目录保留完整采样。CPUcores是进程消耗的核数，主线程百分比是相对一个核；容器配额14核。整卡GPU采样不是单个函数SM占用，1秒采样可能跨越阶段边界。资源保留提高了运动阶段GPU工作，但验收依据是有效组吞吐改善。

![原生时间线](evidence/native_timeline.png)

时间线使用第一份individual Vulkan追踪。它发生8192workload/frame溢出，GPU记录并集是已观察工作的下界，缺记录不能当成绝对空闲。改用batch避免该类溢出，但批次覆盖区间可能包含内部空档，也不能解释为GPU持续100%。CUDA13驱动与Nsight2025.1有兼容警告，报告未隐去这些限制。

## 数据正确性

{chr(10).join(quality)}

点云不与 v03 位级一致。v03 两次相同顺序运行的104路次点云位级一致，而新版改变渲染序列后点数与返回距离不同，不能用“随机噪声”一句话跳过这一差异。同一冻结姿态、同一仿真时间再次预热/采集，配置测距噪声为0的 NZ3 返回仍变化，证明渲染历史本身足以改变结果。关闭3DGS后差异缩小但没有完全消失，具体随机源或透明度返回机制尚未定位到闭源内部。独立解析箱体检查及误差见 native_hotspots_and_depth_checks.md。数据格式、时钟、TF、组完整性已验收；不承诺复现旧版每一个点。需要复现原采集顺序的任务可使用 compatibility 后端或保留的 v03。图像也存在采样与降噪差异，原始分辨率PSNR和四路导出图单独检查。

原生面板验收状态：{tests.get('state','pending')}。详细过程见 reports/controls.json：无窗口Omni.UI代码运行、初始化空闲门控、静态采集、目标关节/俯仰、暂停→恢复→停止、再次采集、安装位姿修改重同步与关闭恢复。这是功能验收，不是网页桌面上的视觉或手感验收。按钮仍可能等待长原生调用，未承诺消除所有交互卡顿。

## 失败或无收益的实验

| 实验 | 结果与处理 |
|---|---|
| 只保留相机预热会话，随后加入LiDAR | 错误RTX位姿；重试增加到136.65秒/8组，拒绝 |
| 预热全传感器但仍逐组停止 | 91.82秒/8组，开销移到预热，没有收益，不作为默认独立策略 |
| 只保留LiDAR更新但仍停启生成 | 159.31秒/8组，退化，撤回 |
| 持续会话但未处理双DomeLight | 74.45秒/8组但画面黑天空，正确性未通过，不算验收收益 |
| 恢复viewport灯光开关或常规capture settings | 黑天空未修复，未加入生产逻辑 |
| 先同步雷达再关闭雷达让相机收敛 | RTX矩阵错误，整组拒绝，未加入生产逻辑 |

## 警告与剩余风险

原始Kit日志和各阶段warning计数全部保留。8组正式对照中，v03/v04门控/v04资源保留分别有228/204/191条warning，均无Error或Traceback；already released类分别191/167/167条，仍未消除。hydratexture接口already released警告与阶段门控资源停启同时出现，未直接证明每条警告都造成数据损坏；本次通过独立回调与来源检查拒绝无效结果。SDK反复获取接口的performance warning、Fabric版本差异、缺RobotMotionSchema、非本项目动画图注册警告仍存在。没有静默过滤，也没有修改安装目录来消除文本。

MotionBVH关闭保留原有兼容配置。当前正式采集冻结场景、Instant扫描不包含组内运动，故不依赖运动模糊效果；不能推广为任意动态扫描都安全。音频/Cache Server警告与本轮主要关键路径无直接证据，不为此安装服务或修改系统。

## 可复现、部署与回退

实验输入、SDK计时、Kit日志、原生nsys-rep/SQLite、MCAP保留在 /root/gpufree-data/semantic/output/sensor_visualizer/v04/experiments。每个目录有job/spec/process/supervisor结果；源码哈希在对应diagnostics manifest。实验入口只在自己的进程中包装SDK，finally恢复，未修改已安装SDK。

复现普通基准用 experiments/remote_start.py，通过runpy传入VERSION、LABEL、GROUPS和JOB_EXTRA；公平v03基线还设置SPEC_EXTRA.single_hdr_dome=true。原生追踪应direct_kit=true，短窗口profile_first/profile_last，关闭其他本任务采集。高开销追踪不能与普通墙钟基准混用。Nsight选项依据已安装help及[NVIDIA官方指南](https://docs.nvidia.com/nsight-systems/UserGuide/index.html)，无工具下载/安装。

项目部署到双端v04。旧源码双端ZIP和哈希在backups/20261009_before_v04；原始USD从不Save。关闭v04后直接使用保留的v03入口即可回退。启动流程见startup_and_operation.md。无系统、驱动、桌面或安全设置变更。本轮操作通过cloud-instance-ops审计包装器留痕，记录不等于整台实例完整审计。
'''
(ROOT/'docs/deployment_and_native_test.md').write_text(text,encoding='utf-8')
(ROOT/'docs/verification.md').write_text('''# v04 验证说明

本轮以实际文件为证据，不沿用旧版本验证结论。完整结果见 deployment_and_native_test.md。

- docs/evidence/portable_tests.txt：29项可移植测试，包括丢失/晚回调、独立数组所有权、全传感器屏障、取消与原生排空、错误源时间/矩阵、失败资源关闭、缓冲ACK和跨线程CPU计时。
- docs/evidence/final_gated_comparison.json 与 final_throughput_comparison.json：完整MCAP解码及同等灯光/姿态/时间对照。
- docs/evidence/controls.json：实际Kit/Omni.UI功能验收及资产前后哈希，不等同网页桌面视觉验收。
- docs/evidence/native_final_analysis.json 与 native_direct_analysis.json：原生栈、调度、Vulkan/CUDA/OSRT证据及采集限制。
- reports/isolation_check.json：生产入口不依赖旧代码；旧版哈希核对。experiments明确可以读取基线，仅用于诊断。

尚未完成的长100组统计与闭源内核精确归因不宣称已验证。图像与点云不宣称位级一致。失败实验完整保留，不计作成功收益。
''',encoding='utf-8')
print('Wrote native delivery report')
