# Semantic World Module v03：传感器配置化与 Path Tracing 稳定性排查方案

日期：2026-08-19  
阶段：仅排查与设计，不实现 v03 脚本  
基线：`scripts/260811_01semantic_worldModule_v02`

## 1. 结论先行

### 1.1 Path Tracing 问题不是单纯“性能低导致假死”

远端至少出现过一次明确的原生 GPU 崩溃：

- 任务在完成第 205 个数据帧后停止。
- `omni.rtx` 报告 `GPU crash is detected`。
- 紧接着报告 `GPU pagefault occured`，虚拟地址没有对应的已知分配。
- Isaac Sim 成功生成 `.nvdbg` 和 `.nv-gpudmp`。
- 日志没有 Python 异常栈，说明该次失败发生在 RTX/GPU 原生层，而不是普通 Python 死循环或 Writer 抛错。

因此，v03 不能只通过“增加 Python 超时”解决；需要降低 RTX 资源生命周期抖动，并在 Isaac Sim 进程外增加监督、分段、心跳和断点续跑。

### 1.2 第二次 Path Tracing 长跑属于另一类失败

后续重跑从 2026-08-17 14:51 持续到约 22:28，已经提交 4294 个数据帧，并在第 4295 帧的 `full_scene` 写出阶段被中断：

- 三个变体的已提交元数据均为 4294 份。
- `motion_state.jsonl` 为 4294 行。
- `.frame_staging/frame_4294/` 中留有下一帧的部分文件。
- `run_config.json` 仍为 `status: running`。
- 本次没有新的 `.nv-gpudmp`，日志中也没有 GPU crash/pagefault 或正常退出标记。

这更像进程、容器或算力实例被外部终止。现有日志不足以判断是人工停止、平台回收还是宿主机级中断，不能将它和第一次 GPU page fault 混为同一根因。

### 1.3 v03 的核心方向

v03 应从“一个语义相机调度器 + 主循环手写三个变体”升级为：

1. 配置加载器负责描述传感器实例、时钟、输出和渲染组。
2. 传感器注册表按 `type` 创建驱动，不让主调度器知道针孔、鱼眼或 LiDAR 的具体实现。
3. 帧协调器只负责时间、冻结世界、场景变体和事务提交。
4. 相机、RTX LiDAR 等分别实现统一生命周期接口。
5. 输出层处理通用 `SensorPacket`，不再假定恰好一个 RenderProduct。
6. Isaac Sim worker 外增加 supervisor，支持心跳、超时、进程重启、分段与断点续跑。

需要明确边界：

- 新增一个“已支持类型”的传感器实例，例如第 2、第 3 个针孔相机，应只改配置。
- 鱼眼相机在 v03 内置相机驱动支持后，新增实例也只改配置。
- RTX LiDAR 在 v03 内置 LiDAR 驱动支持后，新增型号/实例通过配置或传感器 USD 完成。
- 首次支持一种全新的物理传感器族仍需新增一个驱动插件，但不应修改主调度器、帧事务或现有相机链路。

## 2. 本次排查范围与证据完整性

本次只进行了只读排查，没有启动新的渲染任务，没有修改远端文件。

本地与远端以下 6 个关键文件 SHA-256 完全一致，说明远端事故可以直接映射到当前本地 v02：

- `semantic_capture_custom.py`
- `simulation_orchestrator.py`
- `semantic_dataset_writer.py`
- `capture_launch_config.py`
- `configs/capture_output0817_01_pathtracing_full_trajectory_three_variants.json`
- `configs/render_pathtracing_720p_64spp.json`

远端关键证据路径：

```text
/root/gpufree-data/semantic/scripts/260811_01semantic_worldModule_v02/logs/
  output0817_01_pathtracing_full_trajectory_three_variants_gpu_crash_20260817_123239.log
  output0817_01_pathtracing_full_trajectory_three_variants.log

/root/isaacsim/kit/logs/Kit/Isaac-Sim Python/6.0/
  kit_20260817_120901.log
  kit_20260817_120901-0.nv-gpudmp
  kit_20260817_120901-00007fe1358a4180-00007fe1894ec090.nvdbg
  kit_20260817_145120.log
```

对照组 `output0813_01_full_trajectory_three_variants.log` 使用 `RealTimePathTracing`，完整完成了 10190/10190 帧。这说明：

- 轨迹长度和确定性运动本身可以跑完。
- 三变体业务逻辑在实时 RTX 模式下至少有一次完整成功记录。
- 问题与 `PathTracing` 压力或其和 3DGS/变体切换的组合高度相关，但还不能仅凭现有证据断言是某一个 Carb 设置单独导致。

## 3. v02 当前链路与结构性限制

### 3.1 单相机假设写进了配置模型

`CaptureLaunchConfig` 直接拥有一组全局字段：

```text
camera_prim_path
width / height
rt_subframes
image_output_folders
```

它没有 `sensors[]`、传感器 ID、传感器独立频率或输出模态的概念。

对应源码：`capture_launch_config.py:592-620`。

### 3.2 调度器只拥有一个 Camera 和一个 RenderProduct

`SemanticCameraScheduler` 的职责被固定为：

- 验证一个 `UsdGeom.Camera` prim。
- 创建一个名为 `SemanticCapture` 的持久 RenderProduct。
- 创建一套固定 annotators。
- 同步调用一个 Writer。

对应源码：

- `semantic_capture_custom.py:46-89`
- `semantic_capture_custom.py:102-132`
- `semantic_capture_custom.py:145-173`

### 3.3 Writer 明确拒绝多个 RenderProduct

`SemanticDatasetWriter.write()` 在收到多个 RenderProduct 时直接报错：

```python
if len(render_products) != 1:
    raise RuntimeError(...)
```

对应源码：`semantic_dataset_writer.py:285-295`。

这意味着即使只增加第二个针孔相机，也必须改 Writer 和主链路，正是 v03 要消除的耦合。

### 3.4 主循环手写了业务变体顺序

每个数据帧当前依次执行：

1. `full_scene` 探测。
2. `full_scene` 正式采集。
3. `excavator_only` 探测。
4. `excavator_only` 正式采集。
5. `front_teeth_only` 探测。
6. `front_teeth_only` 正式采集。
7. 恢复 `full_scene` 并再次探测。

对应源码：`simulation_orchestrator.py:775-922`。

主循环同时知道变体、相机、Writer、语义验证和事务提交，新增传感器后会继续膨胀。

## 4. Path Tracing 事故分析

### 4.1 已确认事实

| 事实 | 证据 | 含义 |
|---|---|---|
| 第一次长跑在 205 帧后崩溃 | 运行日志最后完整帧为 205 | 不是启动失败 |
| RTX 报告 GPU page fault | `omni.rtx` 原生日志 | 不是普通 Python 异常 |
| 生成 GPU crash dump | `.nv-gpudmp`、`.nvdbg` | 可提交 NVIDIA 进一步解码 |
| 没有 OOM 文本 | 崩溃日志为 page fault | 不能简单归因于显存不足 |
| 同一配置重跑越过 205，达到 4294 | 第二次运行记录 | 不是确定性的“第 206 帧场景内容坏了” |
| RealTimePathTracing 完成 10190 帧 | 0813 对照日志 | PathTracing 或其压力组合是关键差异 |
| 第二次运行每个提交帧出现一次 hydratexture release 警告 | 共 4294 次 | RenderProduct/Hydra 生命周期存在持续告警 |
| 第二次 Kit 日志出现 47250 次 `Gaussian prim loaded` | 404 MB Kit 日志 | 变体切换造成大规模重复资源装载 |

### 4.2 单个数据帧的真实渲染负载

当前 Path Tracing profile：

- `/rtx/pathtracing/spp = 8`
- `/rtx/pathtracing/totalSpp = 64`
- `rt_subframes = 8`
- `settle_rt_subframes = 8`
- `settle_render_count = 1`

每个数据帧通常发生 7 次阻塞渲染，每次 8 个 RTX subframes，总计约 56 个 subframes。按 profile 的名义算法，每次输出目标为 64 spp；三个正式输出之外还有三个预探测和一次恢复探测。

对应源码：

- 阻塞渲染：`semantic_capture_custom.py:214-234`
- 每次变体切换重置 history：`simulation_orchestrator.py:202-231`
- history 通过增加 `/rtx/externalFrameCounter` 重置：`semantic_capture_custom.py:277-285`
- profile 的 spp 计算：`render_profile.py:280-298`

因此 10190 个业务帧不是 10190 次渲染，而是大约 71330 次阻塞 render step、570640 个 RTX subframes。高负载本身不等于 bug，但显著放大了驱动、SceneDB 和资源生命周期缺陷的暴露概率。

### 4.3 最可能的根因链

#### 高置信度：3DGS 可见性切换导致 RTX 资源频繁卸载/重建

当前顺序是“帧优先、变体次之”。每个数据帧都要反复切换全场景、挖掘机、前齿和全场景。远端日志显示高频 `Gaussian prim loaded`，说明可见性变化并非廉价的 mask，而会触发 Gaussian 资源重新进入 RTX SceneDB。

GPU page fault 地址没有关联到已知分配，更像陈旧 GPU 地址、资源释放后仍被引用或驱动/渲染器生命周期竞态，而不是有明确证据的容量型 OOM。精确到 NVIDIA 内部调用栈仍需使用 `.nv-gpudmp`/`.nvdbg` 和匹配版本符号分析，当前不能宣称已经定位到某一行 Isaac Sim 源码。

#### 高置信度：单一超长进程缺少故障边界

当前一次 worker 要完成 10190 帧。任何 GPU 崩溃、平台回收或进程异常都会使 `run_config.json` 留在 `running`，且 v02 没有从已提交帧继续的正式入口。第二次运行已经证明这类非 GPU crash 中断真实存在。

#### 中置信度：重复“探测 + 正式采集”使压力翻倍

探测已经经过真实 annotator 和 Writer 数据路径，只是不发布业务文件；紧接着又用相同冻结世界和相同变体正式渲染一次。若最后一次探测验证通过，可以考虑将其结果直接提升为正式事务，避免重复渲染。必须先验证语义新鲜度和 Path Tracing 累积质量，不应直接删掉探测。

#### 中置信度：配置存在不必要的压力放大项

- `maxVolumeBounces = 64` 对当前场景是否必要尚未证明。
- 单 GPU 机器的启动参数仍显示 `/renderer/multiGpu/enabled=True`。
- Kit 的 Info 级日志在 7.6 小时内增长到约 404 MB。

这些项未被证明是 page fault 的直接根因，但应该进入消融实验。

#### 低置信度：Python Writer 死锁

现有证据不支持把第一次失败归因于 Python Writer 死锁。第一次有明确原生 GPU crash；第二次日志在文件写出阶段突然终止且无 Python 栈。Writer 仍需要超时和心跳，但不是当前第一根因。

## 5. 下一阶段的最小实验矩阵

不要直接再次发起 10190 帧全量任务。先用同一场景、同一轨迹和固定随机种子做逐层消融，每组至少重复 3 次，因为第一次在 205 帧崩溃、第二次却能到 4294，问题具有非确定性。

| 实验 | 渲染 | 场景/变体 | 输出 | 目的 |
|---|---|---|---|---|
| E0 | PathTracing | 简单 mesh、full_scene | RGB | 验证基础 PT/驱动 |
| E1 | PathTracing | 当前 3DGS、full_scene | RGB | 隔离 3DGS 基础压力 |
| E2 | PathTracing | 当前 3DGS、full_scene | RGB + semantic | 隔离 annotator 组合 |
| E3 | PathTracing | 三变体，变体优先执行 | RGB + semantic | 验证减少反复切换 |
| E4 | PathTracing | 三变体，帧优先执行 | RGB + semantic | 当前模式对照 |
| E5 | RealTimePathTracing | 三变体，帧优先执行 | RGB + semantic | 已知成功模式复核 |

每组分三道门：

1. 3 × 500 帧。
2. 1 × 5000 帧。
3. 1 × 10190 帧，并主动在中途终止一次验证恢复。

必须采集的指标：

- 每个阶段的开始/结束心跳：physics、variant transition、render、annotator read、writer、commit。
- GPU 显存已用/保留、GPU 利用率、温度、功率。
- 进程 RSS、线程数、文件描述符数。
- 每帧耗时及 p50/p95/p99。
- `Gaussian prim loaded`、hydratexture release、RTX warning/error 的累计计数。
- 当前帧、变体、sensor_id、render_group、事务目录。

实验变量一次只改一个：

- `frame_major` 与 `variant_major`。
- semantic annotator 开/关。
- `reset_render_history` 开/关或仅在必要切换时调用。
- spp/subframes 组合。
- `maxVolumeBounces`。
- 显式 `multi_gpu=false`。
- 详细日志级别与日志轮转。

## 6. v03 配置模型草案

以下 JSONC 仅用于定义边界，不是本阶段要落地的最终 schema：

```jsonc
{
  "schema_version": 6,
  "scene": {
    "usd": "/path/to/scene.usda",
    "physics_hz": 60,
    "trajectory": "/path/to/trajectory.csv"
  },
  "render_groups": {
    "camera_pt": {
      "kind": "camera_rtx",
      "profile": "render_pathtracing_720p_64spp.json",
      "execution": "serial",
      "multi_gpu": false
    },
    "lidar_rtx": {
      "kind": "rtx_sensor",
      "execution": "serial",
      "multi_gpu": false
    }
  },
  "sensors": [
    {
      "id": "boom_front",
      "type": "camera.pinhole",
      "enabled": true,
      "source": {
        "mode": "existing_prim",
        "prim_path": "/Excavator/boom/Camera"
      },
      "render_group": "camera_pt",
      "clock": {"hz": 10, "phase_seconds": 0.0, "acquisition": "snapshot"},
      "resolution": [1280, 720],
      "modalities": ["rgb", "semantic_segmentation"],
      "output": {"sink": "semantic_dataset", "required": true}
    },
    {
      "id": "boom_fisheye",
      "type": "camera.fisheye_opencv",
      "enabled": true,
      "source": {
        "mode": "create",
        "parent_prim": "/Excavator/boom",
        "prim_name": "Fisheye"
      },
      "render_group": "camera_pt",
      "clock": {"hz": 10, "phase_seconds": 0.0, "acquisition": "snapshot"},
      "resolution": [1280, 720],
      "calibration": {
        "model": "opencv_fisheye",
        "intrinsics": [0, 0, 0, 0],
        "distortion": [0, 0, 0, 0]
      },
      "modalities": ["rgb", "semantic_segmentation"],
      "output": {"sink": "semantic_dataset", "required": true}
    },
    {
      "id": "roof_lidar",
      "type": "lidar.rtx.rotary",
      "enabled": true,
      "source": {
        "mode": "create",
        "parent_prim": "/Excavator/roof",
        "config": "HESAI_XT32_SD10"
      },
      "render_group": "lidar_rtx",
      "clock": {"hz": 10, "acquisition": "interval"},
      "scan": {"accumulate_outputs": true, "aux_output_level": "BASIC"},
      "modalities": ["point_cloud", "range", "intensity"],
      "output": {"sink": "pointcloud_dataset", "required": true}
    }
  ],
  "capture": {
    "frames": 10190,
    "variant_execution": "variant_major",
    "variants": ["full_scene", "excavator_only", "front_teeth_only"],
    "snapshot_groups": [
      {
        "id": "camera_sync",
        "sensor_ids": ["boom_front", "boom_fisheye"],
        "commit_policy": "all_or_nothing"
      }
    ]
  },
  "runtime": {
    "chunk_frames": 500,
    "resume": true,
    "heartbeat_seconds": 5,
    "stage_timeout_seconds": 120,
    "render_timeout_seconds": 180,
    "max_worker_restarts": 3,
    "log_rotation_mb": 100
  }
}
```

### 6.1 为什么使用 render group

`SimulationApp` 的 renderer 和很多 RTX Carb 设置是进程级/全局状态，不应假装成每个传感器都能独立切换。因此：

- 使用相同 renderer/profile 的多个相机可以处在一个 camera render group。
- 不同 profile 或生命周期冲突的传感器应拆到不同 group，必要时由不同 worker 进程执行。
- PathTracing 相机和 RTX LiDAR 初期建议进程隔离，先保证稳定性，再评估是否安全合并。

### 6.2 鱼眼相机的模型选择

Isaac Sim 6 推荐使用 `OmniLensDistortionOpenCvFisheyeAPI`，而不是继续把所有鱼眼都近似成旧的 `fisheyePolynomial`。配置应保存：

- 模型名。
- 图像尺寸。
- 内参矩阵。
- 畸变系数。
- 外参和单位。
- 校准版本/哈希。

Isaac Sim 6.0 对任意 LUT 畸变模型有已知限制，因此第一版优先支持原生 OpenCV pinhole/fisheye schema。

### 6.3 旋转 LiDAR 不能套用“冻结世界的一张图片”语义

针孔/鱼眼相机是瞬时 `snapshot`；旋转 LiDAR 的一帧通常覆盖一个扫描时间区间，需要在物理时间推进中积累。v03 的时钟模型必须区分：

- `snapshot`：在同一冻结世界状态读取多个相机。
- `interval`：记录 `scan_start_time`、`scan_end_time`、参考时间和运动补偿策略。

RTX LiDAR 的 `tick_rate` 必须和 `scanRateBaseHz` 一致，否则可能静默地产生不完整扫描，不能只复用相机的 `capture_fps`。

## 7. v03 核心模块与接口

```text
RunConfig
   |
   v
ConfigLoader -- schema/引用/能力/时钟预校验
   |
   v
SensorRegistry ---- type -> SensorFactory
   |                         |
   |                         +-- PinholeCameraDriver
   |                         +-- FisheyeCameraDriver
   |                         +-- RtxLidarDriver
   v
CaptureCoordinator <---- TimelineScheduler
   |       |
   |       +---- SceneVariantProvider
   |       +---- RenderGroupManager
   v
SensorPacket(s)
   |
   v
FrameTransaction ---- OutputSink(s) ---- Manifest/Ledger

进程外：RunSupervisor ---- heartbeat/watchdog/restart/resume/crash artifacts
```

### 7.1 SensorDriver

概念接口：

```python
class SensorDriver(Protocol):
    sensor_id: str
    capabilities: SensorCapabilities

    def preflight(self, stage, spec) -> PreflightReport: ...
    def initialize(self, runtime_context) -> None: ...
    def warmup(self) -> None: ...
    def capture(self, request: CaptureRequest) -> SensorPacket: ...
    def health(self) -> SensorHealth: ...
    def close(self) -> None: ...
```

主协调器只依赖该接口。注册表使用受控 allowlist/entry point，不允许配置文件任意导入 Python 路径，以保证安全和可复现。

### 7.2 SensorPacket

所有驱动输出统一元数据，不强迫所有数据都是图片：

```text
run_id
capture_id
sensor_id
sample_id
variant_id
timestamp / interval_start / interval_end
frame_id / physics_step
calibration_hash
modalities
payload descriptors
validation result
render/driver metrics
```

### 7.3 OutputSink

把 Writer 从“相机调度器内部对象”拆出：

- `SemanticImageSink`
- `PointCloudSink`
- `MetadataSink`
- 可选 ROS/消息输出 sink

现有语义映射、语义内容验证、原子 staging/commit 能继续复用，但必须删除“恰好一个 RenderProduct”的全局假设，并把路径命名改为包含 `sensor_id`。

推荐目录：

```text
output/
  run_manifest.json
  ledger.jsonl
  calibration/<sensor_id>.json
  sensors/<sensor_id>/<variant>/<modality>/...
  metadata/<sensor_id>/<variant>/...
  .transactions/<capture_id>/...
```

### 7.4 CaptureCoordinator

协调器只做 5 件事：

1. 从 TimelineScheduler 接收本次到期的 sensor events。
2. 对 snapshot group 冻结一次权威世界状态。
3. 请求 SceneVariantProvider 准备目标变体。
4. 调用到期的 SensorDriver。
5. 按 commit policy 原子提交或全部回滚。

不在协调器中出现 `if fisheye`、`if lidar` 或第 N 个相机的分支。

## 8. Path Tracing 稳定性设计

### 8.1 优先采用 variant-major

当前是：

```text
frame 0: full -> excavator -> teeth -> full
frame 1: full -> excavator -> teeth -> full
...
```

PathTracing 推荐改为：

```text
pass 1: full 的全部帧
pass 2: excavator 的全部帧
pass 3: teeth 的全部帧
```

利用已有的权威轨迹/根姿态回放，以 `frame_id + dataset_time + state_hash` 配对三个 pass。这样每个进程/分段只切换一次主要可见性集合，避免每帧重新装载大量 Gaussian prim。

代价是三变体不再在同一 Isaac 进程的同一事务中产生，因此需要后置 pair manifest 检查三者的状态哈希一致。对于当前已记录的确定性轨迹，这一代价通常小于持续 GPU 资源抖动的风险。

保留 `frame_major` 作为严格同进程配对模式，但不作为 PathTracing 默认值。

### 8.2 将“验证通过的探测”提升为正式结果

目标不是盲目删除 settle，而是：

1. 变体切换后渲染到目标 spp。
2. 读取真实 annotator 数据并验证。
3. 若通过，直接将当前 payload 写入 staging 并提交。
4. 若失败，重置/重连后重试。

这样通常每个变体只需要一次成功渲染，而不是成功探测后再无条件重复正式渲染。该优化必须用图像哈希、语义新鲜度和 spp 统计做回归验证。

### 8.3 分段 worker 和断点续跑

建议每 300～500 个数据帧主动结束 Isaac Sim worker，由 supervisor 启动下一段：

- 限制长生命周期资源泄漏/碎片化。
- 每段产生独立 Kit 日志和资源指标。
- GPU crash 后只重跑未提交 segment。
- 进程退出可以释放所有 RTX 原生资源，而不是依赖不确定的 in-process recovery。

恢复条件必须严格：

- 配置 fingerprint 相同。
- USD、轨迹、mapping、render profile 和传感器校准哈希相同。
- 已提交 capture transaction 文件完整。
- 未提交 staging 自动隔离或清理。
- 从 ledger 的下一个 capture_id 继续，禁止覆盖已提交数据。

### 8.4 进程外 watchdog

`rep.orchestrator.step(wait_for_render=True)` 位于原生调用中；GPU 故障时 Python 线程不一定能及时抢回控制权。watchdog 必须在 Isaac worker 进程外：

- worker 每个阶段更新原子 heartbeat 文件。
- supervisor 检查 heartbeat 年龄和当前阶段超时。
- 超时后保存日志、`nvidia-smi`、当前事务和进程栈信息。
- 先 TERM，宽限期后 KILL。
- 新进程启动前确认旧进程退出和 GPU 上下文释放。
- 重启次数超限后标记 run 为 `failed`，不能永久自动重启。

### 8.5 崩溃分类

manifest 至少区分：

- `python_exception`
- `writer_failure`
- `render_timeout`
- `gpu_crash_dump_detected`
- `worker_signal_exit`
- `supervisor_killed_stale_worker`
- `host_or_container_interrupted`
- `user_cancelled`

这可以避免把所有问题都称为“卡住”。

## 9. 分阶段实现建议

### 阶段 A：先建立诊断与恢复底座

- 冻结 v02 基线和远端事故证据索引。
- 增加阶段心跳、GPU/进程指标和日志轮转。
- 增加 segment、ledger、resume 和 supervisor。
- 执行第 5 节消融矩阵。

完成标准：即使主动杀死 worker，也能从最后一个完整事务继续；GPU page fault 能被明确分类并保留 dump。

### 阶段 B：建立配置与注册表，但先保持单相机结果等价

- 引入 schema v6、`sensors[]`、render groups、clock 和 output sink 配置。
- 引入 SensorRegistry、SensorDriver、SensorPacket。
- 用 `camera.pinhole` adapter 包装现有单相机实现。
- 建立 v02 配置到 v03 配置的迁移器或兼容加载层。

完成标准：同一输入下，单相机 v03 的帧数、时间戳、语义 ID、目录内容和相机状态与 v02 对齐。

### 阶段 C：多相机与鱼眼

- 支持任意数量针孔相机实例。
- 支持 OpenCV fisheye schema 和校准元数据。
- 同步组共享一次 frozen world snapshot。
- 评估多个 RenderProduct 同步 step、顺序 step 和 tiled camera 三种策略。

完成标准：新增第 2、第 3 个相机只改 JSON；主协调器无相机数量分支。

### 阶段 D：RTX LiDAR

- 新增独立 `RtxLidarDriver`。
- 使用 interval acquisition、scan rate、积累和运动补偿元数据。
- 默认与 PathTracing camera render group 进程隔离。
- 点云 sink 与相机 sink 分离。

完成标准：新增已支持 LiDAR 型号只改配置；完整扫描的点数、时间区间和 tick rate 可验证。

### 阶段 E：PathTracing 生产化

- 默认 `variant_major`。
- 验证并启用“validated capture promotion”。
- 完成 3 × 500、1 × 5000、1 × 10190 稳定性门槛。
- 对比图像质量、耗时、GPU 指标和 warning rate。

## 10. v03 验收标准

### 配置化

- 增加一个针孔相机实例只改配置。
- 增加一个鱼眼相机实例只改配置。
- 增加一个已支持的 RTX LiDAR 实例/型号只改配置或引用新的传感器 USD。
- 未注册 `type` 在 Isaac Sim 启动前失败，并给出可用类型列表。
- 所有 `sensor_id`、输出路径和时钟冲突在启动前验证。

### 同步与数据契约

- snapshot group 的相机共享同一 `capture_id`、dataset time 和 world state hash。
- interval sensor 明确记录开始/结束时间，不能伪装成相机瞬时帧。
- 每个输出都可追溯到配置、校准、USD、轨迹和 render profile 哈希。
- required sensor 任一失败时，本组事务不产生半提交数据。

### 稳定性

- 3 次连续 500 帧 PathTracing 消融测试无 GPU crash。
- 5000 帧测试无未解释停顿，显存/RSS/文件描述符趋势可审计。
- 完整 10190 帧任务可以在主动中断后恢复，不重复、不漏帧。
- worker 异常终止后 manifest 不长期停留在含糊的 `running`。
- Kit 日志受轮转控制，不再由单次任务产生数百 MB 无界日志。

### 质量与性能

- 目标 spp 的计算和有效值写入 manifest。
- semantic segmentation 不出现前一变体的陈旧数据。
- `variant_major` 三个 pass 的 world state hash 完全配对。
- 与 v02 RealTimePathTracing 基线相比，语义 ID 映射和目录业务含义不退化。

## 11. 当前不应做的事情

- 不要直接在 `simulation_orchestrator.py` 中继续添加 `if lidar`、`if fisheye`。
- 不要为每个新相机复制一套 `SemanticCameraScheduler` 和 Writer 分支。
- 不要把相机 `capture_fps` 直接复用为旋转 LiDAR 的完整扫描频率。
- 不要只在 Python 线程内实现渲染超时后继续复用同一个 GPU 上下文。
- 不要在没有 resume/segment 的情况下再次长跑 10190 帧 PathTracing。
- 不要把第一次 GPU page fault 和第二次无退出标记的中断合并成一个模糊的“卡死”。

## 12. NVIDIA 官方实现依据

- [多相机 annotator/Writer 示例](https://docs.isaacsim.omniverse.nvidia.com/latest/replicator_tutorials/tutorial_replicator_isaac_snippets.html)：官方示例支持多个 Camera/RenderProduct，说明 v02 的单 RenderProduct 限制是项目实现限制，不是 Replicator 必然限制。
- [Camera Sensors](https://docs.isaacsim.omniverse.nvidia.com/latest/sensors/isaacsim_sensors_camera.html)：Isaac Sim 6 推荐 `CameraSensor`/`TiledCameraSensor`，并提供原生 OpenCV pinhole/fisheye schema。
- [RTX Lidar Sensor](https://docs.isaacsim.omniverse.nvidia.com/latest/sensors/isaacsim_sensors_rtx_lidar.html)：LiDAR 具有独立 tick、scan accumulation 和 GenericModelOutput 语义；文档也要求谨慎处理 multi-GPU。
- [RTX Interactive Path Tracing](https://docs.omniverse.nvidia.com/materials-and-rendering/latest/rtx-renderer_pt.html)：`spp` 是每个 render frame 的 samples per pixel，`totalSpp` 是累积上限。

## 13. 建议的下一决策

建议下一开发阶段按以下顺序启动：

1. 先实现 supervisor + segment + resume + heartbeat。
2. 同时完成 E0～E5 消融，确认 `variant_major` 是否显著降低 Gaussian 重载和 GPU crash 风险。
3. 再建立 v03 配置模型和 `camera.pinhole` 等价适配器。
4. 等单相机 v03 通过等价性和 PathTracing 稳定性门槛后，再加入多相机、鱼眼和 RTX LiDAR。

这个顺序能把“架构升级”和“GPU 原生稳定性”拆成可验证的小步，避免新增传感器后再难以判断崩溃来自哪一层。
