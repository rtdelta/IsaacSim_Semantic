# single0601ContinuousRt 连续主路线修复与流水线实现方案

日期：2026-10-14。版本：004。实施状态：C0/C1诊断基线与观测已实施；C2已收敛复现但修复门槛未通过，C3–C6尚未进入。实际结果见[2026-10-14执行报告](../Execution/20261014_execution.md)。

本方案在现有独立项目上修复连续采集的时间与位姿契约，随后实现有界流水线，并完成原003任务书剩余验收。实施顺序为：取得原生事件证据，区分实际射线与位姿元数据问题，通过单组连续同步门槛，再扩大在途窗口和进行性能对照。

本方案细化[002快速同步采集实现方案](002_single0601ContinuousRt_快速同步采集实现方案.md)与[003执行任务书](003_single0601ContinuousRt_Agent执行任务书.md)，不放宽其同步、完整性、质量和交付要求。内部IPC协议的并发改造单独演进版本；已有数据及原001至003文件保持不变。下面列出的新增模块、工具和试验均是执行任务，不代表现有实现已经具备。

## 1 实施起点与目标

### 1.1 已有实现和实测边界

运行目标为 `isaac-new` 单卡L40实例、SSH端口30729，安装Isaac Sim `6.0.1-rc.7+release.42383.32955d8d.gl`、Replicator1.13.27、RTX sensor common3.0.0及ROS2 Jazzy。

远端项目为 `/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt`，输出根为 `/root/gpufree-data/semantic/output/single0601ContinuousRt`。继续使用现有scene18。

常驻产品与Writer、物理PRE运动和POST实际读回、不可变历史、CPU载荷复制、精确组包、CPU worker、commit、独立MCAP回读已经实现。屏障路线已有36份READY、1612组；这些数据不构成连续路线通过证据。

2026-10-13最后一轮连续探测取得两路共58条有效receipt。2026-10-14对原始矩阵复核得到：

| 观察 | 前相机 | MyAiry前雷达 |
|---|---:|---:|
| 连续播放旋转超限 | 0/24 | 9/24 |
| 暂停恢复旋转超限 | 0/5 | 1/5 |
| 最大平移误差 | 约2.12微米 | 约2.12微米 |
| 最大旋转误差 | 约8.02e-8 rad | 约8.727e-4 rad |

异常旋转相当于沿运动方向落后约一个60Hz物理步，但平移对齐且异常间歇出现。对矩阵正交化后仍有10条雷达旋转超限。当前只证实提取器输出的变换与历史状态不符，尚未证实实际射线结果也发生相同错位。

### 1.2 实施目标

1. 每个原生载荷有可追溯的完成事件、源时间、坐标系和位姿来源。
2. 连续主路线在运动中满足同一物理步的时间、实际状态和几何要求。
3. 在证明原生提前量和缓冲容量后，允许采集与编码、保存跨组重叠。
4. 补齐Reset、安装变更、原生交互、故障策略和长期资源验收。
5. 同条件测量相对原v06 keepalive基线的合格数据产能；2倍提升为验收目标，全组合墙钟实时10Hz为扩展目标。

## 2 固定契约与实施范围

| 项目 | 固定要求 |
|---|---|
| 时钟 | 默认60Hz物理及loop、10Hz采样；只按实际物理时间和理数目标网格调度 |
| 时间误差 | 每路映射源时间与实际目标步误差不超过2ns |
| 位姿误差 | 平移不超过1mm，旋转测地角不超过1e-4 rad |
| 传感器 | 正式scene18保留4相机、13雷达；1920×1080、无损PNG、Instant及10Hz scan参数 |
| 状态 | command与actual分开；实际状态在渲染前固定，回调不读取最新场景充当历史 |
| 所有权 | Writer有效回调内完成自有CPU复制；后台不保留原生借用指针 |
| 默认策略 | strict_complete，采样前预留资源；过载减速或安全暂停，计划组不静默丢弃 |
| 发布 | 每组commit；关闭MCAP后独立解码回读，再生成manifest与READY |

禁止固定平移时间戳、最近邻组包、插值历史状态、用历史矩阵覆盖错误原生矩阵后自证通过。静止同字节的新事件合法；新鲜度必须来自事件证据。

所有场景和传感器临时改动写自有匿名Session层，记录before/after并恢复。规定运动模型仍不声明接触动力学真实。正式采集不降低分辨率、不改JPEG、不删状态话题、不擅改噪声或扫描模型。

本地新增实现仅位于本项目。执行远端操作沿用cloud-instance-ops及已有身份、指纹、凭据引用；只管理本任务进程。初期使用现有SDK和依赖。版本对照在形成可复现SDK问题后另列具体来源、版本、落点与验证范围，遵循已有外部下载规则。

## 3 执行阶段和依赖

| 阶段 | 对应原任务 | 交付内容 | 进入下一阶段的门槛 |
|---|---|---|---|
| C0 冻结基线 | M0 | 实际版本、配置、源码和资产证据及资源预算 | 目标正确、旧记录可追溯、预算明确 |
| C1 补齐观测 | M0 | 状态阶段追踪、原生GMO事件和CPU所有权证据 | 能区分时间映射、状态同步、元数据和实际几何 |
| C2 定位机制 | M0 | 最小用例、单变量对照和修复路线判定 | 形成有证据的原因分支及可执行修复 |
| C3 单组连续闭环 | M0至M2 | 修复适配、连续正式MCAP、独立回读 | 单组在途下全部连续正确性用例通过 |
| C4 有界流水线 | M2与M4 | 多ticket、分阶段credit、异步worker及故障验证 | 并发不破坏同步、完整性或资源上限 |
| C5 控制和生命周期 | M3与M4 | 原生输入、Reset、安装revision、策略切段 | 焦点、跨epoch、20轮及故障测试通过 |
| C6 质量性能长期验收 | M5 | 六轮对照、独立质量、30分钟全组合长测 | 七项项目验收各有实际结论 |

在C0至C2期间，允许输出明确标记为诊断的原始载荷和追踪，不生成正式数据READY。C3失败时不进入C4优化。C2若定位到当前SDK不可修复的问题，交付可复现证据及可行后备结果，continuous_ok保持false。

## 4 C0 冻结运行条件

保存当前执行源码和五种配置的逐文件SHA、实际扩展和GPU版本、scene18及依赖清单。引用已有失败探测和屏障数据，不修改已发布记录。为新试验使用独立运行ID和目录，例如 `reports/continuous_recovery/<run_id>/`。

启动时读取有效设置，而不只保存请求值，至少包括物理及loop dt、Timeline timeCodes、Fabric默认周期、MultiTick、perSensorTickTlas、Motion BVH、asyncRendering、Hydra waitIdle和渲染完成检查顺序。接口不存在则记录unavailable及实际替代来源。

建立 `resource_budget.json`，分别定义录制缓冲、诊断日志、Kit/worker RAM和VRAM的预算及测量方式。初始录制缓冲仍为512MiB；整进程预算根据实际可用资源和稳态预热确定，在验收前锁定。Credit不是整个进程RSS，二者分别报告。

C0只冻结和读取运行条件，不把切换应用经验、重建资源或启动引擎描述为只读操作。

## 5 C1 补齐状态和原生事件观测

### 5.1 物理状态与渲染状态分别采集

新增 `state_trace.py`，由唯一EngineOwner在已验证的事件阶段采集：

| 状态来源 | 应记录的内容 | 用途 |
|---|---|---|
| PhysX实际状态 | Root、关节、可取得的实际link pose及物理步时间 | 运动真值 |
| USD组合变换 | 传感器及相关父链世界矩阵 | 检查场景传播及安装关系 |
| Fabric当前状态 | 实际支持接口返回的传感器/父链变换及时间 | 检查USD至Fabric同步 |
| 渲染历史状态 | 可取得的历史样本引用、时间及变换 | 判断Hydra历史采样 |

记录阶段名、接口名、订阅排序域、physical_step、simulation_time_ns、monotonic_ns和scene_generation。不同事件系统的order数值不直接比较。没有公开历史读取接口时保留该缺口，并用零延迟对照和独立几何约束定位，不构造假Fabric历史。

StateLedger继续保存不可变actual状态。调试状态放在独立追踪中，不能将当前Fabric矩阵替换物理真值以消除差异。读回函数的状态写入副作用单独列出；必要时分离参考帧更新和纯数值读取，使追踪不改变被观察阶段。

### 5.2 在完成回调内保存原生事件

新增 `native_event.py` 和 `native_adapter.py`，按已安装SDK的结构版本解析GMO或等价原生输出。保存以下字段及实际来源：

- sensor_id、recording、epoch、原生引用的作用域和分子/分母。
- 原生frameId和timestampNs，以及已验证的时钟域与映射方法；无接口时保留null和原因。
- frameStart/frameEnd的时间、位置、四元数、modelToAppTransform。
- frameOfReference、坐标类型、motionCompensationState、实际Instant和积累设置。
- 逐点timeOffsetNs的实际存在性、数量、最小/最大值及自有字节摘要。
- 提取器transform、XYZ/RGB自有数据摘要、生产数组布局、回调及复制完成时间。
- 原生字段、提取器输出和ReferenceTime属于同一载荷事件的关联证据。

解析前校验结构版本、尺寸、点数、布局和接口支持。原生指针只在SDK允许的有效窗口内使用，复制后的证据才进入CPU队列。逐点offset完整副本仅用于有界诊断；正式主输出仍为002规定的XYZ。

确认Instant输出是否具有满足契约的单时刻语义。frameStart/frameEnd和逐点offset不符合单时刻要求时，先确定其真实含义；不得忽略时间区间或直接套用一个矩阵。若只能支持另一种扫描/补偿模型，则按新数据契约另行设计，本路线保持不合格。

### 5.3 证据格式和工具

新增诊断信封schema1：`phase_states.jsonl`、`native_events.jsonl`、`geometry_observations.jsonl`、`mechanism_report.json`，并记录适配器、解析器、特征提取器源码SHA。时间和大整数按002规则存十进制字符串，矩阵明确行向量约定及单位。

新增 `tools/probe_native_events.py` 与离线 `tools/analyze_native_events.py`。每个诊断用例最多40个有效目标，墙钟上限默认120秒，追踪预算默认128MiB/用例。格式、容量或时间不足即明确结束为inconclusive/failed；必需证据不静默丢弃。关闭高频追踪后再进行普通性能测量。

## 6 C2 定位实际射线和元数据问题

### 6.1 最小用例及单变量对照

先测单雷达与已知静态几何。初始轨迹为静止、纯平移、纯转动、平移加转动，每类至少40个有效事件、三次独立初始化。加入方向反转、启停和非匀速片段，避免匀速轨迹掩盖错帧。

按出现异常的最小层级逐级扩展：纯USD运动传感器、单刚体固定安装、当前关节机器人、1相机加1雷达、全部传感器。每级保留相同原生参数；不执行所有设置的无依据笛卡尔组合。

| 对照变量 | 目的 | 保持条件 |
|---|---|---|
| 当前完整GUI与已安装零延迟参考配置 | 判断异常是否依赖帧间渲染重叠 | 相同dt、tick、模型、几何及轨迹 |
| 规定姿态写入和同步阶段 | 判断历史样本提交顺序 | 每物理步只积分一次，读回实际状态 |
| 原生GMO位姿与提取器transform | 判断提取/元数据问题 | 同一原生完成事件及自有副本 |
| 有依据的物理dt或tick初始相位诊断对照 | 判断边界索引或舍入问题 | 不改正式默认60/10Hz，不伪造时间 |
| 初始化前后历史配置 | 判断设置生效时机 | 需要新历史时重新初始化自有资源 |

实际读取零延迟配置的有效值，记录 `app.hydraEngine.waitIdle` 和完成检查顺序。全局waitIdle先作为诊断变量；若解决问题，再寻找准确的原生完成边界。Motion BVH关闭、MultiTick关闭等仅作为有原因的诊断，不直接升级为主路线成功。

### 6.2 独立几何检验

在自有匿名层放置至少三组独立法向的已知平面和非对称角点，令平移与旋转可观测。平面位置、法向、角点、材质、使用传感器及噪声覆盖全部进入诊断清单。

几何工具直接解码自有RGB/XYZ，用actual状态和真实前一物理步状态分别计算误差；后一计算只用于检验偏移识别能力，不能用于正式纠正。特征选择采用预先固定的颜色、连通区域和形状规则，歧义或缺失明确拒绝，不按最近预期位置挑选结果。

理想几何阈值仍为重投影P95不超过1px、无噪声点到面P95不超过5mm。轨迹须使一物理步偏移产生超过阈值的可观测差异。报告有效及拒绝样本数量、覆盖范围；传感器模型与坐标转换经过非对称算例校验。正式scene18保留原噪声，理想诊断不代替正式质量对照。

### 6.3 按证据选择修复路线

| 证据结果 | 实施路线 | 必须补齐的验证 |
|---|---|---|
| PhysX正确，USD/Fabric传播或历史采样落后 | R1 统一规定运动写入、原生同步与历史提交阶段 | 每步actual、渲染位姿和几何均对应同源时间 |
| 原生GMO位姿正确，提取器transform错误，XYZ几何正确 | R2 采用经验证的原生GMO适配路径 | 原生位姿的语义、坐标转换、源事件及XYZ绑定 |
| 错误依赖帧间重叠或不一致的完成关系 | R3 修复事件依赖和原生完成边界，验证有限在途 | 暂停排空、重负载、缓冲寿命和全部传感器 |
| 仅关节安装层级复现，独立传感器rig正确 | R4 先修复父链同步；必要时验证由actual驱动的渲染rig | 同GUI、完整参数/安装映射、遮挡几何与版本清单 |
| 最小原生场景仍复现且无可用修复入口 | R5 收敛SDK复现材料，开展有范围的版本/修复对照 | 新构建重新通过完整门槛，旧结果不可继承 |

R4的渲染rig不是第二个Isaac重放场景。只有actual至rig映射、当前场景几何、原生事件和标定全部验证后才可正式采用，资产/安装变更必须登记。R2不能用StateLedger矩阵替代错误原生元数据来制造通过。

每个试验写明候选原因、单一改动、预计能区分的结果及实际结论。无新增证据的重复设置试验不继续扩展。不能定位时保留unknown及所缺接口，不将猜测写成SDK根因。

## 7 C3 单组连续闭环

固定C2验证过的适配器和阶段配置，先保持一组在途。合并诊断工具和正式 `capabilities.probe` 的核心检查，避免两个入口对同一能力给出不同结论。

连续能力门槛新增事件字段绑定、坐标系语义、GMO/提取器位姿来源和几何验证引用；已有时间、所有权、共同相位、运动与暂停检查继续保留。当前完整SDK版本及有效配置作为capability适用范围。

| 连续正式用例 | 最低数量 | 必须验证 |
|---|---:|---|
| 相机静止与运动 | 各200组 | 实际运动声明、源事件、PNG、TF、首尾完整 |
| 单LiDAR运动 | 200组 | XYZ、原生位姿、单时刻语义和局部坐标 |
| 1相机加1LiDAR | 200组 | 共同时间、原生事件新鲜性、全路到齐 |
| 全4相机加13LiDAR | 100组 | 所有模型/安装类型及完整状态话题 |
| 非匀速与暂停恢复诊断 | 每模式至少40事件 | 当前与旧步状态可区分，恢复首帧正确 |

单传感器还须覆盖scene18不同LiDAR模型及安装类型，不能只从MyAiry前雷达推导其余路线。每份正式MCAP由独立ROS读取器重新解码和计算hash、时间、位姿、TF及计数；连续数据明确标记backend=continuous。

默认组deadline保持5秒。全组合负载用例需要15秒等配置时显式记录，deadline只作为故障界限，不作为速度指标。每次正式录制仍重新验证所选集合；失败保持unsupported。后端在首组前锁定，运行中失败不得静默切换。

新增原生事件证据按版本化扩展字段/旁路清单保存，进入commit或manifest哈希范围。保持现有正式消息语义；确需破坏性变更时为该结构单独升版并同时更新生产端、独立读取器及示例。旧schema读取器继续验证旧数据，已发布READY不改写。

## 8 C4 有界流水线改造

### 8.1 多目标调度和状态生命周期

新增 `sampling_scheduler.py`，唯一分配目标网格、ticket和暂停边界。将Recording中的单一complete_group及当前ticket假设改为有界的按ticket标识查询；backend的permit只接受已预留的目标集合。故障注入工具也按实际目标选择，不再默认读取第一个ticket。

目标生命周期为 reserved、armed、assembling、validated、transferred、written、completed，异常进入failed/discarded。状态发布后不可修改；目标引用的历史在其必需证据转为独立CPU值之前不能淘汰。

从窗口1开始验证，满足事件提前量和容量条件后测窗口2、再测3。capabilities分别记录观测提前量、SDK契约可保证的范围、暂停生效期间的到达余量和本配置已验证窗口。有限试验最大值不冒充通用SDK上界；没有可靠控制边界时effective窗口保持1。

### 8.2 分离raw槽位和写盘credit

将当前BufferPool拆为RawSlotPool和EncodedCreditLedger，可保持同一文件内实现。raw槽位具有独立generation；编码/持久化credit以完整group身份及预留token跟踪。

- release ACK仅允许释放该group不再被worker引用的raw槽位。
- written ACK仅释放该group的编码/持久化credit，不以当前raw槽位generation作为唯一判据。
- 旧group的raw槽位被复用后，其合法written仍可匹配原credit；篡改身份、错误generation、重复ACK和已关闭epoch均明确拒绝或按预先定义的幂等规则记账。
- ticket保留证据与raw数组引用分别管理；完成mmap转移且不再使用原数组后释放源数组，避免等待written期间继续占用旧raw。

采样前预留raw、编码最坏容量、到达安全余量和必要元数据容量。保守容量不足就限制窗口，不仅限制queue长度。记录credit占用、实际raw/mmap/encoded字节、进程RSS/VRAM、峰值及阶段计数。512MiB不能按当前保守模型直接支持3组；容量变化必须显式配置和复验。

内部IPC升级为协商后的schema2，包含ticket身份、raw slot generation、encoded reservation token和提交顺序。协议不匹配在worker ready前失败。原schema1诊断/正式记录保持可读；新版本不得把旧ACK套入新槽位生命周期。

### 8.3 worker和写入顺序

保持一个CPU进程，在有界队列中执行PNG/CDR准备；MCAP仍由单一写入所有者提交。编码完成可以乱序，提交使用有界重排表按正式输出顺序写入。每组普通消息后写commit，不能因完成顺序变化跳过未处理目标。

ACK产生时机必须对应实际引用生命周期：后台仍使用mmap view时不得release；written不代表fsync、段关闭或READY。关闭段先停止接受对应的新组，再完成已接收组并关闭writer，最后独立验证。

strict_complete高水位在安全边界阻止未预留目标，已有在途继续完成；低水位后继续原epoch和下一未提交目标。Writer回调只做必要CPU物化和非阻塞投递，不等待PNG、MCAP、socket或队列空位。

### 8.4 并发回归门槛

验证正确release后复用raw而旧group尚未written、合法旧group written、错误旧release、错误written token、乱序/重复回调、缺路、慢编码、慢写盘、worker退出、ENOSPC、历史容量耗尽、点数超槽和在途暂停。每类检查真实原生数据链路与独立回读；注入行为明确标记。

每次扩大窗口后重做所受影响的全组合同步与完整性用例。失败无READY，原请求数不改写。测试能证明并发正确后才移除逐组等待written的调度瓶颈。

## 9 C5 控制策略和生命周期

Reset、安装或标定修改由owner串行处理：停止预留新目标，清空按键，收齐并排空已承诺目标，关闭旧段，执行修改，建立新epoch或revision，重建失效句柄并验证必要预热，再安排共同新tick。暂停恢复不发生时间/引用断裂时保持epoch；发生断裂则按新epoch处理。

Root、关节、sensor集合及calibration snapshot不在组装中的ticket之间修改。控制命令带revision并在唯一物理阶段应用，记录accepted-to-applied。UI文字输入、失焦、关闭控制、Pause、Stop和Reset都清空键状态。

实现strict_latest整组丢弃及gap账本。预留失败在目标层登记；部分到达的组丢弃后，其迟到路不能挂到下一目标。target_index和target_step保留缺口；正式输出序号与计划索引的关系明确保存，worker及验证器不能继续用已写组数猜测目标。若现有Ticket/日志字段不足以表达该映射，则单独定义并升版，不能通过重编号隐藏丢组。

strict_latest报告completeness_ok=false；保持同步正确的带gap数据按002的completed_with_gaps规则独立发布，不计入strict_complete完整采样验收。Stop保持原requested和cut-off，不把前缀会话改为完成。

完成原生焦点、参数和轨迹专项测试，覆盖录制中修改、暂停恢复、Reset及安装切段；同一GUI至少20轮、每轮至少10组。核对每轮自有订阅、产品、Writer、匿名层、worker、IPC线程和槽位；SDK缓存与自有资源分开记录。未解释的持续增长保持lifecycle未通过。

## 10 C6 质量 性能和长期验收

实现实际基线驱动及只读 `baseline_adapter.py`，调用原v06已有入口并解码其原输出；不改v06源码，不将新实现当基线，不捏造基线原生事件或新格式READY。对同条件的轨迹、实际捕获状态、传感器、标定、资产、渲染和PNG参数提供证据；旧入口无法满足比较条件时，先解决基线条件，性能结论保持未验收。

基线为原v06 persistent_gated加keepalive、16相机预热子帧加2正式子帧。候选为通过连续同步验收的实现。六轮按baseline/candidate交错，各预热20组后测至少200组；同单卡、同GUI/预览负载，普通速度测试关闭高频诊断追踪及profiler。

独立质量覆盖铲齿、细杆、鱼眼边缘、遮挡显露、快速转动和恢复首帧；固定抽样规则及特征提取器版本。理想几何通过不自动代表正式scene18质量等同。同步、完整性和质量通过后，才将相同统计口径的速度提升解释为合格数据产能。

报告冷启动、采集、排空、回读及全操作墙钟；按原002分别计算稳态written组/墙钟和readback组/全操作时间，并给每轮值及规定分位数。目标为稳态有效组吞吐至少2倍；引擎控制延迟P95不超过50ms、P99不超过200ms，最大值单列。全组合RTF达到1单独报告。

最后运行至少30分钟墙钟的全组合strict_complete，全部关闭MCAP并回读；记录RAM、VRAM、FD、线程、产品/订阅、credit及资源增长趋势。预算在测试前锁定，测试中超限明确失败，不通过增大预算掩盖泄漏。有限长测只证明指定版本、负载及时间范围内的有界行为。

## 11 文件改动与交付任务

| 顺序 | 文件或模块 | 主要改动 |
|---|---|---|
| T0 | 现有remote_ops和manifest工具 | 冻结C0、审计自有部署与恢复位置 |
| T1 | 新state_trace、native_event、native_adapter | 原生字段、时钟域、阶段和所有权证据 |
| T2 | 新probe_native_events、analyze_native_events；geometry_diagnostics | 最小用例、单变量试验及独立几何 |
| T3 | engine_owner、sensor_backend、capabilities | 只实施C2证实的修复；统一能力门槛 |
| T4 | validation、messages及实际MCAP回读工具 | 新证据绑定、坐标/时间复算及版本兼容 |
| T5 | 新sampling_scheduler；recording、time_joiner、state_ledger | 多ticket、安全背压、完整状态引用 |
| T6 | buffer_pool、record_pipeline、record_worker | 分阶段credit、IPC2、编码/提交次序 |
| T7 | motion_controller、ui、recording | Reset、revision、焦点、strict_latest与gap |
| T8 | 新baseline_adapter；compare_performance、run_acceptance | 实际六轮基线、质量、长测及七项验收 |

测试围绕时间域、原生事件身份、状态真值、raw复用/旧written、并发重排、epoch及缺口等关键契约编写；真实GPU完成、缓冲寿命、传感器tick和焦点使用真实SDK验证。每项修复先验证直接影响范围，窗口、版本、安装或策略变化后再扩大验收。

交付包括新增源码、五配置及诊断配置、实际capabilities、完整连续MCAP与READY、规则抽样、各阶段机制报告、原始错误、配置/资产/源码SHA、性能和资源报告、运行/停止/恢复说明。最终七项结果逐一引用实际证据；不从屏障READY继承continuous、质量、性能或生命周期通过。

## 12 执行起步与参考

第一批执行T0至T2：冻结环境，接入原生事件与状态追踪，完成单雷达最小诊断及修复路线判定。先交付C2机制报告，再按选定路线执行T3和C3。当前同步阈值保持不变。

项目资料：

- [002设计与验收契约](002_single0601ContinuousRt_快速同步采集实现方案.md)
- [003执行任务书](003_single0601ContinuousRt_Agent执行任务书.md)
- [2026年10月13日执行报告](../Execution/20261013_execution.md)
- [原始矩阵复核](../../reports/continuous_mechanism_analysis.json)
- [已安装SDK只读检查](../../reports/mechanism_installed_sources.json)

官方机制参考用于设计试验，实际rc7接口和行为由capabilities确认：

- [Isaac Sim 6.0.1 Multi Tick Rendering](https://docs.isaacsim.omniverse.nvidia.com/6.0.1/sensors/isaacsim_sensors_multitick_rendering.html)：物理时间、Fabric、传感器tick和渲染顺序。
- [Isaac Sim 6.0.1 RTX Sensor Annotators](https://docs.isaacsim.omniverse.nvidia.com/6.0.1/sensors/isaacsim_sensors_rtx_annotators.html)：GMO点云提取及sensor-to-world输出。
- [Isaac Sim 6.0 GenericModelOutput](https://docs.isaacsim.omniverse.nvidia.com/6.0.0/py/docs/source/generic_model_output/generic_model_output.html)：frameId、起止位姿、坐标系和逐点时间结构；与已安装头文件交叉确认。
