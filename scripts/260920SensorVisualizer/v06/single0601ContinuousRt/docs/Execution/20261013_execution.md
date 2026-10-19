# 2026-10-13 实现与真实验收报告

**完整主目标尚未完成。已实现并实测可行的 `barrier` 后备路线；连续 RT2 路线在当前真实 SDK 的 LiDAR 位姿探测中失败，禁止发布连续正式数据。** 此结论遵循003第1节允许的“实际探测和失败证据、完成可行后备、明确未完成主目标”。数据READY只表示指定录制的同步、完整性和文件校验通过。

| 项目级验收项 | 结论 | 实际范围与依据 |
|---|---|---|
| continuous_ok | false | 连续 captureOnPlay 原生 LiDAR 渲染矩阵与相同源时间的实际历史状态不符，最大旋转差约0.000872704rad，超过0.0001rad |
| sync_ok | true | 后备路线：相机静止/运动各200组，单雷达200、混合200、全组合100；独立ROS CDR、源时间、TF、PNG、XYZ及状态回读 |
| completeness_ok | true | 上述正式录制请求、调度、验证、写入和独立回读数一致；无gap、无静默丢帧 |
| quality_ok | null | 理想诊断几何通过；scene18运动细节、鱼眼边缘、遮挡、恢复首帧及v06质量对照未完整验收 |
| performance_ok | null | 没有三轮交错、20组预热+200组测量的合格基线/候选对照，不宣称2倍提升 |
| interaction_ok | null | 原生键盘/焦点、正常负载延迟未实测；录制中Reset及安装revision尚未实现 |
| lifecycle_ok | null | 同GUI20轮各10组、单次原生资源/CPU/IPC清理通过；RSS有增长，30分钟全组合资源有界性未验证 |

项目级 `full_delivery=false`。不能用本报告里的READY数量替代七项全部通过。

实际实例为 `isaac-new` 单卡端口30729，主机 `gpufree-container`，GPU NVIDIA L40，UUID `GPU-98e8b2c0-e87d-4770-07ca-72683e12547c`，驱动580.126.09。安装版本为 Isaac Sim `6.0.1-rc.7+release.42383.32955d8d.gl`、Replicator1.13.27、RTX sensor common3.0.0、simulation_manager1.15.6，CPU worker使用已有ROS2 Jazzy。单个真实GUI拥有USD/PhysX/渲染/输入，CPU worker和独立验证器不启动第二个Isaac。

实现位于 `single0601_continuous_rt`，入口 `run_capture.py` / `run_in_isaac.py`。内容包括schema4五种配置、选定传感器发现、物理PRE运动与POST实际读回、不可变状态历史、原生ReferenceTime映射、持久Writer/产品、按源时间组包、预留有界credit、独立PNG/CDR/MCAP worker、release/written/segment_closed分别核验、commit哈希、独立P7回读和READY清单。复用代码及实际原文件SHA列于 `docs/source_transplants.json`。全局渲染设置、自己创建的层和输入订阅在关闭时恢复或释放。

M0连续探测实际尝试了PRE/POST阶段调整、Motion BVH和MultiTick配置、Stage创建前Fabric60Hz等组合。最后一轮得到58条有效receipt、29个共同10Hz tick、每路29个不同运动位姿；时间映射、独立CPU数组寿命、共同相位及暂停恢复通过，LiDAR位姿仍失败。该差异接近3deg/s运动在一个1/60秒物理步内的旋转量，是实测现象，不据此伪造旧帧时间或修改同步阈值。连续路线没有正式commit或READY。

后备路线使用同一套持久产品和Writer，在精确物理目标边界暂停，执行一次manual Writer请求并等待全部原生owned receipt，不逐组16子帧预热或stop/drain。保留60Hz物理、10Hz模拟时间采样、1920×1080 RGB、无损PNG、13路原生Instant LiDAR、10Hz scan及完整状态话题。暂停产品更新的两种优化试验导致空点云/无效原生矩阵，均被M0拒绝，未进入正式采集，最终恢复已验证的持续产品更新方式。

| 真实用例 | 独立回读组数 | 录制ID与结果 |
|---|---:|---|
| M1相机静止，含实际Root不移动断言 | 200 | `recording_0a001d1cba7249ea960c4867f087e002` READY |
| M1相机运动，含实际Root移动断言 | 200 | `recording_6b1b5024ac4942d0a8207ba35b343362` READY |
| M2单雷达运动 | 200 | `recording_81f3a3b91ca54397aab778d20bf4c97f` READY |
| M2一相机+一雷达运动 | 200 | `recording_7c3407bacbb747ddb258794ddb8e8532` READY |
| M2全4相机+13雷达运动 | 100 | `recording_04340e89046a43878e845c5131e4dad0` READY |
| M3同一GUI20次独立录制 | 20×10 | `matrix_20261013_201715`，全部READY；每次原生资源、层/设置、CPU与IPC清理核查通过 |

原先的200组静止记录也经新验证器重新检查，实际Root平移与旋转变化均为0；新增显式Hold和运动声明断言属于加固。后续再录制200+200组，均通过。对“静止是否残留运动”的中途判断已由实际MCAP回读更正。

全组合第一次使用5秒墙钟deadline时，第96目标没有收齐，保留95组前缀和FAILED，没有READY。重试显式配置15秒deadline后100组完整通过；默认配置仍为5秒，源时间2ns、平移1mm、旋转0.0001rad阈值不变。独立回读100组、3102条消息，最大源时间差0ns、平移差2.67612e-6m、旋转差3.96252e-7rad。新验证器再次完整读取该MCAP也通过。

M4对真实原生owned载荷的CPU传输链路进行显式故障注入。2秒延迟、乱序和相同重复各5组全部完整回读并READY；冲突重复返回 `conflicting_duplicate`、旧epoch返回 `epoch_mismatch`、旧release ACK返回 `stale_ack`、旧written ACK返回 `stale_written_ack`；旧帧被丢弃，无法填充新目标，最终 `missing_sensor`。这些负例全部FAILED且无READY，原始请求数保留。另有缺路测试按deadline失败、慢worker每组延迟2秒仍完整通过、写group_commit之前注入ENOSPC导致磁盘失败并保留前缀。它们是明确标记的故障注入，不声称SDK自然发生了同类故障。纯逻辑测试另外覆盖时间/位姿/epoch/ownership/溢出及旧generation等契约。

独立几何诊断仅在本任务匿名层加入已知平面和色标，正式磁盘资产及常规传感器参数不变。原保留15mm rangeAccuracyM的测试平面P95约19.74mm，不能拿它宣布“无噪声平面5mm”失败或通过；原色标提取还混入栏杆、遮挡及阴影问题，原失败记录保留。单独声明无噪声平面诊断将rangeAccuracyM临时设0并记录before/after，保留1mm rangeResolution、Instant和scan参数。改用颜色比例、连通区域、已知投影面积/形状检测，含糊和缺失特征记录为拒绝，几何验收阈值始终不变。

对冻结的24组快速运动MCAP完整独立复核：63个特征重投影P95 **0.768384px**；24组平面点到面P95 **6.79584e-6m**。故意使用真实前一个物理步的状态重新投影，P95 **2.456609px**，正确被诊断识别。新的外部回读报告为 `reports/remote/reports/revalidation_noiseless_fast.json`，既有READY、manifest及原失败报告没有改写。这只证明明确声明的理想几何诊断，不能自动推导scene18整体画质等同基线。

全组合100组实测采集382.379秒、准备121.926秒、排空6.287秒、回读23.817秒，单次完整操作534.409秒；采集吞吐0.2615组/墙钟秒。原performance字段中的0.1871是“回读通过组数/该次全操作时间”，未做M5质量比较，不解释为已验收的可交付数据产能。原生路间到达等待P95约3558.7ms，PNG编码中位约78.7ms，当前主要瓶颈在单卡多产品渲染/到达等待，不能通过删传感器或降图像分辨率隐藏。512MiB配置的保守预留credit峰值为384MiB，一组在途；该值是录制缓冲credit，不是整个Kit/worker进程RSS。

同GUI20轮完成后文件描述符保持396，线程398–399；第一轮结束RSS约7.58GB，第二十轮约9.03GB，峰值约9.64GB。后续已释放额外Python USD引用，但未重做20轮及30分钟长期资源证明，所以项目lifecycle保持未验收。所有本任务测试GUI和CPU检查进程已结束；没有关闭无关进程。

最终逐文件SHA审计：47次有结束状态的录制中，**36份READY、1612组**通过文件完整性检查；失败/停止原始录制没有伪造READY。完整真实10组混合MCAP已经下载到本地 `reports/remote/reports/deliverables/recording_12b92d339a94453a8a7b1bb108335fd0/`，包括根/段READY与完整hash清单，并由新验证器再次独立解码通过。固定规则抽样为首组、floor(N/2)组、末组，原始无损PNG和完整XYZ在 `reports/remote/reports/samples/`，未为速度降采样。

冻结记录、清单、实际错误和M0原始探测证据下载至 `reports/remote/reports/delivery_evidence_20261013_210539/`。41个过大原生参数文件没有重复下载，实际大小、远端位置、SHA及未复制原因列在其 `evidence_manifest.json`，完整原件保留远端。独立验收汇总为 `reports/remote/reports/acceptance_final.json`。

本地12项实际纯逻辑测试全部通过，77个Python文件语法及5个schema4配置校验通过。执行前后原v06文件哈希无增加、删除或改变；磁盘scene18 SHA保持 `e44ff38c21caaaccf20aa44a9b834e33d7109407e737df27198a63ad95e9fb79`。比对证据在 `reports/source_integrity.json`。没有安装新依赖或覆盖001/002/003。SSH/SFTP操作使用已有凭据引用、指纹和实例身份核验，逐次审计保留在本地CloudInstanceOps目录。

尚未完成的工作：连续SDK时间/位姿契约；strict_latest运行及整组丢弃记账；录制中Reset/新epoch、安装和calibration revision切段；真实原生键盘/文本焦点、UI参数/轨迹及控制延迟专项验收；v06同条件六轮基线/候选质量与速度对照；30分钟墙钟全组合长测与长期资源有界证明。比较工具目前检查规范化证据契约并拒绝未合格结果，没有产生实际基线速度。后续应先解决连续位姿接口和M3，再按M5门槛完成比较。

运行、停止、显式后备选择、五配置和回退说明见根目录 `README.md`。远端项目仍位于 `/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt`，数据位于 `/root/gpufree-data/semantic/output/single0601ContinuousRt`。
