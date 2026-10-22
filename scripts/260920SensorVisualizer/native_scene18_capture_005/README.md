# Scene18 原生冻结 RT2：300 组运动采集

本子项目复制并保留 `capture_comparison_004/engines/frozen` 的已验证原生链路，在本目录独立适配轨迹；不修改旧代码或场景文件。原始源文件及哈希保存在 `baseline_sources/` 和 `source_provenance.json`。

## 本轮参数

- 场景：`combine_scene_18_terrain_fisheye_mesh.usda`。场景现有灯光/天空和传感器安装位姿保持原样。
- 300 个有效组，逻辑时间 0～29.9 s，步长 0.1 s。
- 世界 X 前进 0.1 m/s，累计 2.99 m；世界 Y/Z 保持初始值。
- 根 Yaw/Pitch/Roll 相对初始姿态分别在 ±15° 匀速往复，速度 3°/s，同相，周期 20 s，初始 0° 向正方向。
- 根旋转为列向量 `R_world = R_initial @ Rz(delta_yaw) @ Ry(delta_pitch) @ Rx(delta_roll)`；记录输入四元数 xyzw。
- 大臂/小臂/铲斗同样在 ±15°、3°/s 往复；cab–track 保持初始角度。
- 13 路 Instant LiDAR、4 路鱼眼。RT2、DLSS Quality、AA=3、资源常驻、每组 16 预热＋2 正式子帧。
- 规定运动：每组先推进 6×1/60 s，再关闭自动推进，设置 Articulation 根/关节姿态并清零关节、整机线速度和角速度，调用原生运动学更新与 PhysX→USD 同步；最后以 `delta_time=0` 渲染。规划速度保存在轨迹定义中，不能把冻结时的 JointState.velocity 当成规划导数。
- 原生 ROS Helper 发布 Image、PointCloud2、CameraInfo、TF、JointState、Clock，标准 rosbag2 MCAP 录制。原生初始化、预热、尾部消息也保留，`groups.jsonl` 与严格数据哈希校验确定有效组。
- ROS 根参考 frame 沿用原生基线名称 `swing_coordinate`，其几何语义是挖掘机根参考，不是随 cab 回转的坐标系。相机为 ROS optical frame。

## 顺序

准备 3 组极值小样本（完整轨迹第 0、50、150 个状态）→ 原生录包及逐组验证 → 通过后再运行独立的 300 组正式任务。小样本逻辑时间跨越 0/5/15 s，但实际引擎相邻冻结时间间隔仍为 0.1 s，仅用于极值位姿验证。正式任务的逻辑与原生时间步长均为 0.1 s，初始化时间偏移如实记录。

每组检查：目标根位姿/关节角、冻结前后时间和姿态、相机/雷达实际渲染变换、MCAP 中同时间戳的 RGB/XYZ 哈希、TF 和关节数据。组数必须达到要求。原生额外消息不篡改时间戳，也不计作额外有效组。

运行 `run.py --config <本轮job.json> --output <不存在的输出目录>`。输入由 `prepare.py` 在现有 USD Python 环境生成；脚本不会安装依赖。运行前要求没有现存 Kit 进程，剩余磁盘至少 40 GiB。仅创建本项目目录和独立输出，所有 USD 改动进入匿名 Session 层。

`resources.jsonl` 记录整卡 GPU busy、显存、功率、频率及 Kit/录包进程与线程 CPU 计数；不代表 CUDA/RT/Tensor Core 的单独利用率。原始 warnings 与分阶段耗时保留。

## 精确 300 组交付包

`tools/export_groups.py` 使用 ROS 官方 `rosbag2_py.SequentialReader/SequentialWriter`，根据冻结时刻的图像/点云数据哈希，以及 TF、关节角逐组匹配，保留最后一条符合要求的原生消息。既不重新序列化传感器数据，也不改 header 或录包时间戳。输入原始 MCAP 保留。

每组 25 条消息：13 PointCloud2 + 4 Image + 4 CameraInfo + 2 TFMessage（根、传感器）+ JointState + Clock，共 24 个话题。正式 300 组应为 7500 条消息、3900 帧点云、1200 张图像。原生时间戳保留初始化偏移，具体见 `groups.jsonl`。

`finish_delivery.py` 等待本任务的原始录包及严格校验通过，才生成 `delivery_300/bag/`，再对交付包重做逐组校验和文件哈希。`selection_manifest.json` 记录来源消息序号、原始 CDR 哈希和时间戳，使删去预热/重复消息的过程可追溯。

## 本次运动适配排障

最初采用“设置姿态→推进物理步→冻结”，在第二个极值姿态检测到根位置偏差约 0.5 m、关节约 0.2844 rad，因此停止，未进行正式采集。增加速度清零/运动学同步后该顺序仍失败。改为“推进→冻结→设置姿态→原生同步→渲染”后，0°/+15°/−15° 三个极值全部通过图像、点云、TF、关节与冻结校验。

失败样本独立保留在 `capture_20261012_110148`、`capture_20261012_110922`，不作为交付数据。适配前代码在 `backups/pre_pose_sync`、`backups/pre_freeze_apply`。旧项目与磁盘 USD 未修改。原生 PoseTree 类型警告保留在日志中，是否影响数据以数值 TF 及渲染矩阵校验为依据，未通过屏蔽日志来回避检查。

## 报告与验收证据

正式报告、精选验收摘要和必要配图见 [报告索引](docs/reports/README.md)。原始采集、逐帧状态和性能追踪保留在原运行目录，由仓库忽略规则排除。
