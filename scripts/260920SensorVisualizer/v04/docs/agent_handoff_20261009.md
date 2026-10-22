# Sensor Visualizer v04 任务交接

整理日期：2026-10-09，Asia/Shanghai。本文供接续 agent 阅读；只整理交接，不启动新实验、不修改采集代码。部署与进程信息是上一轮验收快照，接手时需要重新确认。

## 1. 当前任务与结论

用户希望解决 Sensor Visualizer 在 Isaac Sim 中运行后严重卡顿、CPU/GPU 总利用率看似不高的问题，并要求保留旧版本，进行底层诊断和有证据的优化。用户已明确选择：**以 v03 为基线，新建独立 v04**。原始 prompt 正文中的 v02 目录不能覆盖这项选择。

v04 已在本地完成并部署到远端。主要改动是保留采集生成会话，避免逐组停止后重建 RTX/Vulkan/CUDA 互操作资源；同时保留运动与正式采集的顺序、来源校验、异步编码写包和诊断日志。

同配置 8 组对照中，默认门控策略有效吞吐提高 22.4%，离线保留资源策略约为 v03 的 2 倍。**这不代表卡顿全部解决。** 多秒原生调用仍占用主线程；100 组长任务、真实网页桌面手感与 RViz 视觉验收尚未完成。点云不与 v03 位级一致，具体返回差异仍需排查。

接续时优先读本文，再读性能报告与正确性证据。不要把历史方案、实验失败或推测写成已部署能力。

## 2. 路径、环境与备份

| 项目 | 位置 / 验证快照 |
|---|---|
| 本地项目 | `D:\learning\IntelligentDepartment\CodesSet\Self\260707IsaacSIm\scripts\260920SensorVisualizer\v04` |
| 云端项目 | `/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v04` |
| 云端输出根目录 | `/root/gpufree-data/semantic/output/sensor_visualizer/v04` |
| 当前场景 | `/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_16_terrain_fisheye.usda` |
| 两端旧版备份 | 项目父目录下 `backups/20261009_before_v04`，包含 v02/v03 ZIP 和逐文件哈希 manifest |
| Isaac Sim | `/root/isaacsim`，6.0.1-rc.7 |
| Replicator | 1.13.27+110.1.1 |
| ROS | ROS 2 Jazzy，`/opt/ros/jazzy` |
| GPU | L40，46068 MiB 显存；驱动 580.126.09 |
| 容器资源 | CPU 配额 14 核，RAM 约 120 GiB；不是主线程可同时使用 14 核 |
| 已有 Nsight | `/opt/nvidia/nsight-compute/2025.1.1/host/target-linux-x64/nsys`，2025.1.1.0 |
| 本地 Python | `D:\Anaconda3\python.exe`，读取中文建议 `-X utf8` |

传感器为 **4 路 1920×1080 鱼眼相机 + 13 路 Instant LiDAR**。相机方位为 front/back/left/right。MyAiry 为 back/backleft/backright/front/left/right/up 共 7 路；MyNZ3 为 back/backleft/backright/front/left/right 共 6 路。发现与选择传感器沿用自动发现逻辑。

最后验收记录：[final_verification.json](../reports/final_verification.json)：

- 102 个部署文件本地与云端哈希一致，部署差异为空。
- 71 个 Python 文件通过运行时依赖隔离检查。生产代码不导入 v02/v03；`experiments/` 可在独立实验进程中包装基线。
- 云端原版本 268 个文件、18 个被使用的原始资产层未变；本地旧版本检查 191 个文件未变。
- 当时未留下 Kit、采集 supervisor 或录制 worker。**这是快照，不能代替接手时进程检查。**

本轮没有安装或下载工具，没有修改 SDK、驱动、桌面、安全配置或原始 USD，没有创建系统软链接。旧版本目录仍保留，可以直接回退。

## 3. 用户约束与已保留功能

1. 保留 v02/v03 与原始资产；v04 独立运行，不调用旧版运行时代码。需要新增大幅架构实验时先备份当前 v04。
2. 正式采集必须按 **运动 → 冻结 → 渲染/读取 → 保存** 的顺序执行，采集窗口内不推进机器人姿态与仿真时钟。
3. 交互模式仍不高于 0.1 倍速；用户已允许离线模式不限速。10 Hz 指仿真时间采样网格，并非墙钟达到 10 组/秒。
4. 保留关节和整机控制、传感器安装位姿调整与记录，不为提速删掉这些能力或重新设计面板。
5. 关节与整机 Pitch/Roll 有 Direct、Target + speed、Periodic 三种模式；整机支持 XYZ、Yaw、前进速度和转速。cab–track 保持初始角度。
6. 安装位姿为父节点局部 XYZ/RX/RY/RZ；每次调整有日志，Save Current Poses 为明确保存的快照。Stop/关闭恢复初始运动和安装位置，需要保留的位姿应先保存。
7. Warning 要留证据和分析，不通过屏蔽文本、删日志或修改 SDK 制造“无警告”。
8. 不降低相机分辨率、雷达数量、采样参数或渲染质量来宣称同质量提速；不拟合、过滤或补点制造与 v03 一致。

## 4. 代码模块与一组数据链路

所有模块均位于 `sensor_visualizer_v04/`，除入口和 tools/experiments 外。

| 环节 | 项目入口 / 函数 | 主要外部接口 |
|---|---|---|
| 启动 | `run_capture.py` → `kit_entry.py`；GUI 用 `run_in_isaac.py` → `ui.py` | Kit 子进程、Omni.UI；启动器仅整理自己的子进程环境 |
| 组调度 | `coordinator.py::CaptureRunner.run()` | asyncio；协调控制请求、缓冲背压、组状态与失败收尾 |
| 场景初始化 | `scene.py::SceneStepper.initialize()`；`robot/` | `omni.usd`、pxr USD、Articulation、Timeline；匿名 Session 子层 |
| 运动和时钟 | `scene.py::SceneStepper.advance()` / `native_time()` | `SimulationManager.get_simulation_time()`、物理更新与关节控制 |
| 冻结与采集 | `scene.py::SceneStepper.capture()`；`tickets.py::CaptureTicket` | 记录原生时钟、机器人/传感器矩阵、安装 revision；前后冻结校验 |
| 渲染生命周期 | `sensors.py::SensorDrivers.warm_cameras()` / `acquire()` / `_step()`；`gating.py::ProductGate` | Replicator RenderProduct、Writer、annotator、Hydra texture 更新开关 |
| 正式渲染 | `SensorDrivers._step()` | `rep.orchestrator.step_async(delta_time=0, pause_timeline=True, wait_for_render=True, rt_subframes=...)` |
| 完成与拥有数据 | `SensorDrivers._receive()` / `read()` | `rgb`、`CameraParams`、`IsaacExtractRTXSensorPointCloud`、`IsaacReadSimulationTime`；复制为独立 CPU 数组 |
| 后台传输 | `pipeline.py::RecordPipeline.reserve()` / `submit()`；`buffers.py` | 有界 mmap 槽、IPC、独立录制进程 |
| 编码与写包 | `record_worker.py::run()` 内的 `encoder()` / `sink()`；`messages.py` | 并行 PNG 编码、ROS 2 CDR、MCAP/rosbag2 顺序写入；ROS preview 可选 |
| 诊断 | `diagnostics.py`、`resources.py`、`native_trace.py` | 单调时间、native TID、线程 CPU、/proc/cgroup、GPU 采样、可选 NVTX/Nsight |

一组默认执行顺序：

1. 先等可用缓冲槽，避免机器人已经运动却没有保存空间。
2. 推进运动：60 Hz 物理、10 Hz 采样时每组推进 6 步；采样时间来自原生仿真时钟。
3. 暂停 Timeline，冻结机器人部件、全部传感器矩阵、时钟与安装 revision。
4. 同一固定姿态预热。默认相机预热 16 子帧，正式采集 2 子帧；初始 warmup 为 4。
5. 手动请求全部 17 路传感器 Writer，再执行零时间增量正式渲染。
6. 等待全部完成回调；复制数据、检查来源仿真时间与渲染矩阵，拒绝过期/错位结果。
7. 把拥有的数据交给后台 mmap/IPC。默认 3×64 MiB 槽、4 个编码 worker、PNG 压缩级别 1。下一组可与后台编码写包重叠。
8. Pause/结束/失败/关闭时停止并排空生成与录制，不在原生回读未完成时销毁产品或移动场景。

### 来源与同步的边界

`SimulationManager.get_simulation_time()` 用于运动时钟与采样网格；annotator `IsaacReadSimulationTime` 用于确认返回数据来源。保存时间戳为仿真时间，不是墙钟或人工递增的伪造来源时间。

当前适配器没有暴露可靠 `source_frame_id`，字段保持 `null`；request_id 只用于关联，不能证明帧新鲜。MultiTick 关闭后 native GMO timestamp 与逻辑仿真时钟并非同义，暂停时 native timestamp 也可能变化。来源时钟与矩阵一致不能单独证明每个 XYZ 对应同一个原生扫描帧；下一步应研究安全、拥有数据的 native header/frame 标识。

`async` 不表示原生调用完全不阻塞。Kit/USD/RTX 有主线程和上下文约束，不能任意放入 Python 线程。

## 5. 策略、兼容配置与灯光

| 配置 | 行为 |
|---|---|
| `capture.backend: persistent_gated` | 默认。保留全部传感器生成会话，通过回调读取和来源检查，避免逐组 stop/drain |
| `capture.backend: compatibility` | 独立实现的较旧生成生命周期；较慢，用于回退/对照，不保证仅改此标志就逐点复现 v03 |
| `capture.resource_policy: gated` | 默认。空闲、运动、背压、暂停与结束关闭实际传感器更新；固定姿态预热/采集时开启 |
| `capture.resource_policy: keepalive` | 仅离线+persistent。活动组间保留实际更新，运动中的中间渲染不保存；正式采集仍先冻结，暂停/结束/背压时停用 |

离线 keepalive 的提速包含**允许运动阶段做中间渲染**这一取舍，不能描述成“所有阶段都关闭传感器”。

目前保留 Motion BVH=false、MultiTick=false、perSensorTickTlas=false 和 `outputBufferOnGPU=false`，渲染采用 RealTimePathTracing，DLSS mode 2 / AA 3。没有把这些兼容项列为已经解决的底层问题。

[NVIDIA RTX Sensor 文档](https://docs.isaacsim.omniverse.nvidia.com/6.0.1/sensors/isaacsim_sensors_rtx.html)说明当前 annotator 路径在 `outputBufferOnGPU=true` 时输出为空。不能直接打开它来“提速”；须先设计 GPU 感知读取器与同步/生命周期验证。当前资产已经使用 BASIC GMO 通道，不能再把 FULL 降到 BASIC 当作现成收益。

当前场景有两个有效 DomeLight，初版 persistent 捕获出现黑天空。显式配置：

```json
{"render": {"background_dome": "/environment_Fangshan_02/DomeLight"}}
```

在 Session 层停用其他 DomeLight 后画面恢复，关闭时恢复；其他类型灯光不变。公平 v03/v04 对照均使用相同 HDR。内部为什么选择黑背景尚未证明。换场景要确认正确路径；如需保留资产全部灯光选择，可使用 `background_dome: null` 与 compatibility 后端。

## 6. 性能证据与主要剩余热点

### 公平短对照：未启用高开销 Nsight

同场景、同轨迹、同 17 路传感器和渲染参数，8 组完整采集。

| 版本 | 采集及排空墙钟秒 | 组/墙钟秒 | 单组至拥有数据 P50 / P95 秒 | 进程启动至退出秒 |
|---|---:|---:|---:|---:|
| v03 | 92.23 | 0.08674 | 11.31 / 11.58 | 148.85 |
| v04 gated | 75.37 | 0.10614 | 9.03 / 10.21 | 138.74 |
| v04 keepalive | 46.11 | 0.17348 | 4.94 / 9.97 | 109.59 |

P95 只有 8 组且包含首次预热，不能据此宣称长任务稳定。总冷启动另列，不能与稳定组吞吐混用。

### 原生追踪：不能与普通吞吐数据混用

- v03 重启生成的稳定初始化：墙钟 7.138 秒，主线程实际运行 6.940 秒；1166 次 `vkAllocateMemory`、1101 次 `vkGetMemoryFdKHR`、20270 次 `vkUpdateDescriptorSets`。证据支持反复资源准备/互操作是主因，长锁等待不是该段主要时间。
- v04 keepalive 稳定预热：墙钟 3.093 秒，主线程运行 3.054 秒；`cudaFreeHost` 234 次累计 1.955 秒，`cudaHostAlloc` 234 次累计 0.276 秒。
- v04 keepalive 正式渲染：墙钟 0.719 秒，主线程运行 0.713 秒；两接口各 52 次，累计分别 0.426 / 0.061 秒；`vkAllocateMemory` / `vkGetMemoryFdKHR` 都为 0。

**下一热点有证据指向原生锁页内存生命周期与同步。** 但这些 API 墙钟时间可能包含驱动等待、隐式同步，也可与 GPU 执行重叠，不能全部当作纯分配 CPU 成本。尚未确认内部每个缓冲的对象、所有权或复用接口。

主线程稳定采集接近一核吃满，容器 14 核总百分比仍可能很低。新增 PNG 线程不能消除这个瓶颈。CPU/API/GPU 时间不能相加；inclusive 栈的 LiDAR/CUDA/NVRTC 比例也不能相加。

追踪限制：individual Vulkan 达到 8192 workload/frame 上限，GPU 工作并集仅是观察下界；改 batch 后区间可能含内部空隙，也不证明持续 100%。Nsight 2025.1 对 CUDA 13 驱动有兼容警告并回退 CUPTI 12.8。不能凭这些 trace 的空档断言 GPU 空闲。第一轮启动器去掉了 Nsight 注入的 preload；后续 direct Kit 追踪已有 OSRT，不要再次用错误入口。

## 7. 正确性、warning 与尚未解决的事项

### 已验证

- 29 个可移植单元测试通过。
- gated：8 组、32 张图像、4,565,184 个点，30 话题/组；完整组、CDR/PNG、TF、来源时间和冻结检查通过。
- keepalive：8 组、32 张图像、4,563,721 个点，相同格式完整性检查通过。
- 相同组时间戳与矩阵一致；图像对照 PSNR gated 32.49–34.38 dB，keepalive 30.62–33.91 dB。四路对照缩略图人工查看过，天空与主要几何恢复；原素材 3DGS 模糊仍在，未承诺逐像素一致。
- 原生 headless Omni.UI 测了静态采集、目标关节/倾斜、暂停恢复停止、再次采集、安装调整重同步与关闭恢复。三种运动模式的逻辑另有便携测试。

### 点云返回差异仍待排查

两次相同顺序的 v03 共 104 路次点云位级一致；改变渲染顺序后的 v04 点数与距离不同，部分比较的最近邻 p95 约 0.299 m，不能笼统归为随机噪声。

同一冻结姿态与仿真时钟重复 v04 预热/采集，配置测距噪声为 0 的 NZ3 仍有变化；来源时钟差和矩阵差均为 0。关闭 3DGS 后差异缩小但不全消失。支持渲染历史影响返回，**尚未定位闭源内部机制**，不能断言全部由 3DGS 或某一种噪声造成。多回波时射线方向匹配存在歧义，尚无完整逐射线等价证明。

独立不透明解析箱体：v04 4 组、52 路次返回点均满足几何真值，最大表面误差约 7.97 μm；v03 同样检查通过。然而“所有配置发射器均有有效回波”的额外断言两版都失败，最低比例分别为 v03 98.5578%、v04 98.6127%。[analytic_depth.json](evidence/analytic_depth.json)保留整体 `passed:false`，`geometry_passed:true`、`full_emitter_coverage_passed:false`。**不得把整体改成 passed，也不能把缺少回波等同于录制丢组。**

### Warning 与交互边界

正式 8 组 v03/gated/keepalive warning 分别 228/204/191 条，无 Error 或 Traceback。hydratexture “already released” 分别 191/167/167，仍存在；另外有 performance interface、Fabric schema、RobotMotionSchema 和动画注册类。没有过滤/修改 SDK，也没有证据证明每条 warning 都导致数据损坏。需按阶段和资源生命周期继续归因。

按钮测试是在组边界请求，不能用测试响应时间证明多秒原生调用中即时响应。实际网页桌面面板手感、RViz 显示和 100 组稳定性都仍待验收。双 GPU、GPU 直接编码/DMA、MultiTick/Motion BVH 的收益尚未验证。

## 8. 不应直接重复的失败实验

| 实验 | 已有结果 |
|---|---|
| 先只预热相机，再加入 LiDAR | RTX 矩阵错误，最大约 4.316 m；重试后 136.65 秒/8 组，拒绝 |
| 全部产品预热但仍逐组停止 | 91.82 秒/8 组，几乎没有收益 |
| LiDAR keepalive 但仍停启会话 | 159.31 秒/8 组，退化 |
| persistent 不处理双 DomeLight | 74.45 秒/8 组但黑天空；不是有效性能收益 |
| 同步雷达后关闭它，单独做相机收敛 | 错误 RTX 矩阵，拒绝 |
| 冻结重复采集但中间不完整预热 | 错误矩阵；诊断改为每次同姿态完整预热 |
| 解析箱只隐藏 Mesh/3DGS | 其他旧基元仍在，几何验证失败；不能算生产链路失败 |

除非有新证据解决已知失败条件，不盲目重试。曾经无界 dump 资产数组导致约 186 MB 输出和 SSH 超时；检查 USD 属性应限制长度，尤其是 3DGS 数组。

## 9. 接手后的建议优先级

这里是接续建议，不表示本次整理文档已执行这些事项；启动新实验应结合用户后续具体授权。

1. **复核现状**：核对源代码/配置/部署哈希、旧版备份与实例身份，确认是否已有用户的 GUI 或采集进程。阅读下面证据，先备份 v04；不能默认最后验收快照仍有效。
2. **长任务和交互验收**：同质量 100 组无 Nsight 测量，检查 P50/P95、内存/显存增长、槽背压、写包完整性、warning 随组数增长与实际 GUI 手感。先小任务确认画面；不同时运行两个控制器。
3. **原生缓冲原型**：短追踪区分锁页内存申请/释放、隐式同步与 GPU 工作，确认 buffers 所有权和可复用接口。若研究 GPU 驻留 GMO，另写最小后端原型，先证明数据可读与同步正确，再讨论替换。禁止 unsafe pointer view、盲目 hook 或简单开启 GPU 输出开关。
4. **返回值差异**：安全获取拥有的 native header/emitter/frame 标识，区分渲染种子、透明度、多回波筛选、缺回波与旧姿态；保持冻结与时钟校验。解析几何、3DGS 隔离、完整 MCAP 验证是不同验收维度。
5. **Warning 归因**：以时间、组 ID、native TID 与生命周期对齐 already-released 等警告，判断是否与资源再建和阻塞相关，处理可验证原因。

不要预设“加一张 GPU”或“多开 Python 线程”能解决单主线程原生准备。要新增日志时记录关联 ID、CPU 调度和 GPU/API 时间边界，保持低开销；跨 await 的 thread CPU 增量是包含期间其他工作的统计，不是函数独占 CPU。

## 10. 启动、验证、回退与部署操作

完整用户操作说明：[startup_and_operation.md](startup_and_operation.md)。以下仅保留接手所需命令。

### GUI

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v04
/usr/bin/python3 run_capture.py --gui
```

打开 scene_16 后，Script Editor：

```python
from pathlib import Path
p = Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v04/run_in_isaac.py')
exec(compile(p.read_text(encoding='utf-8'), str(p), 'exec'))
```

入口只建面板。顺序：Load Job（如需）→ Initialize Current Stage → 等 Ready → 调关节/整机/安装位置 → Start Capture → Pause/Resume 或 Stop + Drain → 等 finished；关闭使用 Close / Restore。不要手工 Timeline Play，不要因初始化慢重复运行入口。

此面板沿用 v03 的 Initialize / Start Capture，**不是更早 v02 的 Play Simulation / Start Recording / Adjust LiDAR**。这属于已有版本差异，接手时不要擅自重做 UI。

### 离线与验证

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v04
# 先短诊断。其余两种正式命令二选一，不同时启动。
/usr/bin/python3 run_capture.py --job config/diagnostic.json
# /usr/bin/python3 run_capture.py --job config/offline.json
# /usr/bin/python3 run_capture.py --job config/throughput.json
source /opt/ros/jazzy/setup.bash
/usr/bin/python3 tools/validate_capture.py /实际采集目录 --export-images
/usr/bin/python3 tools/analyze_trace.py /diagnostics_ref指向的诊断目录 --trace
/usr/bin/python3 -m unittest discover -s tests -v
/usr/bin/python3 tools/verify_project.py --originals
```

`throughput.json` 为离线 keepalive，当前默认 100 组；不要把它当短 smoke 直接启动。`smoke.json` 只选前相机，不适用于声称全传感器收益。验证和分析工具会写自己的报告，并非完全只读。

启用 ROS preview 后，在另一个终端：

```bash
/usr/bin/python3 launch_rviz.py --session /实际采集目录
```

Fixed Frame 为 world，分别勾选 PointCloud2 显示。取消显示不会停用 Isaac 传感器。DDS preview 可墙钟节流，MCAP 仍保存完整组。

### 输出与日志

采集目录含 `bag_unified/`、`capture_index.jsonl`、`writer_report.json`、session/job/registry/calibration 与来源证据；`diagnostics_ref.json` 指向 `runs/<run_id>/diagnostics`。安装变更与专门保存的快照在 `pose_adjustments/`，不应与 MCAP 或运行轨迹混为一类。

### 远端操作与部署注意

遵循本地 [cloud-instance-ops SKILL](C:/Users/15452/.codex/skills/cloud-instance-ops/SKILL.md) 及其 audited-tools。使用已配置 **isaac-new** 别名和审计包装器：

```text
C:/Users/15452/.codex/skills/cloud-instance-ops/scripts/ops.py
```

凭据在本机凭据管理中，连接会核对固定主机指纹和实例身份。不要从历史对话复制旧密码或连接已释放实例；本文不保存凭据。操作留 purpose/intent/task 日志，按工具真实写入声明 intent。不要启动未知外部下载、上传资产或改全局 preload；新需求遵循 skill 的实际规定。

`tools/make_deployment.py` 当前生成分批部署脚本 `generated/deploy_01.py` 等及 manifest，逐批执行/核验。审计脚本上限 256 KiB。**遗留 `generated/deploy.py` 为旧大脚本，不使用。** 新批次检查旧版哈希、保存被覆盖 v04 文件至 deploy_history、合并部署 manifest；不删除未知文件。不要上传全部 reports、原始审计数据或大输出。

回退：先停止本任务并排空，关闭 v04，再使用保留 v03 入口。不要通过广泛 pkill 或删目录回退；只操作确认属于本任务的 PID、start tick 和路径。原始 USD 未 Save，无须重装桌面或驱动。

## 11. 证据索引与复现定位

### 本地 / 已镜像项目文档

- [deployment_and_native_test.md](deployment_and_native_test.md)：公平吞吐、根因分类、正确性、警告与回退。
- [native_hotspots_and_depth_checks.md](native_hotspots_and_depth_checks.md)：原生 API 热点、CPU/GPU 阶段、几何真值、返回差异和图像。
- [implementation.md](implementation.md)、[verification.md](verification.md)：实现与验证说明。
- [原始优化 prompt](../docs/agent_deep_performance_optimization_prompt.md)：历史任务输入；基线以用户明确的 v03 为准。
- [performance_metrics.json](evidence/performance_metrics.json)、[native_direct_analysis.json](evidence/native_direct_analysis.json)、[native_final_analysis.json](evidence/native_final_analysis.json)。
- [final_gated_comparison.json](evidence/final_gated_comparison.json)、[final_throughput_comparison.json](evidence/final_throughput_comparison.json)。
- [frozen_depth.json](evidence/frozen_depth.json)、[mesh_comparison.json](evidence/mesh_comparison.json)、[analytic_depth.json](evidence/analytic_depth.json)、[analytic_baseline_depth.json](evidence/analytic_baseline_depth.json)。
- [controls.json](evidence/controls.json)、[controls_validation.json](evidence/controls_validation.json)、[portable_tests.txt](evidence/portable_tests.txt)。
- [native_timeline.png](evidence/native_timeline.png)、[final_images_comparison.jpg](evidence/final_images_comparison.jpg)：时间线存在上述覆盖限制；图像为缩略对照。

`reports/` 有更全的操作结果、采集元数据与最终部署核验，通常不全量镜像到远端。历史失败结果也保留，不要只选成功结果。

### 云端原始实验

均位于 `/root/gpufree-data/semantic/output/sensor_visualizer/v04/experiments/`：

| 用途 | 实验子目录 |
|---|---|
| 公平 v03 基线 | `20261009_131753_414163_final_single_dome_baseline_v03` |
| 最终 gated | `20261009_132344_396382_final_gated_v04` |
| 最终 keepalive | `20261009_132927_629284_production_throughput_v04` |
| 最终短原生追踪 | `20261009_134119_584925_native_final_throughput_v04` |
| 原生面板控制 | `20261009_133504_572690_production_controls_v04` |
| 冻结重复扫描 | `20261009_141049_092866_diagnostic_frozen_repeat_warm_v04` |
| 正确隔离解析箱 v04 | `20261009_142106_798350_diagnostic_isolated_box_checked_v04` |
| 正确隔离解析箱 v03 | `20261009_142620_693751_diagnostic_isolated_box_v03` |

每个实验保留 job/spec/process/supervisor 结果、Kit 日志、SDK 计时、采集目录；原生实验另有 nsys-rep/SQLite。采集会话实际路径从 `capture_result.json` 读取，不按日期猜测“最新”结果。

复现实验工具：`experiments/remote_start.py` 接受 runpy globals `VERSION/LABEL/GROUPS/NATIVE/JOB_EXTRA/SPEC_EXTRA`；公平 v03 设 `SPEC_EXTRA.single_hdr_dome=true`。原生追踪用 `direct_kit=true`、短 `profile_first/profile_last` 窗口。`supervise.py` 检查属于自己的进程，`probe_in_kit.py` 只在自己进程临时包装 SDK，finally 恢复。`compare_mcap.py` / `depth_validation.py` 用于图像、点云和几何对照。先阅读各工具再启动，不能把实验 monkeypatch 搬入生产 SDK。

## 12. 给接续 agent 的首条建议

如果用户要求继续完成原任务，先复核现状，再按第 9 节安排长任务验收、原生缓冲诊断与点云差异排查；用户指定其他优先级时随之调整。用户已经授权的范围内继续推进，不反复询问常规操作许可。若没有新的执行要求，本文就是交接产物，无需自动启动采集或变更实例。

汇报时分清：已部署能力、无追踪的实测性能、原生追踪推断、正确性通过项、仍失败的断言和未验证事项。当前可用结果是 **v04 已部署并有提速证据，深层瓶颈与逐点等价问题尚未完全解决**。
