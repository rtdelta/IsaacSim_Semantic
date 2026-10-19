# single0601ContinuousRt 快速同步采集实现方案

日期：2026-10-13。版本：002。用途：交给实现 agent 执行的设计与验收契约。

在独立项目中实现常驻传感器、连续 RTX Real-Time 2.0 渲染、同一物理仿真时间的多传感器组包和后台 MCAP 保存。默认完整保存所有计划采样；只有原生载荷、时间、位姿、状态及保存结果全部通过检查的数据，才进入可交付数据集。性能目标是减少重复预热、原生资源启停与串行写盘等待，实际吞吐以同条件测试决定。

本方案规定实现和验收要求，不是已经实现功能或已经取得性能的证明。001 保留为历史技术路线说明；实现遇到两者冲突时遵循 002。同步保证是当前限定传感器模型、已验证 SDK 接口和本方案误差范围内的保证，不等同物理传感器完全真实。

## 1 目标与交付定义

首版必须同时交付以下能力：

1. 使用一个 Isaac GUI 进程同时承担场景、运动、视口与正式传感器采集；一个独立 CPU 记录进程负责编码、CDR 和 MCAP。可保留网页服务作为控制入口，不能另起第二个 Isaac 场景来重放交互状态作为默认采集路径。
2. 支持相机、Instant LiDAR 的任意非空组合，包括单相机、单 LiDAR、1+1、4 相机+13 LiDAR。
3. 物理时钟驱动运动和采样；持续渲染阶段没有逐组 16 子帧预热，没有逐组创建、销毁 RenderProduct 或执行 Replicator stop/drain。
4. 多路载荷在同一个物理仿真采样时刻组包，TF、关节状态、整机姿态及标定来自该时刻的不可变快照。
5. 视口焦点下的原生键盘控制、参数控制和轨迹重放均经过同一个运动控制器。
6. 输出包含严格回读验证结果。同步正确性、采样完整性、速度与图像质量分别报告，不能互相替代。

默认运行策略为 `strict_complete`：内存或保存链路过载时允许物理仿真减速或在安全边界暂停；不丢弃计划组。持续墙钟运动且允许丢整组的 `strict_latest` 是显式可选策略，仍要求每一个实际提交组同步正确。它不满足完整采样验收。

下列情况不能报告完整交付：只生成 PNG、只发现所有话题都有数据、只通过生产端检查、只交付后备调度但未通过连续调度验收，或同步通过而快速采集目标未达到。

## 2 项目位置与操作范围

工作根目录：`scripts/260920SensorVisualizer/v06/single0601ContinuousRt/`。在其下创建新包 `single0601_continuous_rt`、配置、工具、测试和说明。旧 v06 源码、配置、实验项目及磁盘 USD 保持原样。

目标场景为现有：

```text
/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_18_terrain_fisheye_mesh.usda
```

该路径来源于 scene18 交付记录，启动前必须在实际主机确认存在并读取真实哈希。场景依赖原有环境和传感器资产；根 USD 哈希不足以描述所有依赖，还要记录使用层、传感器配置及可解析材质或几何依赖的清单和哈希。

复制复用模块时重命名包内导入，记录来源及修改。新运行包不能偷偷导入旧 `interactive_runtime` 或 `SceneStepper` 来获得另一套时钟、冻结调度和状态。几何、发现、关节控制、缓冲、诊断和记录组件可按明确接口移植。

修改 USD、传感器采样设置、原图停用和运动属性时只写自有匿名 Session 子层；结束时移除此层并恢复本项目改过的全局设置。不得接管其他工具的匿名 RenderProduct。不得为测试终止不属于本项目的进程。

本地 Windows 保存代码和文档；真实 Isaac/ROS 验证按实际运行主机进行。执行远端部署或 SSH 操作时使用适用的 `cloud-instance-ops` 技能与已有授权；这份方案本身不建立新远端凭据或系统改动授权。

## 3 版本探测与启动条件

先实现 `tools/probe_capabilities.py`，将实际 Isaac、Kit、Replicator、RTX 传感器扩展、ROS、MCAP、Python、GPU UUID、驱动版本及相关设置写入 `capabilities.json`。已有实验报告使用过 Isaac Sim 6.0.1 rc7；官方 6.0.1 文档不能代替该构建的实际接口验证。

探测至少回答：

| 能力 | 必须取得的证据 | 缺失后的处理 |
|---|---|---|
| 播放触发 Writer | 持续播放时相机与 LiDAR 分别收到实际新载荷 | 连续后端不合格，测试屏障后端 |
| 源时间 | 与载荷同一完成事件关联的物理仿真时间 | 不允许用回调时当前时钟代替 |
| 原生渲染引用 | `ReferenceTime` 或等价可验证的原生事件引用；记录作用域 | 缺失时不能默认多帧在途成立 |
| 渲染位姿 | CameraParams 的 view transform，LiDAR 输出的 transform | 无等价来源则不允许严格交付 |
| 完成与源缓冲寿命 | 可立即物化独立 CPU 数据的事件及接口契约 | 不允许跨回调保留 SDK 缓冲 |
| 传感器 tick | 实际新载荷间隔、相位、scanRateBaseHz、tickRate | 相位不对齐则启动失败或进入后备验证 |
| 运动阶段 | 同一物理步写入、读取、渲染的先后关系 | 不允许仅用 app update 序号猜测 |
| 暂停与排空 | 暂停后在途完成和资源准备行为 | 不允许在 Writer 回调中盲目 stop/drain |

探测使用至少 20 个有区分度的运动采样，不只测试静止。传感器 ID、注释字段和返回数组设备必须取自真实输出。原生 `ReferenceTime` 的分子、分母表示渲染引用，不可直接当成物理仿真秒；用目标版本支持的映射读取物理时间，并保存映射证据。

探测输出 `continuous_verified`、`barrier_verified` 或 `unsupported`，同时列出具体失败原因。`auto_verified` 仅可在首组正式提交前选择已经实测通过的后端；不得在正式运行中静默换后端。

## 4 同步与完整性的硬契约

正式组的主键为 `(recording_id, epoch_id, target_step)`；传感器样本主键还包含 `sensor_id`。`epoch_id` 隔离时间回退、复位和重新开始。原生帧编号可以为空，但不能用项目回调计数伪造。

每个正式组必须满足：

1. 包含所选传感器集合中的每一路，每路恰好一个独立拥有的载荷。
2. 每路时间证据来自其载荷所属的原生渲染完成事件；从源时间映射出的采样步必须等于组的 `target_step`。
3. 源时间与该物理步实际记录时间的差值不超过 `2 ns`；这是浮点转整数的容差，不是允许几毫秒跨帧匹配。各路原始源时间及原始差值都保存。
4. 没有最近邻时间匹配、状态插值、跨 epoch 匹配、给旧载荷统一平移时间戳等补救。初版仅交付精确物理步对应的数据；其他策略必须另设数据契约与版本。
5. 状态快照已在渲染之前产生，且代表该步实际生效状态。不能以指令值替代实际读回状态，也不能在回调中读取最新 USD 充当历史状态。
6. 渲染位姿与历史状态中的传感器位姿一致；刚体转换、单位、光学坐标与点云局部坐标均通过检查。
7. 有新的采样事件证据，没有旧缓存回读或重复源事件。相同 RGB/XYZ 字节在静止情况下允许出现，内容哈希不能单独充当新鲜度依据。
8. 编码和写入后的消息可按提交清单回读，采样 header、载荷与 TF 对应关系没有改变。

连续后端要用每路可验证的原生引用、源时间和事件完成关系证明新鲜度。不同 RenderProduct 的原生 frame ID 可能处于不同作用域，不能要求数值相同就认定同步。若只有模糊回调顺序，先限制到一组在途，并验证屏障后端；没有可靠源证据则拒绝正式采集。

默认位姿阈值：平移误差 `<= 1e-3 m`，旋转测地角误差 `<= 1e-4 rad`。分别计算二者，不再仅用 4×4 矩阵最大元素差描述全部位姿误差。阈值超限必须定位原生状态、变换或时序原因；更改阈值必须有独立精度依据，并在报告中标记，不能用于掩盖半帧或一帧偏移。

保证有效组同步，不代表故障时一定能完成全部计划。`strict_complete` 遇到缺路、错误时间、错误位姿或无法取得独立所有权，应停止录制并标为失败，保留经过验证的前缀；不能跳过组后仍标 `completed`。`strict_latest` 只可丢整组并标记缺口。

## 5 物理时钟与采样配置

首版默认物理步 `60 Hz`、同步采样 `10 Hz`、所有正式传感器同频同相位。scene18 的现有采集清单显示 13 路 Instant LiDAR 的 scanRateBaseHz 为 10；启动必须再次读取实际资产，不能把历史清单当成运行时参数。

以实际物理步计数和 `SimulationManager` 时间作为权威来源，按理数计算目标采样网格，不累计浮点 `t += 0.1`。记录物理步实际时间；其与计算网格也要核对。例：采样 epoch 对齐后的第 6、12、18 个物理步采样，间隔 100 ms 仿真时间。

`loop_hz` 和物理步默认都为 60，按目标 SDK 设置固定步长。若一个应用更新包含多个物理步，每个物理步仍须独立积分和读回；不得把实际发生的多个步压成一次大 dt。`omni.timeline` 和墙钟仅用于播放控制及性能测量，不承担第二个运动时钟。

相机使用目标版本支持的 OmniSensorAPI/tickRate 设置 10 Hz；LiDAR 保持现有 scanRateBaseHz，并设置相同 tickRate。保留 instantLidar、扫描参数、角度、范围及噪声配置。若资产的扫描频率不符合本配置，明确拒绝或选择单独的合法配置，不能偷偷改 scanRateBaseHz 来凑频率。

初版要求 `physics_hz / sample_hz` 为正整数，混合采集的每路实际频率与相位符合共同网格。先在初始化预热后观察共同新 tick，确定采样 epoch；第一个正式目标安排在之后的共同 tick，生产端和记录进程必须提前 ready。初始化样本有明确排除范围，不得把正式缺失首组伪装为预热。

`sample_hz` 降到 5 Hz 时，若 LiDAR 原生合法 tick 仍为 10 Hz，可在已验证共同 10 Hz 事件中按固定序号选每第二个完整组，记录采样规则；不将 LiDAR tick 改成与 scanRateBaseHz 不一致。不同原生频率的通用异步融合留给后续版本。

## 6 统一运动控制器

所有键盘、参数和轨迹命令先进入有界控制队列，附带接受时间、来源及 revision。按键事件只更新按键状态。物理步控制器按照实际 dt 积分一次，再提交姿态。

移植 v06 控制器时必须移除以下行为：墙钟间隔截断后生成独立运动秒、自增 `self.time_s`、发现 Timeline 播放就强制暂停、交互循环和原生图分别再次调用 `controller.step()`。

规定阶段如下，具体事件/API 名称由 capabilities 实测确定：

```text
物理步开始
  消费已经接受的控制命令
  根据该物理步 dt 积分一次
  提交规定运动状态
物理及原生变换同步完成
  读回实际整机、关节、参考帧和传感器矩阵
  为该 physical_step 发布不可变 StateRecord
Hydra/传感器采样
  原生载荷携带该事件的时间与渲染位姿
Writer 完成回调
  通过源时间/原生引用关联之前保存的 StateRecord
```

若目标 SDK 中 pre-physics 直接姿态写入会被随后积分覆盖，允许改为物理步之后、Hydra 之前统一施加规定姿态并同步，必须用已知轨迹验证后固定该阶段。禁止混用两个阶段或依赖未证实的订阅优先级。

首版保持规定运动：关闭重力、碰撞和关节力驱动属于明确记录的模型选择，不声明挖掘接触动力学真实。保存 command 与 actual 的区别；现有模块中归零的 DOF velocity 不作为运动速度标签，速度可由连续实际姿态按仿真 dt 计算，并标记来源。

视口控制条件为应用窗口聚焦、目标视口具有输入焦点、文本输入没有阻塞、Keyboard Control 开启、Timeline 播放。每个更新检测焦点丢失并清空按键状态，不能只等下一次键盘事件。Pause、Stop、复位和关闭均清空。保留明确开关，消费项目控制按键以避免同一按键同时驱动视口导航。

## 7 连续采集后端

`ContinuousBackend` 是主交付路线。RenderProduct、Annotator 和 Writer 在会话初始化时创建并常驻；正式录制期间保持传感器原生准备状态，利用合法 tick 跳过不需要的传感器采样。原场景产品通过移植 `RenderLease` 临时停用，产品和节点清单写入 manifest。

设置 RTX Real-Time 2.0，即 `RealTimePathTracing`，正式数据保留每路 1920×1080、原鱼眼标定与无损 PNG。默认渲染配置先沿用 v06 DLSS Quality/现有 AA，并关闭 Frame Generation。记录请求值与实际值；不将插值显示帧作为传感器采样。

正式采样每事件仅要求一次 RT2 渲染完成，不执行 16+2 子帧累积。启动预热只在初始化、恢复了已确认失效的资源或资产/安装发生离散修改后执行。连续姿态变化不触发逐组预热。

播放采集使用 `set_capture_on_play(True)` 和目标版本验证通过的 Writer 自动触发机制；不要同时运行会产生第二套采样/随机化的 `run_async` 或 `on_frame` 链路。每路 Writer 同时接收载荷、源时间、原生引用、渲染位姿，字段不能分别在不同时刻轮询后拼接。

使用 `IsaacExtractRTXSensorPointCloud` 获取 XYZ。首版 MCAP 主输出沿用 v06 自有后台 ROS 消息与 `SequentialWriter`，ROS Helpers 不参与正式时间戳生成。可选 RViz 发布仅消费同一组已验证消息；预览失败不改动正式数据，另行记录错误。

常驻期间不会为了完成每组调用 `wait_until_complete_async()`。此接口在现有链路可能带来 stop/drain 生命周期成本。仅在录制段结束、资源变更或退出时，按照已验证的排空契约执行。

## 8 单采样步屏障后端

`BarrierBackend` 是后备正确性路线，也用于对照连续链路。它保留同一套产品、分辨率、传感器配置、后台保存和同步验证。

对每个目标采样：预留缓冲和 ticket；按照固定物理步推进至目标时间并取得 StateRecord；使用已经验证的原生单次渲染/Writer 完成机制取得全部载荷。在取得源证据和独立数据所有权前，不推进超过该目标的物理状态。UI 可以继续处理事件，下一步的运动命令排队，不能在等待期间修改目标姿态。

可验证目标版本的 `step_async(..., rt_subframes=1, wait_for_render=True)` 或完整 app update 驱动方式，但不预设某一调用能在所有构建、tick 设置和暂停状态下取得新 LiDAR 数据。必须证明每次返回实际新载荷、正确时钟与位姿，不能把暂停后的缓存 get_data 当采集。

后备模式不恢复每组 16 子帧预热，也不逐组销毁资源。若原生采样必须在特定的 play/update 边界完成，则只保持一组在途并在该边界等待收齐；把实际操作写入 capability 报告。

连续后端在正式运行中失去同步能力时，当前会话标失败并排空；用户或上层可以另开已经验证的屏障会话。不得给现有会话静默换调度。只有屏障后端通过时应报告 `barrier_only`，不能声称完成连续主目标。

## 9 状态历史与时间组包

`StateLedger` 在每个物理步原生同步完成后保存 StateRecord，字段包含 epoch、physical_step、实际物理时间、状态 revision、安装 revision、整机/参考帧矩阵、实际关节状态、所选传感器世界矩阵和标定引用。

历史只保留数值和不可变 CPU 数据，不保留 USD prim、Articulation 或 SDK array 对象。以在途 ticket 引用保护所需记录，释放 ticket 后才能淘汰。默认最大 1024 条，接近上限时 strict_complete 暂停新采样并让记录线程排空；不能覆盖仍被引用的状态。strict_latest 超出窗口时丢弃相应整组并记账。

`TimeJoiner` 用源时间先定位精确物理步，再关联期望传感器集合。允许回调乱序；不能靠回调到达顺序生成 target_step。组完成前等待剩余路，达到墙钟 deadline 后触发明确错误。默认组 deadline 5 s，只代表故障检测界限，不是实时性能门槛。

每路收到的原始 source time、rational reference 和 frame ID 均保留；frame ID 无接口时为 null，项目递增的 receipt_seq 单独命名。重复原生事件不得重复提交。相同事件若收到不同数据，标 `conflicting_duplicate` 并失败；相同内容重复到达也记录重复来源。

状态、安装或场景修改导致的不连续必须在段边界完成：暂停新目标、收齐并排空旧 ticket、增加安装 revision 或 epoch、重新同步/必要预热、安排新的共同采样边界。不能在一个正式组中混入修改前后的传感器安装或标定。

## 10 缓冲所有权与过载处理

保持以下所有权链：

```text
SDK 拥有的完成载荷
  → 回调期间立即物化到独立 CPU 缓冲
  → 验证完成的组
  → 自有 mmap 槽与 generation
  → 编码后的独立消息 bytes
  → MCAP 写入
```

第一阶段使用 `do_array_copy=True` 或等价的可靠立即独立复制路径。CPU 物化可能包括 GPU 等待，单独测量它。只能把已经独立拥有的数据交给后台线程。不得将 Warp/CUDA/Vulkan 借用缓冲或依赖不明的 pointer view 交给后台。

性能阶段可减少中间复制，例如 Writer 中立即消费借用数组并在返回前完成自有 CPU 拷贝，或在接口契约允许时直接写自有 mmap。每项优化须证明源事件完成、源缓冲生命周期和目标槽位独占。没有这些证据不得做跨帧异步 D2H 重叠，不以自建 CUDA event 猜测原生 Vulkan 完成。

默认每组 64 MiB 槽、总缓冲预算 512 MiB。该预算包含 reserved、assembling、已复制组、mmap 和 encoded queue 的实际驻留估计，不能只限制某一个 queue。4 路 RGBA 原始图像约 31.6 MiB，13 路点云与其他副本另计；启动探测按实际点数上界核算槽位，若不足则拒绝并明确给出需要的容量，不能截断点云。

默认最多 3 组在途仅在实测 native lead 有上界且缓冲足够时启用，否则从 1 组开始。预算容量必须覆盖在途组、native lead 以及暂停生效前可能到达的一整组安全余量。若无法确定引擎会领先多少采样，限制 native 提交为一组屏障。

所有队列均按组数及字节数有界。编码队列初始容量 2，encoder_workers 初始 4，仅相机存在时创建图像编码线程；只有 LiDAR 时不启动图像编码任务。

strict_complete 必须在源采样开始之前预留本组槽位和资源信用，不能等回调到达后因 queue.Full 丢载荷。达到高水位时由引擎所有者在下一安全更新边界阻止新目标/暂停时间推进，保留产品；在途回调继续交付到已预留资源。低水位恢复后记录同一 epoch 的下一计划目标。预留机制若不能覆盖实际 native lead，就不能启用多组在途。

Writer 回调不得阻塞等待编码队列、做 PNG、写盘或做同步 socket.sendall。回调仅做关联、数值提取和必要独立复制，再以不阻塞方式投递已预留资源。压力动作投递给主线程 owner，不在回调里调用重入 stop/drain。

strict_latest 若无法预留，按目标组拒绝整个采样组；若单路已经到达，则保证其余路不会被错误挂到下一组，释放已有资源并登记 gap。output_group_id 可以连续，target_step/target_index 必须保留原缺口。

## 11 MCAP 输出与提交规则

首版保持 ROS 2 消息类型和既有话题命名，图像使用原始鱼眼 RGB 的无损 PNG，点云使用传感器局部米单位的小端 XYZ float32。保持 ROS 光学坐标转换，明确 USD/Gf 行向量矩阵与 ROS 变换约定。

每一个已验证组按固定顺序写入该组相机、CameraInfo、相机 pose、点云、TF、JointState、root pose、Clock 和 frame_index。header 与 rosbag2 写入 timestamp 都取自该组验证通过的物理步时间。原始传感器时间单独保留，不能因输出 header 相同而删除时间差证据。

`frame_index` 元数据 schema 升级为 3，增加 epoch、target_step、target_index、backend、raw source times、native refs、state/mount revisions、同步检查结果和每路载荷 hash。旧冻结说明必须改成新语义。ROS `header.frame_id` 表示坐标系，不表示源帧序号。

再增加 `/sensor_visualizer/group_commit`，以 String 或清晰的新 schema 保存该组消息数、逐话题的序列化消息 hash、group hash、目标时间与同步结果。它必须在该组其他消息之后写入。编码前原始 RGB/XYZ hash 与编码后 CDR hash 分开，不能混称同一个 hash。

槽位只有在所有后台 view 已不再引用它之后才能释放，release ACK 必须检查 recording_id、group_id、slot、generation。收到 ACK 表示可以复用内存，不表示数据已经持久化。另设 written ACK 与段结束的 close/validation 状态。

rosbag2 写多条消息不具备跨消息事务；崩溃可能留下半组。因此写入工作目录始终标为 partial，段完成后关闭 MCAP，独立回读验证，再生成含文件 hash 的 `dataset_manifest.json` 和 `READY` 标记。只有 READY 标记对应的清单供下游训练发现。group_commit 不是 fsync 或崩溃安全保证。

失败会话放在明确的 failed/partial 区域，禁止作为正常数据集被自动发现。只有现有解析器能读取完整提交前缀时才可恢复验证并另行导出；不能假定损坏 MCAP 总能修复。每次恢复必须新建清单并保留来源。

`strict_complete` 完整交付要求 requested、scheduled、validated、written、readback_verified 组数相同，gap=0。严格同步前缀可作为单独有效片段交付，但其原会话保持 failed 或 stopped 状态，不能补写完成。

## 12 生命周期与控制

录制状态与仿真播放状态分别保存，由同一 owner 串行处理命令：

```text
INITIALIZING → PROBING → WARMING → READY
READY → ARMING → RECORDING → DRAINING → VALIDATING → COMPLETED
RECORDING ↔ PAUSED
任意活动状态 → FAILED → CLEANUP
```

初始化时保存 settings，创建 Session 层、运动控制和所选产品；记录进程 ready 后，再安排正式 epoch。预热完成由载荷格式、源时间与渲染位姿稳定共同判定，固定 warmup 数量仅作最低窗口。默认最低 8 app updates，上限 120；超时失败，不能无期限等待。

暂停仿真：清空按键，在安全边界停止推进；在途组按原时间完成并保存。恢复不重复已提交目标，tick/timestamp 行为须先通过探测。若暂停导致原生引用或时间域断裂，关闭旧段并开启新 epoch，不在旧段中强行拼接。

停止录制：清空正式采样请求，记录 cut-off target，完成已经预留和提交的组，排空编码与 MCAP，回读验证；仿真是否继续由独立播放状态决定。任意已在途组不能被假装成停止后新请求。

Timeline Stop、复位、换场景或更换传感器集合：先停止接受新目标并排空；增加 epoch/重建失效句柄。时间回退不能写进同一输出段。键盘状态立即清空，不等待记录线程结束。

编码错误、磁盘满、记录进程死亡、超时、SDK 同步错误均向 owner 传播，停止后续采样，保存失败原因及计数，安全清理自有资源。不能吞掉异常继续报告 completed。禁止在繁忙主线程中同步等待线程 join 或 waitpid。

停止期间使用已验证的完成屏障，不以任意 sleep 判断 GPU 已结束。退出恢复本项目更改的设置与 Session 层，保存清理成功/失败结果。

## 13 模块和接口

建议结构如下，允许拆分文件，但接口责任不能合并成新的全局运行器：

```text
single0601ContinuousRt/
  run_in_isaac.py
  run_capture.py
  single0601_continuous_rt/
    config.py                 配置校验和采样时钟
    capabilities.py           实际 SDK 能力探测
    engine_owner.py           唯一场景及 Timeline 所有者
    motion_controller.py      统一输入和物理步积分
    sensor_registry.py        发现 选择 标定及资源清单
    sensor_backend.py         连续与屏障后端
    state_ledger.py            不可变实际状态和引用保护
    time_joiner.py             源时间组包和同步验证
    buffer_pool.py             有界字节预算 槽位代数及信用
    record_pipeline.py         异步 IPC 和生命周期
    record_worker.py           PNG CDR MCAP 与提交标记
    messages.py                ROS 消息和坐标转换
    diagnostics.py             指标和有界事件日志
    ui.py                      原生面板及视口控制
  config/
    strict_scene18.json
    single_camera.json
    single_lidar.json
    mixed_pair.json
    benchmark_scene18.json
  tools/
    probe_capabilities.py
    validate_mcap_sync.py
    run_acceptance.py
    compare_performance.py
  tests/
  docs/
  reports/
```

接口约定：

- `StateRecord`：epoch、physical_step、sim_time_ns、实际状态、所选传感器矩阵、状态/安装 revision。发布后只读。
- `SensorReceipt`：recording、epoch、sensor_id、raw source time、native_ref、source_frame_id 或 null、receipt_seq、渲染位姿、owned_payload、单调到达时间及 source provenance。
- `GroupTicket`：target_step、期望传感器集合、预留 credit/slot、deadline、received/validated 集合和状态引用。禁止借用冻结 ticket 的新鲜度白名单冒充连续证据。
- `ValidatedGroup`：StateRecord 和全组独立载荷；附逐路同步证据。只有它可进入正式编码器。
- `RecordAck`：分别表示内存 release、消息 written、段 closed，不合并三种状态。
- `ValidationReport`：sync_ok、completeness_ok、quality_ok、performance_ok、backend、实际运行信息、逐组错误及汇总计数。

`engine_owner` 独占所有 Kit/USD/PhysX 调用。TimeJoiner 和 worker 只处理 CPU 数值，不读取当前引擎。若 Writer 回调实际不在主线程，先完成符合 SDK 契约的载荷独立物化，再将 receipt 入有界 mailbox；USD 与原生调用仍由 owner 处理。

## 14 初始配置

以下是新项目 job schema 4 的设计配置，必须由新 `config.py` 实现，不直接传给 v06 schema 3。性能参数可以按实测调优，硬同步与完整性语义不能自动放宽。

```json
{
  "schema_version": 4,
  "scene": "/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_18_terrain_fisheye_mesh.usda",
  "sensors": {"camera_ids": null, "lidar_ids": null},
  "clock": {"physics_hz": 60, "loop_hz": 60, "sample_hz": 10},
  "capture": {
    "backend": "auto_verified",
    "policy": "strict_complete",
    "requested_groups": 300,
    "max_inflight_groups": 3,
    "group_timeout_wall_s": 5,
    "source_time_tolerance_ns": 2,
    "translation_tolerance_m": 0.001,
    "rotation_tolerance_rad": 0.0001,
    "state_history_max_records": 1024,
    "runtime_fallback": false
  },
  "render": {
    "mode": "RealTimePathTracing",
    "dlss_mode": 2,
    "aa_mode": 3,
    "frame_generation": false,
    "formal_subframes": 1,
    "initial_warmup_min_updates": 8,
    "initial_warmup_max_updates": 120,
    "motion_blur": false
  },
  "pipeline": {
    "max_buffer_bytes": 536870912,
    "slot_bytes": 67108864,
    "encoder_workers": 4,
    "encoded_queue_groups": 2,
    "png_compress_level": 1,
    "segment_groups": 1000
  },
  "output": {
    "directory": "/root/gpufree-data/semantic/output/single0601ContinuousRt",
    "require_readback_validation": true,
    "image_codec": "png_lossless",
    "point_fields": ["x", "y", "z"]
  }
}
```

`formal_subframes=1` 表示一次正式 RT2 完成事件，不暗示所有后端直接调用 step_async。motion_blur 关闭代表明确的理想瞬时曝光模型；不代表真实相机没有曝光过程。单相机配置设 lidar_ids=[]，单 LiDAR 配置设 camera_ids=[]。

`None/null` 选择该类所有可用传感器，`[]` 不采集该类，列表只选指定 ID。过滤 inactive/unloaded 节点；明确指定的 ID 若不可用则报错，不静默略过。未选相机不要求存在或读取其标定。总集合为空报错。选定注册表在一段录制内固定。

默认时钟和传感器参数的合法性、实际槽位容量和帧引用能力都由 preflight 检查。无条件将 max_inflight_groups=3 套用到任何 SDK 的行为不符合本方案。

## 15 独立回读验证

`validate_mcap_sync.py` 用实际 ROS/MCAP 环境读取最终消息，不能只读生产端 manifest 或 writer_report 后复述其 ok 字段。它必须重新解码 ROS 消息、PNG 和点云，并独立计算提交 hash、TF、时间与完整性。

逐组验证至少包括：

1. group_commit 存在，目标索引顺序合法，所选话题恰好齐全，没有同组重复。
2. sensor header、CameraInfo、pose、TF、JointState、root pose、Clock 与 group target time 一致；raw source time 与该实际物理步的差值在 2 ns 内。
3. RGB 解码后与 owned 原始像素 hash 一致；XYZ 字节与 owned 点云 hash 一致；CDR 消息 hash 与 commit 清单一致。主验证期间不新增另一套 BasicWriter 全图落盘开销。
4. TF 组合与相机 optical/world、LiDAR local/world 和实际 root 的关系一致。对 Gf 行向量矩阵转 ROS 的步骤设独立非对称旋转和平移算例，避免两个错误转换互相抵消。
5. 图像分辨率、颜色通道、鱼眼内参及 distortion model 正确；点云字段、dtype、单位、范围与有限值规则明确。零点数可在规定的无返回场景合法出现，不能仅凭空点云判旧帧。
6. target_step、source ref、epoch 和安装 revision 的关系一致，无跨段旧回调；每段时间单调，不要求跨复位段绝对时间连续。
7. strict_complete requested=scheduled=validated=written=readback_verified，缺口为零。strict_latest 缺口与日志逐一对应，报告 completeness_ok=false。

此外运行独立的运动几何诊断：使用匿名 Session 层中的已知平面和具有可定位特征的标记，测试整机平移、转动、大臂/铲斗运动、遮挡切换和静止。通过鱼眼投影检查图像特征，通过已知平面/表面检查点云，从物理轨迹预测应出现的位置。

诊断场景使用明确记录的理想曝光及可解释噪声设置。初始几何诊断目标为特征重投影误差 P95<=1 px、无噪声平面点到面误差 P95<=5 mm；正式资产保留原传感器参数。误差超限先调查时间、坐标、模型和特征提取；不能仅用内部矩阵一致来替代独立几何检查。

专门注入旧载荷、错时间、延迟、重复回调、错误 epoch、缺一路和已复用槽位：验证器和生产端都必须拒绝。静止时内容 hash 相同的有效新帧不能误拒绝。用于检测一物理步偏移的运动幅度要足够，单步像素/距离差应明显大于诊断阈值。

## 16 性能与图像质量验收

速度目标是以下设计目标，必须实测，不代表现有硬件承诺：

| 指标 | 目标或判定规则 |
|---|---|
| 全组合稳态吞吐 | scene18、4×1920×1080、13 LiDAR、同 PNG 与参数，对 v06 keepalive 基线至少 2 倍有效组/墙钟秒 |
| 完整单组合 | 各配置计划 10 Hz 仿真采样完整，实际 RTF 和墙钟输出频率如实报告 |
| 交互响应 | 正常负载下 accepted-to-applied P95<=50 ms、P99<=200 ms，最大值单列；这是引擎响应目标，不包括远程桌面和网络 |
| 真实时间运行 | 全组合 RTF>=1 是扩展目标；未达可保持严格同步减速，不能声称 10 Hz 墙钟采集 |
| 回调和复制 | 分别统计提交到回调、CPU 物化/拷贝及 join 延迟，不以 PNG 变快推断引擎变快 |
| 缓冲和生命周期 | 实际驻留预算有界，按已验证 credit 过载，无跨轮句柄和槽位泄漏 |
| 图像质量 | 通过运动细节与几何诊断；删除累积步骤后的质量差异需独立报告 |

基线在 scene18 上使用未修改的 v06 persistent_gated+keepalive、16 相机预热子帧+2 正式子帧。两套方案使用相同选定传感器、轨迹、资产、输出分辨率、标定、渲染设置和编码参数；子帧/调度差异是本方案改变的变量。只在质量验收通过后，将吞吐比较解释为可用数据产能提升。

先预热 20 组，再测至少 200 组稳态，普通无 profiler 运行各三轮，轮序交错。分别报告冷启动、采集、排空、回读验证与全操作耗时；提供中位数、P95、P99、最大和每轮值。诊断追踪单独进行，不混入普通速度结果。两套 GUI、传感器和预览工作负载保持一致或明确分开 headless 与 GUI 比较。

重点检查铲齿、细杆、鱼眼边缘、遮挡显露、快速转动和恢复首帧。保存少量按规则选择的无损样本与对照图，不能以某一组 PSNR 单独宣布画质等同。不得自动降低分辨率、关闭选定传感器、改 JPEG、改噪声或删正式状态话题来达成速度目标。

若默认 RT2 时域重建无法满足任务质量，单独提出并测量新的质量配置，记录差异；默认配置仍显示验收失败。同步正确但速度或交互目标未达时，保留代码和数据证据，明确性能未验收并定位热点。

## 17 分阶段执行与验收矩阵

| 阶段 | 工作内容 | 阶段完成条件 |
|---|---|---|
| M0 契约与探测 | 冻结源清单、版本、scene18 哈希，完成能力探测与配置校验 | 能解释实际回调时间/位姿/事件及暂停行为；不支持项明确 |
| M1 单相机闭环 | 固定物理步运动、状态快照、连续 receipt、PNG MCAP 和回读 | 静止及运动各至少 200 组；正式首尾组存在；时间与几何验收通过 |
| M2 单 LiDAR及混合 | 一路 LiDAR、1+1，再全组合，验证同频相位 | 单 LiDAR/1+1各至少 200 组，全组合至少 100 组；无错配、无正式缺口 |
| M3 控制和生命周期 | 原生视口键盘、参数、轨迹、暂停、停止、安装修改和复位 | 焦点测试通过；重复录制20轮各至少10组；跨 epoch/跨安装测试通过 |
| M4 过载与故障 | 慢编码、慢写盘、磁盘失败、进程退出、回调乱序/重复/错时、槽位旧ACK | 按策略背压或丢整组；所有不合格输入被拒绝；无假完成 |
| M5 性能与长期 | 交错基线、图像对照、30分钟墙钟全组合长测 | 全部组回读，资源有界，速度/控制/质量分别作结论 |

单相机和单 LiDAR 至少覆盖所有不同模型/安装类型，不能只测最容易的一路后假定其余全成立。ID列表为空、未知、inactive/unloaded、重复ID、非法频率、点数超槽、历史容量耗尽均有配置或故障验收。

本地可运行的纯 Python 测试包括：按理数时钟、精确时间组包、乱序/重复/缺失、epoch隔离、不可变状态、byte credit与旧generation拒绝、消息坐标转换、提交清单与缺口检查。真实 SDK 完成、缓冲寿命、tick与焦点行为必须在 Isaac 实测，mock 不作为替代。

## 18 必须提交的成果

实现 agent 必须交付：新独立项目源码与入口；五种配置；能力探测工具；独立 MCAP 同步验证器；本地测试；真实 Isaac 验收矩阵；同条件速度比较；少量图像/几何证据；启动、停止、失败恢复和回退说明。

每次实测报告至少包含 `environment.json`、`capabilities.json`、`source_manifest.json`、`asset_manifest.json`、`sensor_registry.json`、`render_profile.json`、`schedule.jsonl`、`receipts.jsonl`、`groups.jsonl`、`gaps.jsonl`、`performance.json`、`validation.json`、`session.json` 及原始错误日志。高频日志有界，source/receipt证据不得因诊断队列丢弃而失去对已提交组的验证依据。

记录每组状态转换和以下计数：requested、scheduled、received_by_sensor、validated、written、readback_verified、duplicate、invalid、dropped、late、queue_full、backpressure_pause。不同阶段用同一主机 monotonic 时间关联；UTC 只用于人类查阅，不能混入传感器时间。

最终报告逐项给出 `continuous_ok`、`sync_ok`、`completeness_ok`、`quality_ok`、`performance_ok`、`interaction_ok`、`lifecycle_ok`。只有所有必需项为 true 且存在经过回读生成的 READY 清单，才称主方案完整交付。保底交付、部分功能或某项失败必须明确指出，不能以剩余预算或跑通一次代替验收。

## 19 现有证据与参考资料

现有项目资料优先用于理解数据契约和失败模式：

- [001 技术路线](001_single0601ContinuousRt_实现方案.md)。
- [v06 架构与数据契约](../../../docs/architecture_and_data_contract.md)：原链路按冻结整组校验，不能原样当连续契约。
- [v06 传感器适配器](../../../sensor_visualizer_v06/sensors.py)：主机物化、独立复制、源时间及渲染位姿检查。
- [v06 交互运行器](../../../sensor_visualizer_v06/interactive_runtime.py)：迁移时识别独立墙钟积分和 native_play_suppressed。
- [v06 运动模块](../../../sensor_visualizer_v06/robot/articulation_motion.py)：规定运动、归零速度和原生同步。
- [single06_lab 结果](../../../../single06_lab/docs/findings.md)：常驻资源收益与控制长尾；不能保证连续路线自动解决。
- [NC003 测试报告](../../../../native_capture_continuous_pt_003/docs/NC-003_execution_report.md)：首组缺失和源时间偏移，PT/ROS Helper 现象不能直接推广到本路线。
- [scene18 使用说明](../../../../mesh_scene18/README.md)：目标场景路径、依赖与已有全组合清单。

官方接口依据：

- [Isaac Sim Multi Tick Rendering](https://docs.isaacsim.omniverse.nvidia.com/6.0.1/sensors/isaacsim_sensors_multitick_rendering.html)：物理/渲染时钟、源时间映射及 LiDAR tickRate 与 scanRateBaseHz 约束。
- [Replicator Python API](https://docs.omniverse.nvidia.com/kit/docs/omni_replicator/1.12.27/source/extensions/omni.replicator.core/docs/API.html)：capture-on-play、ReferenceTime 和异步数组所有权。实际安装版本须单独核对。
- [Isaac Sim Simulation Manager API](https://docs.isaacsim.omniverse.nvidia.com/6.0.1/py/source/extensions/isaacsim.core.simulation_manager/docs/index.html)：物理时间与事件接口。
- [RTX Real Time 2.0](https://docs.omniverse.nvidia.com/materials-and-rendering/latest/rtx-renderer_rt.html)：DLSS 及时间反馈特性；该文档不提供本项目吞吐或同步保证。

## 20 预期输出数据结构及含义

本节是第 4、5、9、11、18 节输出契约的具体化，供实现 agent、独立验证器和训练数据读取程序共同使用。下列字段为新项目必须实现的约定，不代表现有 v06 已输出这些字段。示例是构造的契约数据，不能作为 Isaac 实测或采集验收证据。

### 20.1 输出格式与目录层级

正式传感器和状态消息保存在 **rosbag2 MCAP** 中，消息类型使用 ROS 2 IDL，消息内容为 CDR 二进制。图像是 `CompressedImage.data` 内的无损 PNG；点云是 `PointCloud2.data` 内的小端 XYZ float32。JSON 用于运行清单、标定和验证报告；JSONL 用于按时间追加的调度、receipt、组状态与缺口证据。默认不另存逐帧 PNG/XYZ 文件，避免增加写盘和文件系统开销。

```text
<output_root>/
  partial/<recording_id>/                 # 写入中，不供训练发现
  datasets/<recording_id>/                # 本次请求完整通过回读后发布
    job_spec.json                        # schema 4，实际使用的配置
    environment.json
    capabilities.json
    source_manifest.json
    asset_manifest.json
    sensor_registry.json                 # schema 3，初始传感器与标定
    render_profile.json
    session.json
    schedule.jsonl
    receipts.jsonl
    groups.jsonl
    gaps.jsonl
    performance.json
    validation.json                      # 全会话独立回读结论
    epochs/<epoch_id>/segments/<segment_id>/
      bag_unified/
        metadata.yaml                    # rosbag2 自动生成，禁止手工猜写
        <storage_generated_name>.mcap     # 一个或多个；以 metadata.yaml 为准
      validation.json                    # 本段独立回读结论
      dataset_manifest.json              # 本段文件、组数、范围与哈希
      READY                              # 本段清单哈希
    logs/runtime.jsonl
    logs/writer.jsonl
    logs/validator.jsonl
    dataset_manifest.json                # 全会话及所有段的文件清单
    READY                                # 全会话清单哈希
  failed/<recording_id>/                  # 失败/提前停止会话及诊断证据
```

`recording_id` 每次开始录制生成新值；`epoch_id` 在复位、时间域断裂等情况下更新；`segment_id` 在分段、安装/标定改变和 epoch 改变时更新。一段不得跨 epoch 或安装/标定 revision。达到 `segment_groups=1000` 可正常分段；分段本身不重置仿真时间，也不逐组预热。元数据在每段开头写入该段实际版本。

段的 READY 表示该段数据可验证；全会话 READY 还要求满足本次请求的组数和策略条件。全会话文件清单冻结后才生成根 READY。失败会话中通过回读的前缀，必须另建导出目录、清单及 READY，并在清单中保留原会话来源；不能给失败原会话补写根 READY。训练发现程序只读取 `datasets/` 下具有根 READY、清单哈希一致且满足所需同步/完整性条件的数据。

READY 是 UTF-8 单行文本：`dataset_manifest.json` 文件字节的 SHA-256 小写十六进制值加换行。清单不包含自身和 READY 的哈希，避免循环依赖；其余必需文件及子段清单/READY 均纳入根清单。READY 是回读验收标记，不是电源故障下的事务保证；重新读取时仍须检查文件存在、大小和哈希。

### 20.2 产生步骤与字段来源

| 步骤 | 组件与原方案对应章节 | 产生的数据 | 后续用途 |
|---|---|---|---|
| P0 初始化与探测 | Preflight、CapabilityProbe，第 2、3、5、7 节 | 配置、环境、源码/资产清单、传感器注册表、渲染实值、能力证据 | 冻结配置、选定后端，建立单位与时钟语义 |
| P1 安排目标与预留 | SamplingClock、CreditAllocator，第 5、10 节 | Ticket、目标物理步/时间、期望传感器、槽位与 deadline | 防止回调到了才发现无空间；保存计划网格 |
| P2 实际状态快照 | MotionController、StateLedger，第 6、9 节 | StateRecord、actual 关节与姿态、历史传感器矩阵、revision | 作为目标时刻状态和 TF 的唯一来源 |
| P3 原生完成与物化 | SensorAdapter、Writer 回调，第 3、7、10 节 | 原始源时间、原生引用、原生位姿、receipt 序号、独立 CPU 载荷 | 证明载荷采样时刻、新鲜度和所有权 |
| P4 精确组包与校验 | TimeJoiner，第 4、9 节 | 源时间差、位姿误差、同步检查、StateRecord 关联 | 只有完整合格组才进入编码 |
| P5 编码与序列化 | Encoder、MessageBuilder，第 11 节 | PNG、XYZ 布局、ROS 消息、frame_index、CDR 哈希、group_commit | 锁定提交消息及字节证据 |
| P6 写入与关闭 | RecordProcess、SequentialWriter，第 10、11、12 节 | MCAP、释放 ACK、写入 ACK、关闭结果 | 区分内存可复用、写入成功和文件关闭 |
| P7 独立回读与发布 | 独立 Validator，第 11、15～18 节 | validation、文件哈希、dataset_manifest、READY | 给训练读取端提供最终验收结论 |

同一字段发生派生时，下表列出最早产生步骤和派生步骤。例如 `source_time_s` 来自 P3；`source_time_error_ns` 来自 P4；输出 Header 来自 P2 的目标时刻，经 P4 校验后在 P5 生成。不能将 P6 的接收时间填进 P3 的源时间字段。

### 20.3 公共类型、单位与约束

下表是后续字段表共用的类型定义。没有标记可空的字段必须存在；动态对象键只能来自注册的传感器/话题，不能作为省略必需字段的方式。

| 类型或约定 | 序列化形式 | 含义、单位及约束 |
|---|---|---|
| `Id` | JSON string | 非空 UTF-8 标识；recording/epoch/segment 的目录 ID 只用字母、数字、下划线和连字符，不能含路径分隔符；传感器 ID 使用 `camera/<id>`、`lidar/<id>` |
| `Index` | JSON integer | 逻辑非负整数，范围 `0..9007199254740991`；group_id 是本会话实际输出序号，target_index 是正式计划序号，二者不能互相替代 |
| `Ns` | JSON 十进制字符串 | 逻辑有符号 int64，单位 ns；字符串符合 `0` 或可选负号加无前导零十进制数字。本版仿真和 monotonic 时刻非负，时间误差可负；避免 JavaScript Number 丢精度 |
| `NativeInteger` | JSON 十进制字符串 | 原生整数引用的精确值；不是秒或项目序号；按探测出的接口范围校验，不转为浮点 |
| `Float` | JSON number / ROS float64 | 有限浮点数，禁止 NaN、Infinity；单位按字段声明 |
| `Hash` | JSON string | SHA-256 的 64 个小写十六进制字符；只能从表中规定的实际字节计算 |
| `RelativePath` | JSON string | 相对当前清单目录的 POSIX 路径，不含 `..`、盘符或绝对路径；文件必须落在清单的交付目录中 |
| `Pose` | JSON object | `position_m: Float[3]` 为米，`orientation_xyzw: Float[4]` 为 ROS 顺序单位四元数；四元数模长误差 `<=1e-6`；不要把 xyzw 当 wxyz |
| `UsdMatrix` | JSON `Float[4][4]` | Gf 行向量、行主序展示，平移在最后一行，最后一列为 `[0,0,0,1]`；平移已经换算为米。不能直接当 ROS 列向量矩阵使用 |
| `RosTime` | `{sec:int32,nanosec:uint32}` | 单位 s/ns，`0<=nanosec<1000000000`；`sec*1000000000+nanosec` 等于该组 simulation_time_ns；输出前检查 ROS sec 范围，超限拒绝 |
| `Header` | ROS object | `stamp:RosTime`，`frame_id:string`；frame_id 是坐标系名称，无前导 `/`，不是 frame_index 或源帧号 |
| `Result` | JSON `bool` 或 `null` | true 为已经通过，false 为已经失败，null 为尚未执行/无法判定；每项结果另有适用范围和证据引用。未测项不能输出 true |
| JSON 文件 | UTF-8，无 BOM | 单个合法对象，时间/大整数遵循上述字符串规则；`schema_version` 是必需整数 |
| JSONL 文件 | UTF-8，无 BOM，每行一个对象 | 行末换行；不写跨行 JSON、不夹杂控制台文本；仅完整行作为证据，尾部截断按故障报告处理 |

JSON 的 `schema_version` 分别为：`job_spec=4`、`sensor_registry=3`、MCAP 的 `run_metadata/camera_metadata/frame_index=3`；本节新增的其他 JSON 清单、JSONL 信封、commit、validation、ACK 都为 1。版本号按各类结构独立演进，不是项目版本号。遇到未知版本应拒绝解析，不能套用旧冻结语义。

三类时间必须分开：仿真 `simulation_time_ns/source_time_ns`；原生 `native_ref`；同主机同次进程会话的 `monotonic_ns`。性能计时使用单调时钟，跨进程前确认共享时钟域；UTC 采用 ISO 8601 字符串，仅供人类查阅。USD 单位和 up axis 从 P0 实际 Stage 读取；米制 Pose、点云和矩阵不再隐式沿用 Stage 原始长度单位。

### 20.4 运行清单与配置结构

以下结构补全第 18 节必需文件。表中每一行可列出一组同类型字段，嵌套字段使用点号；只有明确标记 `null` 的字段可空。文件类 JSON 的公共 `schema_version` 不在每行重复。

| 文件及字段 | 类型 | 含义、单位及取值约束 | 产生步骤 |
|---|---|---|---|
| `job_spec.json` | 第 14 节完整配置对象，schema 4 | 保存最终生效配置；第 14 节的 clock、capture、render、pipeline、output 等配置不得省略；选择结果写 capabilities/session，不改写用户请求 | P0 |
| `environment.recording_id`、`host_id` | Id | 本会话与实际主机标识；不得以本地编辑机器冒充实际 Isaac 主机 | P0 |
| `environment.created_utc` | string | 带时区 ISO 8601 时间 | P0 |
| `environment.os` | `{name:string,version:string,architecture:string}` | 实际操作系统与 CPU 架构 | P0 |
| `environment.versions` | string 或 null 值对象 | 必含 `isaac_sim,kit,replicator,rtx_sensor,ros_distro,rosbag2,mcap_storage,python`；未知版本为 null，并在 capabilities.failures 说明，不伪造版本 | P0 |
| `environment.gpu` | `{uuid:string,name:string,driver_version:string,total_memory_bytes:Index}` | 实际选用的渲染 GPU，显存单位 byte；其他可用 GPU 仅列入探测证据，不能改变本字段的对象类型 | P0 |
| `environment.monotonic_clock` | `{name:string,domain_id:Id,cross_process_verified:bool}` | 单调时钟和该次主机启动/会话的时钟域；bool 必须经验证 | P0 |
| `capabilities.recording_id`、`capability_id` | Id | 本次能力报告标识，receipt 必须引用该 ID | P0 |
| `capabilities.status`、`selected_backend` | enum / enum 或 null | status 为 `continuous_verified/barrier_verified/unsupported`；后端为 `continuous/barrier`，首组前锁定；只通过 barrier 时不能宣称 continuous_verified | P0 |
| `capabilities.tests[]` | object[] | 每项含 `name:string,passed:Result,reason:string,evidence_paths:RelativePath[],sample_count:Index`；覆盖第 3 节探测表，不能只留结论 | P0 |
| `capabilities.source_mapping` | sensor_id 到 object 的对象 | 每路含非空 string 的 `annotator,clock_domain,mapping_method`，以及 `native_ref_kind:string,native_ref_scope:string,max_native_lead_groups:Index或null,verified_max_inflight:Index`；记录实际字段名和映射方法，verified_max_inflight>0 且不超过已验证上限 | P0 |
| `capabilities.state_capture_phase` | string | 目标构建实测确定的运动/同步/渲染阶段与接口名称 | P0 |
| `capabilities.failures[]` | `{code:string,message:string,evidence_paths:RelativePath[]}`[] | 无失败为空数组；unsupported 必须有解释 | P0 |
| `source_manifest.recording_id`、`entrypoint` | Id / string | 实际入口，不能只记录仓库名称 | P0 |
| `source_manifest.files[]` | object[] | `path:string,sha256:Hash,size_bytes:Index,origin_path:string或null,modified:bool`；实际执行源码/配置和移植来源；size 单位 byte | P0 |
| `source_manifest.git` | object 或 null | `commit:string或null,dirty:bool,diff_sha256:Hash或null`；无 Git 时 null；源码逐文件哈希仍必需 | P0 |
| `asset_manifest.recording_id`、`root_asset` | Id / string | 实际主机根 USD 地址；与第 2 节目标一致或明确报告偏差 | P0 |
| `asset_manifest.stage_meters_per_unit`、`stage_up_axis` | Float / enum | 正长度比例 m/Stage单位；up axis 为 `Y/Z`，保存实际值 | P0 |
| `asset_manifest.dependencies[]` | object[] | `uri:string,kind:string,resolved:bool,sha256:Hash或null,size_bytes:Index或null,reason:string或null`；实际层、材质、几何与传感器依赖；无法哈希必须说明，不能用根 USD 哈希替代 | P0 |
| `asset_manifest.session_overrides[]` | object[] | `prim_path:string,attribute:string,before:any,after:any,usd_type:string,unit:string`；关闭动力学、tick 和本项目资源改动必须记录；不可序列化原生句柄禁止写入 | P0 |
| `render_profile.recording_id` | Id | 本次渲染设置归属 | P0 |
| `render_profile.requested`、`effective` | object | 各含 `renderer_mode:string,dlss_mode:Index,aa_mode:Index,frame_generation:bool,motion_blur:bool,formal_subframes:Index,png_compress_level:Index`；effective 来自实际读回，不是复制 requested；formal_subframes=1，PNG level 为 0..9 | P0 |
| `render_profile.settings[]` | object[] | `path:string,requested:any,effective:any,value_type:string`；保存影响质量/采样的完整设置路径及实值 | P0 |
| `render_profile.products[]` | object[] | `sensor_id:Id,render_product_path:string,resolution:Index[2]或null`；相机分辨率 `[1920,1080]`，非图像产品无图像尺寸则 null | P0 |
| `render_profile.warmup` | object | `min_updates:Index,max_updates:Index,actual_updates:Index,passed:Result,evidence_paths:RelativePath[]`；次数非时间，不改成每组累积 | P0／预热结束 |

`any` 仅用于带有 `usd_type/value_type` 的属性实值快照，仍须为合法 JSON 标量/数组，类型与原生属性相符；不是允许消息主体随意改变字段。动态属性的单位必须记录，不能从属性名字猜测未知量的单位。

作为输出中的配置快照，`job_spec.json` 各字段也必须按以下类型校验。它与第 14 节 JSON 是同一结构，不另创一套名称。

| 配置字段 | 类型 | 含义、单位及约束 | 来源 |
|---|---|---|---|
| `schema_version`、`scene` | integer=4 / string | 新配置契约版本、实际主机 USD 地址；地址可解析且资产通过 preflight | P0 |
| `sensors.camera_ids`、`lidar_ids` | string[] 或 null | null=该类全部可用，[]=不选该类；列表唯一且每 ID 必须有效；合并选择集非空 | P0 |
| `clock.physics_hz`、`loop_hz`、`sample_hz` | integer | Hz，>0；首版 loop_hz=physics_hz，physics_hz/sample_hz 为正整数 | P0 |
| `capture.backend`、`policy` | enum | backend 为 auto_verified/continuous/barrier；policy 为 strict_complete/strict_latest；请求与能力选择结果分开保存 | P0 |
| `capture.requested_groups`、`max_inflight_groups` | Index | 请求组数/在途组上限，均>0；实测可用在途数不得超过字节预算与原生 lead 限制 | P0 |
| `capture.group_timeout_wall_s` | Float | 故障 deadline，墙钟秒，>0；默认 5，不是源时间配准容差 | P0 |
| `capture.source_time_tolerance_ns` | integer | ns，本版固定 2；不因慢回调而扩大 | P0 |
| `capture.translation_tolerance_m`、`rotation_tolerance_rad` | Float | 非负 m/rad，默认 0.001/0.0001；放宽必须有独立精度依据并明确版本/报告 | P0 |
| `capture.state_history_max_records`、`runtime_fallback` | Index / bool | 历史记录数>0；runtime_fallback 固定 false，首组后不静默换后端 | P0 |
| `render.mode`、`dlss_mode`、`aa_mode` | string / Index / Index | 本版 RealTimePathTracing；DLSS/AA 是 SDK 枚举值，默认 2/3，须探测实际支持，不是百分比 | P0 |
| `render.frame_generation`、`motion_blur`、`formal_subframes` | bool / bool / Index | 首版 false/false/1，分别是插值显示、曝光模型及正式完成事件要求 | P0 |
| `render.initial_warmup_min_updates`、`initial_warmup_max_updates` | Index | 初始化 app update 次数，0<min<=max；默认 8/120，不是每组采样数 | P0 |
| `pipeline.max_buffer_bytes`、`slot_bytes` | Index | byte，>0；总驻留估计不超过预算，槽位必须容纳实际完整组 | P0 |
| `pipeline.encoder_workers`、`encoded_queue_groups`、`segment_groups` | Index | 编码线程上限/编码队列组容量/正常分段组数，均>0；无相机不创建图像编码任务 | P0 |
| `pipeline.png_compress_level` | integer | 无量纲 0..9，默认 1；压缩等级不改变无损像素 | P0 |
| `output.directory`、`require_readback_validation` | string / bool | 输出根目录可写；首版回读要求固定 true | P0 |
| `output.image_codec`、`point_fields` | string / string[3] | 固定 png_lossless 和 `["x","y","z"]` | P0 |

### 20.5 传感器与标定注册表

`sensor_registry.json` 保存初始注册表；每段 `/sensor_visualizer/camera_metadata` 保存该段完整注册表快照，包含相机和 LiDAR。沿用 camera_metadata 话题名以兼容入口，schema 3 明确其内容不限于相机。注册表中的 cameras/lidars 只包含本会话选择的传感器，某一类未选择时为空数组，不能缺字段。

| 字段 | 类型 | 含义、单位及约束 | 产生步骤 |
|---|---|---|---|
| `schema_version`、`recording_id` | integer=3 / Id | 注册表契约版本与会话 | P0 |
| `mount_revision`、`calibration_revision` | Index | 安装与标定版本；离散改变增加，不跨段混用 | P0／安全变更边界 |
| `world_frame`、`root_frame`、`horizontal_frame` | string | 如 `world`、`swing_coordinate`、`swing_horizontal_coordinate`；TF 唯一命名，非空无前导斜线 | P0 |
| `stage_meters_per_unit`、`stage_up_axis` | Float / enum | 与 asset_manifest 一致；输出长度均为米 | P0 |
| `cameras[]`、`lidars[]` | object[] | ID 全局唯一；合并后不能为空；原始发现清单另见能力证据 | P0 |
| `cameras[].id`、`sensor_id` | Id | 兼容相机短 ID 与全局 `camera/<id>`；frame_index.cameras 以短 ID 为键 | P0 |
| `cameras[].prim_path`、`frame_id`、`topic_prefix` | string | 真实 USD prim 路径、ROS 光学坐标名、`/camera/<id>`；不可用目录名推断 prim | P0 |
| `cameras[].tick_rate_hz` | Float | 有效原生 tick，Hz，>0；与能力报告和共同采样规则一致 | P0 |
| `cameras[].calibration.model` | string | 本版 `opencv_fisheye`；从实际资产读出，不因 CameraInfo 模型名不同而改变成针孔 | P0 |
| `calibration.width`、`height` | Index | 正像素数，默认 1920、1080；与图像解码尺寸和 CameraInfo 一致 | P0 |
| `calibration.intrinsics` | object | `fx,fy,cx,cy,k1,k2,k3,k4:Float`；fx/fy>0，fx/fy/cx/cy 单位 pixel，k1..k4 无量纲；四项按 OpenCV fisheye 顺序，主点须符合实际标定 | P0 |
| `calibration.exposure_attributes` | 属性值对象 | 以实际 USD 属性名为键，值含 `value,usd_type,unit`；无已支持曝光属性为空对象；仅本版明确关闭 motion blur 不等于一般滚动快门已建模 | P0 |
| `lidars[].id`、`sensor_id` | Id | 短 ID 与全局 `lidar/<id>`；frame_index.lidars 以短 ID 为键 | P0 |
| `lidars[].prim_path`、`frame_id`、`topic` | string | 真正传感器 prim、局部坐标名、`/lidar/<id>/points` | P0 |
| `lidars[].coordinates` | enum | 本版固定 `sensor_local_cartesian_m`，与 XYZ 载荷相同 | P0 |
| `lidars[].axes_description` | string | 该适配器实测确认的轴向及手性；不要给所有 RTX 资产硬套 X前Y左Z上 | P0 |
| `lidars[].tick_rate_hz` | Float | 若单列该字段，与 parameters 中 tickRate 必须一致；本节示例只在 parameters 保存，不要求重复字段 | P0 |
| `lidars[].parameters` | 属性值对象 | 保存扫描、频率、角度、范围、噪声等实际设置，不能只记录 points；每项 `value:any,usd_type:string,unit:string` | P0 |

LiDAR 必须包含 `omni:sensor:Core:instantLidar`（bool，true）、`omni:sensor:Core:scanRateBaseHz`（原生整数，Hz）、`omni:sensor:tickRate`（原生数值，Hz）和实际 scanType；范围属性为米，角度单位按 SDK 原属性记录，不隐式度/弧度转换。无量纲单位记为 `1`。如某个版本使用不同属性路径，capabilities 必须提供真实路径映射，不能伪造上述属性存在。

### 20.6 目标采样与实际状态

**Ticket** 是 P1 产生的内部数值对象，也是 `schedule.jsonl` 的 `scheduled` 事件内容；不包含传感器载荷或原生句柄。

| 字段 | 类型 | 含义、单位及约束 | 产生步骤 |
|---|---|---|---|
| `recording_id`、`epoch_id`、`segment_id` | Id | 会话、时间域和写入段归属；和最终组一致 | P1 |
| `group_id` | Index 或 null | strict_complete 可提前预留输出序号；strict_latest 在 P1 为 null，P4 合格后分配连续输出序号；不以此判断是否有采样缺口 | P1／P4 |
| `target_index` | Index | 从 0 开始的正式计划网格序号，丢组不重排 | P1 |
| `target_step` | Index | epoch 内实际物理步编号，与 StateRecord.physical_step 精确相等 | P1 |
| `simulation_time_ns` | Ns | 网格期望时刻，P2/P4 核对实际物理步时间后才能用作组目标时间；允许的转整数偏差按第 4 节，不能改网格掩盖错步 | P1／P2／P4 |
| `expected_sensor_ids` | Id[] | 两类合并的排序后全局 ID 列表，唯一、非空，与注册表完全一致 | P1 |
| `slot`、`generation` | Index | 预留 mmap 槽号和本次占用代次；generation 每次复用增加，拒绝旧 ACK | P1 |
| `reserved_monotonic_ns`、`deadline_monotonic_ns` | Ns | 同一单调时钟域，deadline 大于 reserved；默认差 5000000000 ns；不是传感器曝光时刻 | P1 |

**StateRecord** 保存 actual 状态，是 frame_index.state 的完整内容。根/水平参考帧 Pose 均在 world 中表达，关节名/类型/位置按同一索引对应。

| 字段 | 类型 | 含义、单位及约束 | 产生步骤 |
|---|---|---|---|
| `epoch_id`、`scene_generation` | Id | 时间域和本次实际加载的场景实例；重载必须改变 scene_generation，防止旧回调混入 | P2 |
| `physical_step`、`sim_time_ns` | Index / Ns | 实际物理步与实际时间；不能取墙钟、UI update 次数或指令时刻 | P2 |
| `state_revision`、`mount_revision`、`calibration_revision`、`command_revision` | Index | 分别是实际状态快照、安装、标定和已生效命令版本；命令版本是来源引用，不能代替 actual 值 | P2 |
| `snapshot_monotonic_ns` | Ns | 状态读回完成时刻，用于处理耗时；早于关联载荷的渲染采样阶段 | P2 |
| `root`、`horizontal` | Pose | 实际整机根和水平参考帧在 world 中的米制姿态；TF 从两者计算相对关系 | P2 |
| `joints.names`、`joints.types` | string[] / enum[] | 实际关节唯一名称，type 为 `revolute/prismatic`；数组长度一致 | P2 |
| `joints.position` | Float[] | 与 names 等长；revolute 为 rad，prismatic 为 m；有限且满足资产中已声明限位 | P2 |
| `joints.velocity`、`joints.effort` | Float[] | 为空表示无有效标签，否则必须与 names 等长；velocity 为 rad/s 或 m/s，effort 为 N·m 或 N | P2／明确派生 |
| `joints.velocity_source` | enum | `unavailable/actual_sdk/derived_actual_difference`；本版规定运动中被强制归零的 SDK velocity 不能标 actual_sdk | P2 |
| `joints.effort_source` | enum | `unavailable/actual_sdk`；未仿真接触力时不捏造 effort | P2 |
| `sensor_world_matrices_usd` | sensor_id 到 UsdMatrix 的对象 | 每一路期望传感器恰有一项，实际读回、米制、不可变；相机项仍为 USD 相机坐标，光学转换在 P5 做 | P2 |

若启用差分速度，必须额外保存 `joints.velocity_evidence`：`previous_physical_step:Index,previous_state_sha256:Hash,dt_ns:Ns,method:string`，dt>0；不能跨 epoch、安装离散变更或无证据的跳步差分。默认示例 velocity/effort 为空并标 unavailable，不把未知速度写成零。

### 20.7 每路原生载荷证据

**SensorEvidence** 是 P3 receipt 的证据在 P4/P5 后补齐的输出形式，分别放在 `frame_index.cameras[<id>]` 和 `frame_index.lidars[<id>]`。P3 日志只包含已产生的字段；PNG 和哈希字段由后台补齐，不要求 Writer 回调进行编码或大量哈希计算。

| 共同字段 | 类型 | 含义、单位及约束 | 产生步骤 |
|---|---|---|---|
| `sensor_id`、`kind` | Id / enum | 注册表全局 ID；kind 为 `camera/lidar`，与外层容器一致 | P3 |
| `source_time_s` | Float | 从载荷同一完成事件取得/映射出的原始物理仿真秒，完整保留浮点值 | P3 |
| `source_time_ns` | Ns | source_time_s 按统一的最近整数、恰好半数取偶转换得到 ns；不平移、不强行写成目标时间 | P3 |
| `source_time_error_ns` | Ns | `source_time_ns - simulation_time_ns`，有符号 ns；绝对值<=2，且源时间定位的物理步必须等于 target_step | P4 |
| `native_ref` | object | 下面定义的原生引用；必须有实测支持的事件证据，不能用 receipt_seq 代替 | P3 |
| `source_frame_id` | string 或 null | SDK 原生帧 ID 精确值，按原生作用域解释；无接口为 null；同一路同 epoch 不允许重复事件提交 | P3 |
| `receipt_seq` | Index | 会话内 receipt 的项目计数，唯一；只用于诊断接收顺序，不证明原生新鲜度 | P3 |
| `source_time_provenance` | object | `annotator:string,clock_domain:string,mapping_method:string,capability_id:Id`；必须对应 P0 已验证的物理时间映射，不能用 callback_current_time | P0／P3 |
| `received_monotonic_ns`、`copy_completed_monotonic_ns` | Ns | 回调收到完成载荷、独立 CPU 物化结束的单调时刻；后者不早于前者，用于测量主机物化 | P3 |
| `to_world` | UsdMatrix | 兼容字段：目标 StateRecord 中该传感器历史 USD 坐标到 world 的米制矩阵 | P2／P4 |
| `rendered_to_world` | UsdMatrix | 来自该载荷实际相机 view/RTX transform，经已验证的转换与单位归一化后保存的 USD 坐标到 world 矩阵 | P3 |
| `translation_error_m`、`rotation_error_rad` | Float | 两个矩阵的位姿差，>=0，分别<=0.001 m、0.0001 rad；旋转用测地角，不用最大元素差代替 | P4 |
| `ownership` | enum | 输出合格组必须为 `owned_cpu`；SDK 借用数组/句柄不允许进入正式组 | P3／P4 |
| `shape`、`dtype`、`byte_order` | Index[] / string / enum | 归一化载荷的维度、dtype 与字节序；byte_order 为 `not_applicable/little`，逐传感器类型按下面约束 | P3 |
| `raw_nbytes`、`raw_payload_sha256` | Index / Hash | P3 自有、归一化载荷的字节数与哈希；单位 byte；哈希由后台对这些确定的字节计算 | P3／P5 |

`native_ref` 的字段全部存在：`kind:string,scope:string,numerator:NativeInteger或null,denominator:NativeInteger或null,event_id:string或null`。`kind=rational_time` 时分子/分母非空、分母>0；等价原生事件引用可使用经 P0 验证的其他 kind，此时 event_id 非空并保存对应字段映射，分子/分母可为 null。scope 必须标明 RenderProduct 或原生事件域。不能跨 scope 比大小，也不能把有理数引用相除就直接当 source_time_s。

| 相机专有字段 | 类型 | 含义、单位及约束 | 产生步骤 |
|---|---|---|---|
| `producer_shape` | Index[3] | SDK 物化前约定的像素形状，本版典型 `[1080,1920,4]`；真实通道数按实际返回记录 | P3 |
| `shape`、`dtype`、`byte_order` | `[H,W,3]` / `uint8` / `not_applicable` | 正式原始像素是 HWC、C 连续 RGB，无 alpha；与 PNG 解码完全一致 | P3／P5 |
| `camera_model`、`image_encoding` | string | 本版 `opencv_fisheye`、`rgb8`，不是去畸变后针孔图像 | P0／P5 |
| `encoded_codec` | string | 固定 `png`，无损 8-bit RGB PNG | P5 |
| `encoded_nbytes`、`encoded_payload_sha256` | Index / Hash | PNG 字节数及 SHA-256；与 CompressedImage.data 一致，不是整条 CDR 消息 hash | P5 |
| `calibration_revision` | Index | 与组、StateRecord 和当段 CameraInfo/注册表一致 | P0／P5 |

相机 `raw_nbytes=H*W*3`。RGB 原始哈希针对归一化 RGB，不针对 SDK 的 RGBA 或含行 padding 的数组。不能用忽略 alpha 的约定同时忽略颜色通道转换；RGB/BGR 顺序必须经过验证。

| LiDAR 专有字段 | 类型 | 含义、单位及约束 | 产生步骤 |
|---|---|---|---|
| `shape`、`dtype`、`byte_order` | `[N,3]` / `<f4` / `little` | C 连续小端 float32；每行为一个 XYZ 点 | P3／P5 |
| `points` | Index | N，>=0；空点云允许，但仍需新采样时间/事件证据 | P3 |
| `fields` | string[3] | 固定 `["x","y","z"]`；首版没有 intensity、normal、ring 或每点时间，不能声称已生成这些标签 | P5 |
| `coordinates` | string | 固定 `sensor_local_cartesian_m`，三个分量单位 m，局部轴向由注册表说明 | P0／P5 |

LiDAR `raw_nbytes=N*12`，等于 PointCloud2.data 长度；首版要求输入与输出点全部有限，非有限输入拒绝并报错，不静默删点，输出 is_dense=true。未来若支持过滤，须单独定义策略、原始/移除点数字段和 schema 版本。空数据哈希为 SHA-256(empty bytes)，不是 null。

### 20.8 逐组 frame_index 结构

`/sensor_visualizer/frame_index` 使用 `std_msgs/msg/String`，String.data 是下列 UTF-8 JSON 对象的文本。ROS 消息本身没有 Header，因此组时刻由其中的 simulation_time_ns 和 rosbag timestamp 双重约束。它只描述 P4 合格且 P5 已完成载荷编码的组，不表示 P6 已保存或 P7 已通过。

| 字段 | 类型 | 含义、单位及约束 | 产生步骤 |
|---|---|---|---|
| `schema_version` | integer=3 | 新连续采集语义；旧 schema 不自动解释为本版 | P5 |
| `recording_id`、`epoch_id`、`segment_id` | Id | 与 Ticket、state、当段元数据一致 | P1／P5 |
| `group_id`、`target_index`、`target_step` | Index | 输出序号、计划序号、实际目标物理步；严格同步主键仍是 recording/epoch/target_step | P1／P4 |
| `simulation_time_ns` | Ns | 该实际物理步时间，等于 state.sim_time_ns；所有组内 ROS 时间由此拆分 | P2／P4 |
| `backend`、`policy` | enum | `continuous/barrier`，`strict_complete/strict_latest`；与锁定会话一致 | P0／P5 |
| `expected_sensor_ids` | Id[] | 与 Ticket、注册表及两类 evidence 的 sensor_id 集合相等 | P1／P4 |
| `state_revision`、`mount_revision`、`calibration_revision` | Index | 与嵌套 state、对应注册表一致；不在回调中读最新版本 | P2／P4 |
| `state` | StateRecord | 20.6 的完整不可变 actual 状态 | P2 |
| `state_sha256` | Hash | 对 state 的 CJSON1 字节求哈希，规则见 20.11；不能替代原生位姿验证 | P5 |
| `cameras`、`lidars` | 短 ID 到 SensorEvidence 的对象 | 每个选中 ID 恰一项；未选类别为 `{}`，不是 null；每路 raw/encoded hash 已补齐 | P3～P5 |
| `sync_checks` | object | 下表五项及误差统计；合格组所有检查为 true | P4 |
| `validated_monotonic_ns` | Ns | TimeJoiner 完成生产端同步校验的时刻；不代表独立回读时刻 | P4 |

| sync_checks 字段 | 类型 | 含义及约束 | 产生步骤 |
|---|---|---|---|
| `all_sensors_present` | bool | 与期望集合完全相等，每路恰一次 | P4 |
| `source_time_ok` | bool | 每路源时间精确映射目标物理步，绝对 ns 差<=2 | P4 |
| `pose_ok` | bool | 每路平移和旋转误差分别通过，不以时间相同代替 | P4 |
| `freshness_ok` | bool | 原生采样事件未重复且属于该载荷，静止时同字节可合法 | P4 |
| `state_epoch_ok` | bool | 时间域、场景实例、安装/标定与历史 state 相符 | P4 |
| `max_abs_source_time_error_ns` | Ns | 各路绝对时间差的最大值，非负且<=2 | P4 |
| `max_translation_error_m`、`max_rotation_error_rad` | Float | 各路误差最大值，分别为 m/rad，不能混为矩阵误差 | P4 |

不合格输入只记录 receipts/groups 的拒绝事件及 failure，不写正式 frame_index 或 group_commit。不能出现 sync_checks=false 但作为 READY 数据提交的正式组。

### 20.9 MCAP 话题、消息层级与时间

以下话题集合由选中的相机数 C、LiDAR 数 L 决定，至少 C+L>=1。每组按相机短 ID 排序后依次写图像、CameraInfo、pose，再按 LiDAR 短 ID 排序写点云，最后写 TF、JointState、root pose、Clock、frame_index 和 group_commit。同一话题每组恰一条，原生回调乱序不改变输出顺序。

| 话题 | ROS 2 类型 | 频率与层级 | 内容来源 |
|---|---|---|---|
| `/camera/<id>/image_raw/compressed` | `sensor_msgs/msg/CompressedImage` | 每选中相机每正式组 1 条 | P3 RGB → P5 PNG；Header 来自 P2/P4 |
| `/camera/<id>/camera_info` | `sensor_msgs/msg/CameraInfo` | 每选中相机每正式组 1 条 | P0/P2 的当段标定 → P5；Header 来自 P2/P4 |
| `/camera/<id>/pose` | `geometry_msgs/msg/PoseStamped` | 每选中相机每正式组 1 条 | P2 历史相机矩阵 → P5 光学坐标 Pose |
| `/lidar/<id>/points` | `sensor_msgs/msg/PointCloud2` | 每选中 LiDAR 每正式组 1 条 | P3 局部 XYZ → P5 字段与序列化 |
| `/tf` | `tf2_msgs/msg/TFMessage` | 每正式组 1 条，包含 2+C+L 个 TransformStamped | P2 actual 根/参考帧/传感器姿态 → P5 |
| `/joint_states` | `sensor_msgs/msg/JointState` | 每正式组 1 条 | P2 actual 关节；不可用速度/力保持空数组 |
| `/excavator/root_pose` | `geometry_msgs/msg/PoseStamped` | 每正式组 1 条 | P2 actual 根 Pose |
| `/clock` | `rosgraph_msgs/msg/Clock` | 每正式组 1 条 | P2/P4 合格的物理采样时间 |
| `/sensor_visualizer/frame_index` | `std_msgs/msg/String` | 每正式组 1 条，data 内是 schema 3 JSON | P1～P5 的组与每路证据，见 20.8 |
| `/sensor_visualizer/group_commit` | `std_msgs/msg/String` | 每正式组最后 1 条，data 内是 schema 1 JSON | P5 实际 CDR 字节清单，P6 最后写入 |
| `/sensor_visualizer/run_metadata` | `std_msgs/msg/String` | 每段开头 1 条，data 内是 schema 3 JSON | P0 配置、能力、epoch 和段归属 |
| `/sensor_visualizer/camera_metadata` | `std_msgs/msg/String` | 每段开头 1 条，data 内是 schema 3 JSON | P0/安全变更后的完整 sensor_registry 快照 |

每组普通消息数为 `3*C+L+5`，group_commit 不计入自己的 message_count；实际每组写入 `3*C+L+6` 条。首组之前另有两条段元数据，不计入任何组的 commit。1 相机+1 LiDAR 时，普通消息 9 条，加 commit 为 10 条，段首另加 2 条；4 相机+13 LiDAR 时为 30 条普通消息，加 commit 为 31 条。

所有组内带 Header 的消息及每个 TF TransformStamped.stamp 均等于组目标时刻；`Clock.clock` 同值；rosbag2 写入 timestamp（MCAP log time）也为该值。若插件填写 MCAP publish time，要求同值并记录配置；不能写 wall time。段元数据的 rosbag timestamp 为该段首个正式目标时刻，不宣称元数据本身具有传感器采样 Header。不同 epoch 可以时间回退，读取端必须按段归属解析，不能仅按 timestamp 跨 epoch 拼包。

**CompressedImage**：

| 字段 | ROS 类型 | 含义、单位及约束 | 产生步骤 |
|---|---|---|---|
| `header` | Header | stamp=组目标时刻，frame_id=该相机 optical frame | P2/P4 → P5 |
| `format` | string | 固定 `rgb8; png compressed rgb8`，声明原图与压缩颜色顺序 | P5 |
| `data` | uint8[] | PNG 文件字节；无损、8-bit、RGB；解码后 H/W/通道和 raw hash 必须与 evidence 一致 | P5 |

**CameraInfo**：

| 字段 | ROS 类型 | 含义、单位及约束 | 产生步骤 |
|---|---|---|---|
| `header` | Header | 与同组图像时间、光学 frame_id 一致 | P2/P4 → P5 |
| `height`、`width` | uint32 | 像素行/列，>0，与 PNG 解码尺寸一致 | P0 → P5 |
| `distortion_model` | string | 本版 `equidistant`，对应 OpenCV fisheye 模型 | P0 → P5 |
| `d` | float64[]，长度 4 | `[k1,k2,k3,k4]`，无量纲；不能套 plumb_bob 的五系数顺序 | P0 → P5 |
| `k` | float64[9] | 行主序 `[fx,0,cx,0,fy,cy,0,0,1]`；焦距/主点单位 pixel | P0 → P5 |
| `r` | float64[9] | 行主序单位矩阵，无量纲；首版未做立体矫正 | P5 |
| `p` | float64[12] | 行主序 `[fx,0,cx,0,0,fy,cy,0,0,0,1,0]`；沿用兼容输出，不能单用 P 对原始鱼眼图像作针孔投影 | P0 → P5 |
| `binning_x`、`binning_y` | uint32 | 本版 0，表示无 binning，不是输出尺寸为零 | P5 |
| `roi.x_offset`、`y_offset`、`height`、`width` | uint32 | 本版均 0，表示完整图像，无裁剪；单位 pixel | P5 |
| `roi.do_rectify` | bool | 本版 false；不能把原始鱼眼 PNG 标为已去畸变 | P5 |

这是保留既有入口的原始鱼眼契约。训练投影使用 registry 的 fisheye 参数和 D/K，不因存在 r/p 就认为图像已经 rectified。若未来增加去畸变图像，应新设话题与版本，不能改变 image_raw 的含义。

**PointCloud2 及 PointField**：

| 字段 | ROS 类型 | 含义、单位及约束 | 产生步骤 |
|---|---|---|---|
| `header` | Header | stamp=组目标时刻，frame_id=LiDAR 局部 frame，非 world | P2/P4 → P5 |
| `height`、`width` | uint32 | 本版 height=1，width=N；无组织点云；N=0 合法 | P3 → P5 |
| `fields` | PointField[]，长度 3 | 固定 x/y/z，顺序一致；每项字段见下面一行 | P5 |
| `fields[].name`、`offset`、`datatype`、`count` | string / uint32 / uint8 / uint32 | 名 x/y/z，offset 为 0/4/8 byte，datatype=7（FLOAT32），count=1；没有额外 padding | P5 |
| `is_bigendian` | bool | 固定 false；实际 data 必须小端，不是只改标志 | P5 |
| `point_step`、`row_step` | uint32 | byte；point_step=12，row_step=12*N；乘积/ROS uint32 容量须检查 | P5 |
| `data` | uint8[] | 按 `[x0,y0,z0,x1,y1,z1,...]` 小端 float32 排列，局部单位 m；长度=height*row_step=12*N | P3 → P5 |
| `is_dense` | bool | 本版所有输出点有限，因此 true；空点云也 true；有 NaN/Inf 不得伪标 true | P4/P5 |

**PoseStamped、TFMessage、JointState、Clock、String**：

| 消息及字段 | ROS 类型 | 含义、单位及约束 | 产生步骤 |
|---|---|---|---|
| PoseStamped.`header` | Header | camera pose 和 root pose 的 frame_id 都为 world；stamp 为组时刻 | P2/P4 → P5 |
| PoseStamped.`pose.position.x/y/z` | float64 | camera 为光学原点、root 为整机根，均 world 中的米制位置 | P2 → P5 |
| PoseStamped.`pose.orientation.x/y/z/w` | float64 | xyzw 单位四元数；camera 是 optical 到 world，root 是 root 到 world | P2 → P5 |
| TFMessage.`transforms` | TransformStamped[] | 本版恰 2+C+L 条，无重复 child、无环、每 child 只有一个 parent | P2 → P5 |
| TransformStamped.`header`、`child_frame_id` | Header / string | Header.frame_id=parent，child_frame_id=child；所有 stamp 为该组时刻 | P2 → P5 |
| TransformStamped.`transform.translation.x/y/z` | float64 | child 原点在 parent 中的位置，m | P2 → P5 |
| TransformStamped.`transform.rotation.x/y/z/w` | float64 | child 到 parent 的单位四元数，xyzw、无量纲 | P2 → P5 |
| JointState.`header` | Header | 组时刻，frame_id 保持空字符串；关节标量不凭空增加空间 frame | P2/P4 → P5 |
| JointState.`name`、`position` | string[] / float64[] | 从 state.joints.names/position 逐项复制，顺序相同；rad 或 m | P2 → P5 |
| JointState.`velocity`、`effort` | float64[] | 与 state 同值，空数组表示无标签；单位 rad/s、m/s、N·m、N 按关节类型 | P2 → P5 |
| Clock.`clock` | RosTime | 没有 Header；物理采样时刻，不是 GUI timeline 播放进度 | P2/P4 → P5 |
| String.`data` | string | 完整合法 JSON 的文本，不能用 Python repr 或二次 Base64 代替；各话题 schema 分别定义 | P5 |

TF 树为 `world → horizontal → root → {camera optical / LiDAR local}`。相机光学轴为 X右、Y下、Z前；从 Gf 相机矩阵得到 `optical_to_world_usd = diag(1,-1,-1,1) @ camera_to_world_usd`，再按已验证的行/列约定生成 ROS 变换。LiDAR 使用注册表中的原生局部轴向。TF、pose、frame_index.to_world 之间必须可以独立转换并复算一致，不能把不同坐标系的矩阵直接逐元素比较。

标准字段类型和语义以 ROS 官方消息定义为依据：[CompressedImage](https://raw.githubusercontent.com/ros2/common_interfaces/jazzy/sensor_msgs/msg/CompressedImage.msg)、[CameraInfo](https://raw.githubusercontent.com/ros2/common_interfaces/jazzy/sensor_msgs/msg/CameraInfo.msg)、[PointCloud2](https://raw.githubusercontent.com/ros2/common_interfaces/jazzy/sensor_msgs/msg/PointCloud2.msg)、[JointState](https://raw.githubusercontent.com/ros2/common_interfaces/jazzy/sensor_msgs/msg/JointState.msg)、[Time](https://raw.githubusercontent.com/ros2/rcl_interfaces/jazzy/builtin_interfaces/msg/Time.msg)。实际运行 ROS 发行版仍须在 P0 固定；不能仅因为这些字段同名就跳过安装版本核对。

### 20.10 段元数据结构

`run_metadata.data` 内 JSON 必须包含下列字段，避免单独打开一个 MCAP 时无法解释时间域、来源和配置。`camera_metadata.data` 内为 20.5 的完整注册表，不是其路径字符串。

| run_metadata 字段 | 类型 | 含义、单位及约束 | 产生步骤 |
|---|---|---|---|
| `schema_version` | integer=3 | 本版段级运行契约 | P5 |
| `recording_id`、`epoch_id`、`segment_id`、`scene_generation` | Id | 该段归属及真实加载场景实例 | P0/P1 |
| `backend`、`policy` | enum | 已锁定的后端和策略，同 frame_index | P0 |
| `expected_sensor_ids` | Id[] | 本段完整选择集，等于注册表 | P0 |
| `physics_hz`、`loop_hz`、`sample_hz` | integer | Hz，>0；本版 physics_hz/sample_hz 为整数 | P0 |
| `sim_origin_ns`、`physical_step_origin` | Ns / Index | epoch 采样网格的仿真时间/物理步锚点；不要求原点必为 0 | P1/P2 |
| `first_target_step`、`sampling_stride_steps` | Index | 第一个正式目标及相邻目标物理步差；stride=physics_hz/sample_hz，>0 | P1 |
| `native_sample_hz`、`selection_stride` | integer | 原生共同事件 Hz、抽取每几个完整事件；本版 10Hz→5Hz 时分别 10、2；默认 10、1 | P0/P1 |
| `mount_revision`、`calibration_revision` | Index | 该段固定版本；变化需要新段 | P0/P2 |
| `job_spec_sha256`、`capabilities_sha256`、`source_manifest_sha256`、`asset_manifest_sha256`、`render_profile_sha256` | Hash | 对对应已经冻结的 JSON 文件原始字节求 SHA-256，不是对象重排后求 hash | P0/P5 |
| `registry_snapshot_sha256` | Hash | 对该段 registry 对象的 CJSON1 字节求 hash；因为后续段 registry 可能与初始 sensor_registry.json 不同 | P5 |

理数网格规则为 `target_ns = sim_origin_ns + round_even((target_step-physical_step_origin)*1000000000/physics_hz)`；round_even 用整数/有理数实现，不能先累计浮点。P2 的实际时间仍是权威，必须核对网格与源时间。通过抽取降低输出采样率时，保存 native_sample_hz 与 selection_stride；不是把源时刻改为新的 Header 来伪造频率。

### 20.11 group_commit 与哈希规则

group_commit 固定使用 String.data 内的 schema 1 JSON，避免依赖未定义的自订 ROS 消息。生成时必须已经取得该组所有普通消息的实际 CDR 字节。

| 字段 | 类型 | 含义、单位及约束 | 产生步骤 |
|---|---|---|---|
| `schema_version` | integer=1 | 提交清单版本 | P5 |
| `recording_id`、`epoch_id`、`segment_id` | Id | 与该组 frame_index 一致 | P1/P5 |
| `group_id`、`target_index`、`target_step`、`simulation_time_ns` | Index / Index / Index / Ns | 与 frame_index 逐项相等，防止提交清单关联到另一组 | P4/P5 |
| `state_sha256`、`sync_checks` | Hash / object | 同 frame_index，不另生成另一套状态/结论 | P4/P5 |
| `message_count` | Index | `3*C+L+5`，等于 messages 长度；不包括 commit 自身和段元数据 | P5 |
| `messages` | object[] | 按 20.9 固定写入次序排列，每条普通消息一项 | P5 |
| `messages[].ordinal` | Index | 从 0 开始连续编号，最后为 message_count-1 | P5 |
| `messages[].topic`、`ros_type` | string | 精确话题名及 `package/msg/Type`，不得仅 hash 载荷而忽略对应话题 | P5 |
| `messages[].cdr_nbytes`、`cdr_sha256` | Index / Hash | 实际传给 SequentialWriter 的序列化字节长度与 SHA-256，包括 CDR encapsulation；byte | P5 |
| `group_hash` | Hash | 对 messages 数组完整内容的 CJSON1 字节求 SHA-256；包含 ordinal/话题/类型/长度/消息哈希 | P5 |
| `encoded_monotonic_ns` | Ns | 全部普通消息与提交清单构建完成时刻，非保存完成时刻 | P5 |

本版 **CJSON1** 只对本项目 schema 对象使用：Python 3 `json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)` 的 UTF-8 字节，无 BOM、无尾部换行。数值类型按 schema 固定，不在 hash 之前把 Float 的 0.0 换成整数 0；Ns/NativeInteger 保持字符串。实现与独立验证器共享这份规范，但验证器独立计算值。不同语言实现必须通过固定向量验证浮点文本一致，不能默认任意 JSON 库重编码得到相同字节。

六种哈希的输入分别为：①原始 RGB/XYZ 的归一化字节；②PNG 字节；③state 的 CJSON1；④每条实际 CDR；⑤commit.messages 的 CJSON1；⑥清单指向文件的原始字节。它们不能相互代替。commit 自身不进入 messages/group_hash，避免自引用；其完整消息仍在 MCAP 文件哈希覆盖内。

独立验证器从 MCAP 取得原始 CDR bytes 复算③④⑤，同时实际解码 PNG/XYZ 复算①②，最后核对文件⑥。不能先解码 ROS 再重序列化、只比较重序列化后的 hash，因为这可能掩盖原字节被改变。group_commit 出现只证明提交标记被写到此处，不能单独证明持久化、文件完整或通过回读。

### 20.12 JSONL 证据与内部 ACK

所有 JSONL 行使用统一信封：

| 字段 | 类型 | 含义、单位及约束 | 产生步骤 |
|---|---|---|---|
| `schema_version`、`recording_id` | integer=1 / Id | 日志协议版本及会话 | P0～P7 |
| `epoch_id`、`segment_id` | Id 或 null | 尚未进入正式段的初始化事件可 null；组事件必须有实际归属 | 对应事件 |
| `event_seq` | Index | 每个日志文件内递增、唯一，不能当原生帧 ID；不要求不同文件同序号 | 对应事件 |
| `event_type` | string | 下表列出的事件类型；具体故障以 error.code 区分 | 对应事件 |
| `monotonic_ns` | Ns | 事件产生时刻；同一个 environment.monotonic_clock.domain_id | 对应事件 |
| `data` | 对应事件对象 | 下表规定的内容，不写原始像素/点云/Base64 和原生对象 | 对应事件 |

组引用 **GroupRef** 含 `recording_id:Id,epoch_id:Id,segment_id:Id,group_id:Index或null,target_index:Index,target_step:Index,simulation_time_ns:Ns`。Error 含 `code:string,message:string,evidence_paths:RelativePath[]`。信封归属与 data 中归属必须一致，不允许两者各写一个值。

| 文件与 event_type | data 的字段和类型 | 含义、约束及产生步骤 |
|---|---|---|
| `schedule.jsonl:scheduled` | 完整 Ticket | P1，记录实际成功预留且安排的目标；未预留的目标不伪标 scheduled |
| `schedule.jsonl:backpressure_paused/resumed` | `reason:string,next_target_index:Index,inflight_groups:Index,resident_buffer_bytes:Index` | P1/P6，压力原因、恢复目标和驻留预算，byte；不改变下一目标时间 |
| `receipts.jsonl:received` | `receipt_seq:Index,sensor_id:Id,group:GroupRef或null,disposition:string,evidence:object或null,error:Error或null` | P3/P4；disposition 为 `accepted/duplicate/conflicting_duplicate/invalid/late/unrequested`，只有 accepted 可关联正式组；拒绝需 error |
| `receipts.data.evidence` | SensorEvidence 的 P3 子集 | 只含 `sensor_id,kind,source_time_s,source_time_ns,native_ref,source_frame_id,receipt_seq,source_time_provenance,received_monotonic_ns,copy_completed_monotonic_ns,rendered_to_world,ownership,shape,dtype,byte_order,raw_nbytes`；相机加 producer_shape，LiDAR 加 points；全部是已取得的真实值。无法形成有效证据时为 null，错误说明哪个原始字段不合法 |
| `groups.jsonl:validated` | `group:GroupRef,receipt_seqs:Index[],state_revision:Index,sync_checks:object` | P4；receipt_seqs 与期望传感器一一对应，无重复；此时不要求 PNG/CDR hash |
| `groups.jsonl:encoded` | `group:GroupRef,frame_index:object,commit:object` | P5；完整 20.8/20.11；含元数据但不重复 PNG/XYZ/CDR 大字节；编码后不可变 |
| `groups.jsonl:written` | WrittenACK | P6；不是只看到编码队列就计入 written |
| `groups.jsonl:readback_verified` | `group:GroupRef,group_hash:Hash,validator_run_id:Id` | P7；实际逐组解码通过后记录，与 encoded 的 hash 一致 |
| `groups.jsonl:rejected` | `group:GroupRef,error:Error,received_sensor_ids:Id[],missing_sensor_ids:Id[]` | P4/P5/P6；不合格或写入失败；不因此生成正式提交成功记录 |
| `gaps.jsonl:dropped` | `group:GroupRef,reason_code:string,detail:string,received_sensor_ids:Id[],missing_sensor_ids:Id[],policy:string` | strict_latest 的 P1/P4；每个未提交正式目标恰一项。group_id=null；时间/target_index 保留原网格，policy 必为 strict_latest |
| `logs/*.jsonl:lifecycle/error/control` | `component:string,state:string或null,timeline_state:string或null,error:Error或null,detail:string` | 组件运行、独立 timeline 状态和错误诊断；state 若非空遵循第 12 节。具体命令来源/版本在 control 事件中另存 `command_revision:Index,source:string,accepted_monotonic_ns:Ns` |

高频日志可以后台批量落盘，但写入容量受第 10 节字节预算约束。READY 发布之前证据日志必须关闭且其必要组证据齐全；日志队列丢了某条并不许可把该组标成“证据完整”。故障原始日志可以保留截断尾行，最终清单必须明确其状态，不能解析后悄悄忽略。

ACK 是内部进程协议，不是正式传感器话题。每个 ACK 含 `schema_version=1,type:string,recording_id:Id,epoch_id:Id,segment_id:Id,group_id:Index,monotonic_ns:Ns`；字段按下表补充：

| type 与附加字段 | 类型 | 含义、约束及产生步骤 |
|---|---|---|
| `release:slot,generation` | Index / Index | P5/P6，所有编码 worker/view 均已不再引用原槽位后才发；必须检查 recording/group/slot/generation；只授权内存复用 |
| `written:group_hash,message_count` | Hash / Index | P6，所有普通消息及 commit 的 write 调用成功后发；message_count 与 commit 相同；不表示 fsync/回读通过 |
| `failed:error` | Error | 失败原因，由当前处理阶段发出；不能同时为该组发成功 written |

段关闭是单独的 **SegmentClose**：`schema_version=1,type="segment_closed",recording_id,epoch_id,segment_id,closed_monotonic_ns:Ns,files:RelativePath[],success:bool,error:Error或null`。关闭后才允许 P7 开始正式回读；success 只是 writer.close 成功。没有 `durable=true` 的推断字段。验证结果通过 validation/manifest 表达，不把 release、written、closed 当作同一状态。

### 20.13 会话、性能与独立验证报告

**session.json** 是录制结束后冻结的会话报告。写入期间的运行快照仍位于 partial，最终清单不可引用会继续改变的文件。

| 字段 | 类型 | 含义、单位及约束 | 产生步骤 |
|---|---|---|---|
| `schema_version`、`recording_id` | integer=1 / Id | 会话报告版本及归属 | P0～P7 |
| `status`、`outcome`、`timeline_state` | enum / enum / string | status 为第 12 节状态；outcome 为 `completed/stopped/failed` 或进行中的 null；timeline_state 单独保存。提前停止不写 outcome=completed | P6/P7 |
| `started_utc`、`ended_utc` | string / string 或 null | 带时区 ISO 8601 人类时间；不能用于同步 | P0/P7 |
| `backend`、`policy`、`requested_groups` | enum / enum / Index | 本次请求、锁定后端、请求组数>0；用户 Stop 不回改 requested_groups | P0 |
| `epochs[]` | object[] | `epoch_id:Id,scene_generation:Id,sim_origin_ns:Ns,physical_step_origin:Index,first_target_step:Index,physics_hz:integer,sample_hz:integer,segments:Id[]`；顺序为创建顺序 | P1/P6 |
| `counts` | object | 下面定义的完整计数，不同阶段独立记账 | P1～P7 |
| `failure` | Error 或 null | failed 时非空；正常完成为 null；Stop 可另在原始 control 事件说明 | 对应失败阶段 |
| `acceptance_results` | object | 七项 Result：`continuous_ok,sync_ok,completeness_ok,quality_ok,performance_ok,interaction_ok,lifecycle_ok`；每项在 `acceptance_evidence` 保存证据路径和范围 | P7／专项验收 |
| `acceptance_evidence` | 结果名到 object 的对象 | `scope:string,reason:string,evidence_paths:RelativePath[]`，scope 区分本会话、诊断场景、性能轮次、项目整体验收 | P7／专项验收 |

counts 必须包含：`requested,scheduled,validated,written,readback_verified,dropped,gap_groups`（Index，单位组）；`received_by_sensor`（sensor_id→Index，单位有效正式样本）；`duplicate,invalid,late`（Index，单位 receipt）；`queue_full,backpressure_pause`（Index，单位事件）。received_by_sensor 不含预热、重复、拒绝和未请求样本。strict_complete 完整完成时 requested=scheduled=validated=written=readback_verified、每路有效样本数相等、dropped=gap_groups=0；不能把阶段计数相加当作样本总数。

**performance.json** 必须同时给原始轮次和统计定义，不能只给一个加速倍数：

| 字段 | 类型 | 含义、单位及约束 | 产生步骤 |
|---|---|---|---|
| `schema_version`、`recording_id`、`clock_domain_id` | integer=1 / Id / Id | 必须对应 environment 的单调时钟域 | P0/P7 |
| `scope`、`measured_groups`、`warmup_excluded_groups` | string / Index / Index | 测量范围、稳态组数、排除的预热数；按第 16 节对照轮次记录 | P6/P7 |
| `wall_times_s` | object | `cold_start,capture,drain,readback,total:Float`，非负秒；total 为开始到验收结束实际墙钟，不能只算编码 | P6/P7 |
| `throughput` | object | `capture_groups_per_wall_s,usable_groups_per_wall_s:Float或null`；前者=稳态 written组/稳态采集墙钟，后者=readback_verified/全操作 total；无有效分母时 null 并说明 | P6/P7 |
| `latency_ms` | 指标名到 Statistics 的对象 | 必含 `source_materialization,join_wait,png_encode,cdr_serialize,write,group_pipeline,control_input`；ms。单 LiDAR 的 png_encode 可为未测空统计，不假造 0ms | P3～P7 |
| `buffer_peak_bytes`、`inflight_peak_groups` | Index | 同期实际驻留估计与在途组峰值，byte/组；包括所有缓冲阶段 | P6 |
| `rounds[]` | object[] | `variant:string,round_index:Index,recording_id:Id,steady_groups:Index,steady_wall_s:Float,steady_groups_per_s:Float,quality_ok:Result,config_hash:Hash,evidence_paths:RelativePath[]`；variant 为 baseline/candidate | P7／M5 |
| `speedup_vs_baseline`、`performance_ok` | Float 或 null / Result | 相同统计口径 candidate/baseline；基线不成立或质量未通过时不填通过；目标>=2，需完整轮次依据 | M5 |

Statistics 含 `n:Index,median:Float或null,p95:Float或null,p99:Float或null,max:Float或null,unit:string,definition:string`。n=0 时四个数均 null；n>0 时为非负数且 median<=p95<=p99<=max；本版分位数定义固定为升序样本的 nearest-rank，median 取中间值/偶数中间两值平均，并在工具说明中固定。group_pipeline 的范围为收到本组第一路源完成到 written ACK；TimeJoiner wait 从第一路到全路合格，不能把仿真 ns 当性能耗时。

**validation.json** 由独立进程回读实际关闭的 MCAP 后生成；根报告汇总全部段，段报告列出该段实际范围：

| 字段 | 类型 | 含义、单位及约束 | 产生步骤 |
|---|---|---|---|
| `schema_version`、`validator_run_id`、`recording_id` | integer=1 / Id / Id | 独立验证运行标识及会话 | P7 |
| `scope`、`epoch_id`、`segment_id` | enum / Id 或 null / Id 或 null | scope 为 recording/segment/export；根级后两项 null，段级必须有值 | P7 |
| `backend`、`policy`、`environment_path` | enum / enum / RelativePath | 实际后端、策略和运行环境报告；不能用验证器所在 Windows 环境代替采集主机环境 | P7 |
| `validator_source_sha256` | Hash | 实际验证器源码包清单哈希，保留工具版本 | P7 |
| `started_utc`、`finished_utc` | string | 带时区 ISO 8601；验证结束不能早于开始 | P7 |
| `input_files[]` | FileEntry[] | 实际读取的 MCAP/metadata/必要证据文件，定义见 20.14；不是从生产端照抄 hash | P7 |
| `counts` | object | `groups_seen,commits_seen,groups_verified,messages_seen,incomplete_groups,gap_groups:Index`；组数和消息数单位分开 | P7 |
| `checks` | 检查名到 CheckResult 的对象 | 必含 `commit_presence,topic_set,cdr_hashes,payload_hashes,header_times,source_times,state_epochs,freshness,tf_consistency,calibration,point_layout,schedule_completeness`；每项须独立计算 | P7 |
| `max_abs_source_time_error_ns` | Ns 或 null | 本范围各实际路最大绝对时间差；无完整组则 null，不能填 0 通过 | P7 |
| `max_translation_error_m`、`max_rotation_error_rad` | Float 或 null | 复算历史/渲染及 ROS 变换一致性的最大误差，m/rad | P7 |
| `geometry_diagnostics` | object | `executed:bool,passed:Result,reprojection_p95_px:Float或null,point_plane_p95_m:Float或null,evidence_paths:RelativePath[]`；只有已知诊断场景实测才填数，正式场景不能凭空得出几何误差 | P7／M1～M5 |
| `sync_ok`、`completeness_ok`、`file_integrity_ok` | bool | 已执行回读的结论，不能为 null；未运行不生成“已完成”的 validation 文件 | P7 |
| `quality_ok`、`performance_ok` | Result | 对应独立专项验收结论及证据，未做为 null；不能从文件完整自动推导质量或速度通过 | P7／专项验收 |
| `errors[]` | object[] | `code:string,message:string,group:GroupRef或null,sensor_id:Id或null,topic:string或null,evidence_paths:RelativePath[]`；失败的定位信息 | P7 |

CheckResult 含 `passed:Result,checked_items:Index,failed_items:Index,reason:string,evidence_paths:RelativePath[]`。未测 passed=null；实际检查项为零时不能默认为 true。严格完整会话的 schedule_completeness 必须核对请求和所有目标；strict_latest 的同步检查可通过，但 completeness_ok=false，缺口必须逐一核对。文件哈希能证明文件内容一致，不能单独证明成像时间和几何准确。

### 20.14 dataset_manifest 与可交付判定

段和根清单使用同一 schema 1，区别在 scope 与 range。所有引用路径相对该清单目录；根清单只在全部必要报告冻结后生成。所有 FileEntry 均由 P7 对实际文件读取后计算。

| 字段 | 类型 | 含义、单位及约束 | 产生步骤 |
|---|---|---|---|
| `schema_version`、`recording_id` | integer=1 / Id | 清单版本及会话 | P7 |
| `scope`、`epoch_id`、`segment_id` | enum / Id 或 null / Id 或 null | scope 为 recording/segment/export；与 validation 的归属一致 | P7 |
| `created_utc` | string | 发布时间，带时区 ISO 8601 | P7 |
| `backend`、`policy` | enum | 对应数据的后端和策略，不能在导出时改成更严格标签 | P7 |
| `completion_class` | enum | `complete/completed_with_gaps/verified_prefix`；strict_complete 完整请求才是 complete；strict_latest 使用 completed_with_gaps；恢复导出为 verified_prefix | P7 |
| `source_recording_id`、`source_outcome` | Id 或 null / string 或 null | 普通会话为 null；前缀导出必须记录来源及 failed/stopped，原会话保持原结论 | P7 |
| `selected_sensor_ids` | Id[] | 完整非空选择集，与所有段注册表一致或按明确的新段版本记录 | P7 |
| `counts` | object | `requested,scheduled,validated,written,readback_verified,gap_groups:Index`；与范围内报告一致；根级 requested 是原始请求，前缀不得冒充完成原请求 | P7 |
| `ranges[]` | object[] | 每项字段见下面；按 epoch/段创建顺序排列，不跨复位用时间排序 | P7 |
| `files[]` | FileEntry[] | MCAP、rosbag metadata、日志、报告、配置、段清单等实际文件；不包含当前清单自身和当前 READY | P7 |
| `validation_path` | RelativePath | 本范围 validation.json，必须在 files 中，实际回读通过 | P7 |
| `sync_ok`、`completeness_ok`、`file_integrity_ok` | bool | 与独立验证报告一致；READY 要求 sync_ok/file_integrity_ok=true；完整默认采集还要求 completeness_ok=true | P7 |
| `acceptance_results` | 七项 Result 的对象 | 同 session 的有范围验收结论；数据 READY 不自动把速度、质量、交互和长期验收改成 true | P7／专项验收 |
| `ready` | bool | 必须 true 才生成 READY；false 清单只能留在 partial/failed，训练发现拒绝 | P7 |

FileEntry 含 `path:RelativePath,format:string,size_bytes:Index,sha256:Hash,produced_by:string`；size 单位 byte；format 为 json/jsonl/yaml/mcap/text，produced_by 为 P0～P7 中实际产生步骤。原始日志文件即使来自 P3/P6，其最终 FileEntry 哈希也由 P7 计算。

`ranges[]` 的每项为 `epoch_id:Id,segment_id:Id,first_group_id:Index,last_group_id:Index,first_target_index:Index,last_target_index:Index,first_target_step:Index,last_target_step:Index,first_simulation_time_ns:Ns,last_simulation_time_ns:Ns,group_count:Index,mount_revision:Index,calibration_revision:Index`。每项只描述一个非空段，first<=last，group_count>0。strict_latest 的 first/last 范围之间可能有计划缺口，由 gaps.jsonl 和 counts 表明，不能根据范围自动补帧。

“这段 MCAP 已同步且可解析”“本次请求已完整采完”“项目快速连续采集已完整交付”是三个不同结论，分别由独立数据检查、请求计数/缺口、七项专项验收支撑。默认完整交付仍遵守第 18 节：七项必需结果全部 true 且有经回读生成的 READY。训练任务如要求完整时序，必须同时检查 policy、completion_class、completeness_ok，不能只看 ready 或同一 Header。

### 20.15 一份可解析的示例数据

完整示例：[expected_output_example.json](examples/expected_output_example.json)。配套真实二进制载荷：[example_camera_front.png](examples/example_camera_front.png)、[example_lidar_MyAiry_front.xyz_f32le.bin](examples/example_lidar_MyAiry_front.xyz_f32le.bin)。调度信封示例：[example_schedule.jsonl](examples/example_schedule.jsonl)。这些是文档示例附件，正式采集仍将载荷写入 MCAP，不默认创建此类逐帧旁路文件。

示例含单相机 `camera/front` 与单 LiDAR `lidar/MyAiry_front` 的同一个目标组，1920×1080 RGB PNG 与一个 XYZ 点。图像为构造的纯色 `[40,80,120]`，点为局部 `[1,0,0] m`；标定、prim 路径、原生引用和能力 ID 也均是示例值，不声称来自 scene18 实测。

| 示例位置或数值 | 含义及一致性 | 对应步骤 |
|---|---|---|
| recording=`example_only_recording_001`；epoch=`example_only_epoch_000`；segment=`segment_000000` | 全部 Ticket、state、frame_index 使用同一归属 | P1～P5 |
| epoch 原点 900000000 ns；physics=60Hz；sample=10Hz；target_step=6 | `900000000 + 6/60*1000000000 = 1000000000 ns`；第一正式目标是 1s，target_index/group_id 均为 0 | P1/P2 |
| 两路 source_time_s=1.0，source_time_ns=`"1000000000"` | 原始源时间与目标差均为 `"0"` ns；Header、Clock、rosbag timestamp 均对应 1s | P3/P4/P5 |
| 两路 source_frame_id=null；receipt_seq=0/1 | 没有构造假原生帧号；不同 scope 的有理数 native_ref 只是引用示例，不直接等于仿真秒 | P3 |
| root/horizontal 为单位 Pose；camera USD 世界位置 `[1,0,2] m`；LiDAR 世界位置 `[0,0,1] m` | 相机 optical Pose 四元数为 xyzw `[1,0,0,0]`；点的世界位置为 `[1,0,1] m`，坐标变换可复算 | P2/P5 |
| RGB raw_nbytes=6220800；PNG encoded_nbytes=30122 | 前者是 1920*1080*3，后者是实际附件 PNG 字节数；两种哈希不可互换 | P3/P5 |
| XYZ raw_nbytes=12；points=1 | 小端 float32 三值；PointCloud2.width=1、point_step=row_step=12 | P3/P5 |
| 普通 ROS 消息共 9 条 | 3*1+1+5；完整 JSON 的 ros_decoded_view 含九条消息的全部字段 | P5 |

示例外层是方便阅读的容器，**不是新的正式 MCAP 消息 schema**：

| 外层字段 | 类型与含义 | 约束 |
|---|---|---|
| `example_kind`、`not_for_training`、`note` | string / bool / string，构造示例标识与说明 | 固定 synthetic_contract_example、true；不进入训练发现目录 |
| `stages_present`、`stages_not_executed` | string[]，已构造与尚未执行的步骤 | 明确未执行 CDR、MCAP 写入、独立回读；不是实测阶段状态 |
| `epoch_definition` | 20.10 时间网格字段的示例子集 | 用于核算目标时刻，不冒充完整 run_metadata |
| `sensor_registry`、`schedule`、`frame_index` | 20.5、20.6、20.8 的完整对应对象 | schedule 是 Ticket，JSONL 外层见单独附件 |
| `ros_decoded_view.view_format`、`cdr_serialized`、`messages` | string / bool / object[] | view_format=json_with_base64_uint8_arrays；cdr_serialized=false；messages 含解码展示字段 |
| `messages[].topic`、`ros_type`、`rosbag_timestamp_ns`、`fields` | string / string / Ns / ROS 字段对象 | topic/type 对应 20.9；fields 逐字段展示，String.data 仍为 JSON 文本字符串 |
| `fields.data` 的 Base64 展示对象 | `{encoding:string,nbytes:Index,value:string}` | 仅用于图像/点云 uint8[] 的 JSON 阅读形式；encoding=base64，解码长度=nbytes；正式 MCAP 中是 uint8[]，不是该对象 |
| `group_commit`、`validation` | 本示例固定 null | 没有实际 CDR/MCAP，不能捏造提交哈希或验收 true；正式完成数据中这两类对象必须按 20.11/20.13 实际生成 |
| `payload_files[]` | FileEntry[] | 相对 examples 目录的文件路径、格式、大小、实际哈希与产生步骤；示例格式为 png_rgb8/xyz_float32_little_endian，produced_by 用 P3_owned_copy/P5_payload_encoding 细化构造步骤；正式清单见 20.14 |

下面是完整示例中 LiDAR 消息的 JSON 阅读形式，所有字段都可与二进制附件和 frame_index 对照：

```json
{
  "topic": "/lidar/MyAiry_front/points",
  "ros_type": "sensor_msgs/msg/PointCloud2",
  "rosbag_timestamp_ns": "1000000000",
  "fields": {
    "header": {
      "stamp": {"sec": 1, "nanosec": 0},
      "frame_id": "MyAiry_front"
    },
    "height": 1,
    "width": 1,
    "fields": [
      {"name": "x", "offset": 0, "datatype": 7, "count": 1},
      {"name": "y", "offset": 4, "datatype": 7, "count": 1},
      {"name": "z", "offset": 8, "datatype": 7, "count": 1}
    ],
    "is_bigendian": false,
    "point_step": 12,
    "row_step": 12,
    "data": {
      "encoding": "base64",
      "nbytes": 12,
      "value": "AACAPwAAAAAAAAAA"
    },
    "is_dense": true
  }
}
```

对上述 data 做 Base64 解码后，以 `<fff` 读取，得到 `(1.0,0.0,0.0)`。其 SHA-256 为 `480376c6bf738a0227f2bbf2b3506b7cde209152c0ba9a9077e5527169eb292e`。PNG 附件 SHA-256 为 `968ed4724359f6002377bc975cfce661e284a6e3b2802d19e361f7cf7204bcb3`；解码 RGB 的 SHA-256 为 `70692e1fe8ecf4a0b866a7b0bca20c6a106def1a9c35014b7137be205e126620`；state 的 CJSON1 SHA-256 为 `14e7b7f5b42435f653c59130b378957f022973f3f0f6fcfe997a3beb254faef8`。这些值均从本示例实际对象或附件计算，可用于实现前的字段/字节契约核对。

本示例不包含伪造的 .mcap、commit CDR hash、validation 通过结论或 READY。实现 agent 必须在真实 SDK/ROS 环境补上 P5 CDR、P6 写入和 P7 独立回读，产生包含实际提交与验收清单的完整样本，再按第 17 节交付验收。
