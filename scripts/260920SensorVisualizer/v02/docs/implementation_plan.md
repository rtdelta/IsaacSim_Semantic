# Sensor Visualizer 顺序采集与并行后端完整实现方案

日期：2026-09-23。本文保留实施前的设计基线，模块名和目录是当时的拟定接口。实际交付为独立 `v02` 子项目，使用方式见 `../README.md`，已验证行为、与设计的差异及剩余限制见 `verification.md`。

## 1. 已确定的目标与范围

- 同一组数据按运动到位、冻结、预热、采集、取得独立结果的顺序生成。采集期间场景状态不变、仿真时间不推进。
- 当前只支持 Instant LiDAR；现有场景为四路鱼眼和十三路雷达，数量来自发现结果，不写死。
- 交互预览 RTF 不高于 0.1；用户已授权离线采集取消墙钟限速。取消限速不改变仿真采样频率、运动速度单位或传感器模型。
- 保留三个关节/整机运动模式、传感器位姿调整、调整日志和显式位姿快照功能。离线任务读取显式保存的任务快照，不需要把临时安装位姿永久写入资产。
- 以当前 TF、光学坐标、点云局部坐标和 ROS 消息接口为兼容基线。
- 修复项目能够修复的 warning，定位其余警告的来源和影响。建立可复现的 3DGS 画质对照。
- 使用现有项目目录增加独立采集核心和无界面入口。旧入口在新路径验收前可用；本次不要求修改旧 USD。

本地项目：`D:/learning/IntelligentDepartment/CodesSet/Self/260707IsaacSIm/scripts/260920SensorVisualizer`

远端项目：`/root/gpufree-data/semantic/scripts/260920SensorVisualizer`

输出根目录：`/root/gpufree-data/semantic/output/sensor_visualizer`

## 2. 架构与运行环境

### 2.1 控制与采集

交互入口继续使用 Script Editor 面板；离线新增常驻 headless Kit 入口。两者调用同一个 CaptureCoordinator；同一次任务只允许一个控制器修改 stage、推进时间和提交渲染。离线入口读取已冻结的任务配置及挂载位姿，启动后不依赖 UI 回调。

推荐进程边界：

1. Isaac 自带环境的 Kit 进程：资产加载、运动、PhysX/USD/Fabric 同步、全部 Render Products、采集调度、GPU 读回与不可变帧快照。
2. 现有系统 ROS 环境的记录进程：局部 IPC 接收、编码工作池、ROS 消息构造、单一 MCAP writer、可选 RViz 发布。
3. 现有轻量资源采样进程：记录 CPU/内存、整卡 GPU 指标及控制器心跳。

不把系统 ROS Python 包强行装进 Isaac 解释器。记录端先复用已验证的 rosbag2_py、rclpy.serialization、消息包、Pillow 和 NumPy；实际启动前核对它们所在的解释器。

### 2.2 IPC 与并行

大数组优先通过本机共享内存槽传递，控制信息使用有长度边界及协议版本的本地 socket 消息。只绑定本机，目录/端点限制到任务用户；不开放网络服务。跨不同 Python 版本的共享内存所有权和 resource tracker 行为需专门验证，必要时采用明确拥有者管理的本地 mmap 文件。

槽位由单一拥有者创建和释放。描述符包含 job_id、group_id、槽号、世代号、offset、nbytes、dtype、shape、stride、各传感器元数据；边界校验通过才读取。消费方确认不再持有视图后发送释放确认，防止下一组覆盖仍在使用的数据。不得使用来自未验证来源的 pickle 或执行型消息。

初始使用三组原始数据槽和四个图像编码线程，并对照两个线程。四路 1920×1080 RGBA 每组约 31.6 MiB，三组约 95 MiB；另计点云、GPU 缓冲、编码结果和副本。原始槽与已编码队列分别有字节上限。线程池速度不足时再比较独立编码进程，进程使用独立启动方式，不 fork Kit 图形上下文。

单 GPU 先运行一个采集 Kit，共享加载后的场景。多个 Render Products 交给同一次调度处理，不为每台传感器启动一个 Kit。未来多 GPU / 多实例按轨迹片段分片，每个工作者生成完整传感器组；在同一 GPU 上多 Kit 是否更快单独实测。

## 3. 模块和代码改造范围

| 拟定模块 | 主要职责 | 现有代码处理 |
|---|---|---|
| capture/contracts.py | JobSpec、SensorRegistry、FrameBundle、状态及 IPC 协议 | 新增，不依赖 Isaac |
| capture/trajectory.py | 绝对仿真时间到姿态；三种运动模式和事件 | 提取 joint_control/base_control/motion_profile 中可复用数学逻辑 |
| capture/scene_stepper.py | 控制时钟、应用姿态、提交变换、冻结状态 | 封装 articulation_motion 与 reference_frames，替换离线 OnPlaybackTick 驱动 |
| capture/coordinator.py | 唯一组调度、预热、超时、组完整性、停止 | 从 runtime.py 拆出采集职责 |
| capture/sensor_drivers.py | 相机/Instant LiDAR 的统一 attach/read/close 接口 | 复用 camera_capture 标定/渲染姿态验证，新增原生点云获取适配 |
| capture/render_profile.py | 渲染配置、实际值快照、加载检查与预热策略 | 复用 render_lease，验证后新增 |
| capture/buffers.py | 槽位、容量、复制完成、IPC 生命周期 | 新增 |
| capture/record_worker.py | 编码、ROS 序列化、单 writer、可选发布 | 复用 unified_bag 消息构造和验证，替换正式路径事后合包 |
| capture/diagnostics.py | 分阶段耗时、警告分类、心跳、任务结果 | 扩展 performance.py |
| run_capture.py | 无界面任务启动和退出码 | 新增入口 |
| tools/validate_capture.py | ROS bag 回读、组索引、图像/点云/TF 一致性 | 复用已有验证工具 |

保留 discovery.py 的自动雷达发现。相机保持 front/back/left/right 标识；启动后固定本任务的 ID、prim、topic、frame_id 对照。中途新增、删除、重命名传感器需结束当前任务并重新发现，避免数据接口在一包中无记录变化。

旧 cloud_rate/ScanRateGate 不再决定离线采集节拍；新时钟直接决定目标采样组。旧 camera_rig 的同步 PNG 文件写入退出采集关键路径。旧 recording/unified_bag 保留作为历史数据兼容工具。

## 4. 数据契约与时间轴

### 4.1 JobSpec

任务至少包含：schema_version、job_id、场景路径与版本指纹、仿真起点、采样率、采样组数量或结束时间、传感器清单、初始姿态、运动计划、安装位姿快照、渲染配置、输出位置和性能配置。

会话开始时保存一次完整设置及渲染实际值；帧级数据进入追加式索引，避免每次重写不断膨胀的 session.json。素材指纹优先复用既有清单；只重新校验变化的依赖，不在每组做全资产扫描。

### 4.2 三种运动方式

- 直接角度：在指定组边界一次应用目标值；随后帧保持该值。
- 目标角度和角速度：按仿真时间解析计算或按固定物理步积分，达到目标后钳制到目标，不越界。
- 上下限和角速度周期运动：默认匀速往返，端点切换方向；保存初始位置和相位，允许从采样序号重建状态。

整机平移、Yaw/Pitch/Roll、Z 高度沿用当前坐标和旋转约定，在内部统一处理旋转表示。cab-track 保持当前约束。修改参数只在组边界生效，记录 command_id/config_revision；离线任务默认使用不可变运动计划。

规定运动可尝试直接求目标姿态，跳过中间图像渲染；必须先验证 Articulation、PhysX 与 3DGS 绑定在绝对定位下正确更新。验证前使用确定性的固定物理步推进。存在真实动力学时不能跳过必要积分。

### 4.3 仿真时间、源时间与墙钟

第一版多传感器使用共同 10 Hz 仿真采样网格，例如 0.0、0.1、0.2 秒。group_id 和整数纳秒是唯一公共索引；一般有理数频率直接由整数帧号计算，不累计浮点 dt。

每组保存计划时间、Isaac/传感器源时间、渲染帧标识（如果接口提供）、提交与完成的墙钟时间。ROS header 和 bag 记录时间使用经验证的采样仿真时间；UTC 仅作运行审计。

采集前、必要预热后、最终采集后验证仿真时钟未推进；timeline 与 IsaacReadSimulationTime 不能假定天然相等，需要 ClockAdapter 验证。浮点转整数的微小舍入误差可在明确阈值内归一化，并保留源时间。不能把缓存中的旧结果重新盖章作为新采样。

交互 RTF 的墙钟等待在完整组之间执行；离线不等待墙钟。四相机、所有雷达、TF、JointState 和根位姿属于同一组。预热可能执行多次渲染，但不多生成数据组或 /clock 消息。

## 5. 逐组状态机

状态：INITIALIZING → READY → ADVANCING → FROZEN → WARMUP → CAPTURING → SNAPSHOT_READY → QUEUED。后台状态：ENCODING → WRITING → WRITTEN；最终分段关闭后标记 FINALIZED。暂停、排空、失败和关闭为显式分支。

单组执行顺序：

1. 预留空槽；没有容量则暂停产生下一组，同时保持交互事件可响应。
2. 计算 t_k 与目标运动，应用整机/关节/允许的挂载更新。
3. 同步 PhysX、USD/Fabric 和渲染场景，停止运动控制回调，冻结场景版本与仿真时间。
4. 检查启动加载状态；按渲染配置执行零 delta-time 的必要预热。预热不落盘。
5. 一次组级采集调度覆盖已注册 Render Products。引擎内部是否并行执行由后端决定，不为每个产品各推进一次时间。
6. 等待渲染结束，读取本次相机 RGB、CameraParams、传感器时间和 Instant LiDAR 数据；验证新结果与当前姿态对应。
7. 在同一冻结状态快照全部 TF、相机标定版本、关节状态和根位姿。
8. GPU 结果完成读回，复制到独立槽，形成不可变 FrameBundle。确定此后没有采样任务仍读取可变场景。
9. 交给记录进程后可以开始下一组；后台完成编码和按序写入。

任何必需传感器缺失或结果陈旧时不提交整组。区分“合法无回波点云”和“没有收到传感器结果”；不能把任意零点数视为驱动失败。

当前 CameraCapture.receive 中 is_playing 判断、OnPlaybackTick 发布图、Motion 回调及时间门控必须改为受协调器控制。所有后台线程禁止读取实时 USD 位姿或改变 stage。

## 6. 第一个技术验证关口

先用一相机和一台 Instant LiDAR、现有场景与已知几何靶标完成：

- 暂停时间轴下，rep.orchestrator.step(delta_time=0, pause_timeline=True, wait_for_render=True) 能产生新相机与新雷达结果。
- 同一姿态多次预热不会推进仿真时间、不会重复计入组。
- 切换已知姿态后，相机渲染矩阵、点云靶标位置、TF 和源时间对应，不能只验证时间戳相等。
- 确认原生雷达输出字段、单位、坐标系、强度语义及时间。复用 v04 的 CUDA annotator 思路，不复用其连续扫描历史窗口假设。
- 不能确认点云是新姿态结果时，停止该路径验收并修正传感器触发/读回适配，不偷偷恢复运动中采集。

通过后依次扩展四相机、全部雷达；接口验证完成前不承诺所有原生传感器可直接共用同一个暂停调用。

## 7. 渲染质量与资源就绪

当前文件配置是 RealTimePathTracing / DLSS Performance，但旧会话没有记录所有运行时实际值。新 render_profile.json 同时保存请求值和实际读取值：渲染模式、AA/DLSS、采样/子帧、曝光、景深、运动模糊、分辨率、鱼眼参数、Motion BVH、相关 RTX 设置、软件版本及素材清单。

首选正式采集候选为 RT2 Quality；对照候选为原生分辨率 AA 与 Interactive PT。先做同姿态质量/吞吐对照，再选默认值。子帧数不等于 PT 的 samples-per-pixel。保持现有鱼眼模型、标定和 PNG 无损编码，性能基准时不暗中降低分辨率、采样频率或雷达射线数。

就绪判断分层：USD 引用加载结束、所需资源无明确失败、渲染输出完成、固定姿态输出稳定。没有通用的“3DGS 一定已就绪”布尔接口保证；使用已安装版本可用的完成信号和受控预热对照，超时报告缺口，不以睡眠若干秒代替检查。

最小对照：固定姿态、光照、曝光和随机种子（若接口支持），比较 1/4/16 个子帧；随后对比 Performance/Quality/原生 AA；必要时加入 PT 参考。重启或清理历史的方式必须使用受支持接口，不能拿上一配置留下的历史直接比较。原生渲染可能存在噪声，图像稳定用容差/区域指标，不要求逐字节相同。

再隔离 3DGS、普通 Mesh、各个地面背景，对比相同视角的源素材参考。若局部涂抹在充分预热和高质量配置下仍存在，则继续检查训练覆盖、Gaussian 尺度/旋转/透明度、背景重叠；这些结论不能由单张截图判定。首轮预热与每次姿态变更后的历史收敛分别配置，不能因启动预热完成就假定后续跳转无伪影。

## 8. MCAP、TF 与兼容性

记录端使用已有 rosbag2_py.SequentialWriter，storage_id=mcap，rclpy.serialization.serialize_message。保持以下接口：

| 话题 | 类型/内容 |
|---|---|
| /lidar/<id>/points | sensor_msgs/PointCloud2，保留当前字段、局部坐标、单位和 frame_id |
| /camera/<front|back|left|right>/image_raw/compressed | sensor_msgs/CompressedImage，原始鱼眼 RGB PNG |
| /camera/<id>/camera_info | sensor_msgs/CameraInfo，equidistant、K、D；不声称图像已去畸变 |
| /camera/<id>/pose | geometry_msgs/PoseStamped，世界系光学位姿 |
| /tf | tf2_msgs/TFMessage，采样时刻的变换 |
| /clock | rosgraph_msgs/Clock，每个采样组的仿真时间 |
| /joint_states | sensor_msgs/JointState，实际读取的关节位置，未采集的速度/力矩不伪造 |
| /excavator/root_pose | geometry_msgs/PoseStamped，沿用当前定义 |
| /sensor_visualizer/camera_metadata | std_msgs/String JSON，兼容现有标定元数据 |
| /sensor_visualizer/frame_index | 新增 std_msgs/String JSON，组号、传感器清单、配置版本、源时间和姿态验证结果 |
| /sensor_visualizer/run_metadata | 新增 std_msgs/String JSON，任务、实际渲染配置与版本 |

保留现有 world → swing_horizontal_coordinate → swing_coordinate → sensor/optical 的语义，实际 parent 以当前注册表和资产契约为准。传感器不能同时有两个 TF parent；预览发布端与旧图不能同时发布相同边。采集始终计算完整变换，只有确定不会变化的边才考虑 /tf_static。相机 USD 轴 X右/Y上/-Z前，光学轴 X右/Y下/Z前；序列化时完成一次正确转换。四元数 xyzw。

采集组消息在单 writer 内有确定的写入顺序。frame_index 最后写入，旁路索引区分 WRITTEN 和 FINALIZED；writer.write 返回或组标记存在不代表断电持久化。第一版用有限大小/时长分段，关闭并回读分段后确认 FINALIZED。崩溃后从最后完整关闭段恢复，当前未完成段保留诊断；不直接追加到可能损坏的尾部。不承诺 MCAP 提供跨话题原子事务。

每个分段开头重复必要标定/运行元数据与静态 TF（如有）。标准 ros2 bag info/play 必须验证。使用官方 bag writer 生成元数据，避免手工拼 metadata.yaml 造成兼容偏差。

输出拟定为：

```
<session>/
  session.json              # 固定配置摘要和状态
  job_spec.json             # 可复现的任务计划
  sensor_registry.json      # ID/prim/topic/frame 对照
  render_profile.json       # 请求及实际渲染设置
  bag_unified/              # MCAP 与 ROS bag 元数据
  capture_index.jsonl       # 追加式组索引、分段与完成状态
  events.jsonl              # 控制、调整、警告与失败
  performance/              # 阶段计时、资源和汇总
  validation.json           # 回读及一致性报告
  pose_snapshots/           # 用户显式保存的安装位姿
  exports/                  # 可选离线 PNG/点云导出
```

预览使用独立输出队列，可只保留最新完整显示组；它不影响记录队列。RViz 以 use_sim_time 使用随该显示组发送的时钟与 TF，不能先将 /clock 推到未来再发布旧组。离线任务可比墙钟更快，预览可降频。关闭 RViz 不应减少 MCAP 数据。

## 9. 交互、停止与恢复

新增面板项：运行模式、采样率、时长/组数、渲染配置、保存任务、开始采集、暂停/继续、停止并完成写入。已有运动和安装位姿面板继续使用。

交互操作在采集组边界接纳。安装位姿调整进入现有调整流程时，完成当前组后暂停采集；恢复后增加配置版本并重新做必要预热。挂载调整日志始终保存；显式保存位姿才生成可复用快照。Stop/关闭时沿用恢复初始挂载的现有规则，后台只处理已冻结的旧快照。

离线流程：在交互场景配置运动、位姿和传感器 → 保存任务快照 → 退出或暂停占用同一 GPU 的交互 Kit → 用拟新增 run_capture.py 执行任务 → 查看可选 RViz 预览 → 完成后直接得到 bag_unified，无需再合包。

暂停：停止接纳新组，当前组完成，后台继续排空。停止：完成当前组并排空所有已接收组，关闭分段，完成必要回读和汇总，恢复交互状态。错误：将当前组标为失败，不伪造完整结果，结束接纳并保全此前完整分段。记录进程死亡须通知 Kit 停止生产。

离线续跑从最后 FINALIZED 分段后的采样序号开始，新建分段，检查任务/素材/渲染配置版本一致；固定轨迹从绝对时间重建状态。涉及不可重放的手工交互或动力学时，不承诺精确续跑，另行保存/重放事件或完整状态。

## 10. Warning 处理清单

1. Writer version：在实例初始化设置版本，验证警告消失。
2. hydratexture 重复释放/Stage 引用：按创建→停止接收→等待 GPU/回调→解绑 annotator/writer→销毁 Render Product→释放 stage 顺序整理；close 幂等。复现重复初始化与关闭。
3. USD Diagnostics muted / channels：受控恢复具体诊断，定位 prim 和属性。验证受影响对象的渲染及传感器输出，不能只屏蔽文本。
4. Motion BVH：保留当前已验证的兼容设置，先验收静态姿态下 TLAS、Gaussian 与传感器一致性。Instant 和暂停不能自动证明该路径完全正确。
5. texture→host：独立计时读回，优化复制次数和有界缓冲；如尝试异步读回，必须有可验证的完成信号。
6. anim.graph 导入失败：明确功能依赖和扩展来源；项目路径不需要时可在专用采集启动配置中减少无用扩展，但需验证无间接依赖。
7. 弃用与插件内部性能提示：标注来源、影响及是否能由项目修复，不为日志整洁升级系统或驱动。

每条归类保留首次/末次时间、次数、阶段、来源和处理结论。重复日志可在 UI 聚合，原始日志保留；影响组正确性的故障直接阻止该组提交。

## 11. 性能与验收

监测推进/变换同步、预热、渲染完成等待、读回、IPC、编码、写盘、容量等待及主动限速；区分重叠和嵌套时间。GPU 忙闲不得由 Python 耗时推断，整卡利用率不得当作某传感器专属耗时。

基准为同一轨迹、相同传感器配置、相同画质的固定组数。先验证正确性，再比较工作者数/缓冲数；一次只改一类参数。增加画质与纯性能优化分别报告。

| 验收层次 | 必须满足 |
|---|---|
| 时间 | 每组预热/采样期间不推进仿真时间；源时间可解释且与统一时刻一致 |
| 新鲜度 | 位姿改变后采集的是新场景结果；相同图像内容不能单独作为新旧判断 |
| 几何 | 已知靶标的点云、图像投影和 TF 符合标定容差 |
| 数据 | 所有必需传感器组数一致、无无记录丢失；PNG 可解码，PointCloud2 字段一致 |
| 格式 | 标准 ros2 bag info/play 可用；完整组的 TF、CameraInfo 和元数据可解出 |
| 异常 | 队列满不会越界；暂停/停止排空；记录进程失败后停止生产；未完成段不标成功 |
| 生命周期 | 重复启动/停止不产生项目造成的重复释放，内存不存在持续增长趋势 |
| 性能 | 报告完整组/墙钟秒、P50/P95 延迟、CPU/GPU/内存和各阶段成本；不预先承诺满载或加速倍数 |

只有核心时序、坐标转换、buffer 所有权、异常提交等高影响边界编写针对性测试；避免对每个包装函数堆叠镜像测试。集成验证先小场景，随后在真实四相机十三雷达场景运行。

## 12. 实施批次与交付

P0：冻结基线、修复已定位的 Writer 问题、取得具体 USD 警告、完成静态画质对照。产出渲染基准与警告台账。

P1：完成 ClockAdapter/SceneStepper 与一相机一雷达的暂停采集验证。产出短 MCAP 和时间/几何验收；不通过不进入并行重构。

P2：扩展全部传感器、统一 FrameBundle/TF/状态输出、三种运动模式进入新协调器。产出完整但先以简单写入运行的正确性基线。

P3：接入共享缓冲、编码池、独立 ROS/MCAP worker、分段与停止排空。完成工作者数和缓冲容量基准。

P4：接入 headless 入口、交互任务保存、可选 RViz、运行时参数快照和性能面板；验证整个用户流程。

P5：本地与远端源码清单及哈希对齐，真实场景验收，交付运行文档、数据格式说明、对照报告和回退入口。

部署只操作项目、项目输出及必要的新任务配置，覆盖前保存被替换代码的可恢复版本。现有场景需要测试变体时新建层或文件，不覆盖用户旧 USD。无需默认安装依赖；若确需外部文件，按 cloud-instance-ops 的既定批次清单要求列出来源/版本/用途/落点/校验与执行方式后处理。只使用既有实例别名和凭据引用，记录脱敏操作日志。

## 13. 依据

- reports/20260923_capture_architecture_plan.md：本轮前置分析。
- reports/20260923_parallelism_and_warnings.md：线程、性能与警告证据。
- 现有 sensor_visualizer/camera_capture.py、unified_bag.py、state_publication.py、discovery.py。
- semantic_worldModule_v04 的 runtime/world.py、coordinator.py、camera_driver.py 和 lidar_driver.py。
- NVIDIA Isaac Sim 6.0 Replicator：
  https://docs.isaacsim.omniverse.nvidia.com/6.0.0/replicator_tutorials/tutorial_replicator_getting_started.html
- NVIDIA RTX Real-Time 2.0：
  https://docs.omniverse.nvidia.com/materials-and-rendering/latest/rtx-renderer_rt.html

当前方案复用已读取的官方资料及本地代码，没有新下载依赖或执行远端改动。
