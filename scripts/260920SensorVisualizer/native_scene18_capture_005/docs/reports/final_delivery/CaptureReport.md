# Scene18 原生冻结 RT2：300 组采集交付记录

状态：正式采集与交付包校验全部通过。300 组，13 路点云（3900 帧）、4 路鱼眼（1200 张），24 个话题、7500 条消息。

## 参数

- 场景：`/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_18_terrain_fisheye_mesh.usda`。
- 整机 Yaw/Pitch/Roll：相对场景初始姿态各 ±15°，3°/s 三角波，同相、20 s 周期，0° 起步向正方向。
- 整机世界 X：0.1 m/s；世界 Y/Z 固定。300 个样本按 0.1 s 间隔，逻辑时间 0～29.9 s，累计 +2.99 m。
- 大臂、小臂、铲斗：沿用 ±15°、3°/s；cab–track 保持初始角度。
- 根旋转：`R_world = R_initial @ Rz(delta_yaw) @ Ry(delta_pitch) @ Rx(delta_roll)`。
- 原生冻结 RT2：RealTimePathTracing、DLSS Quality、AA=3，每组 16 预热 + 2 正式子帧，保持原生 Helper 接线，产品常驻。
- 每组先推进 0.1 s → 冻结 → 设置根与关节姿态、清零速度、原生运动学/PhysX→USD 同步 → 渲染 → 读取并校验。
- 规定姿态采集，不自动贴地；冻结状态的速度字段不能当成轨迹速度。既有资产和场景文件未改动。

## 交付位置和组织

`/root/gpufree-data/semantic/output/native_scene18_capture_005/capture_20261012_111643/delivery_300`

- `bag/`：标准 ROS 2 MCAP 与 metadata.yaml，可用于 ros2 bag play/info。
- `groups.jsonl`：300 组的逻辑时刻、原生时间戳、目标位姿、实测位姿、图像与点云哈希。
- `input_trajectory.jsonl`：输入轨迹；`spec.json`：本次运行配置；`sensor_manifest.json`：传感器话题、frame 与 Prim 对应。
- `selection_manifest.json`：每条交付消息的原始录包序号、CDR 哈希及时间戳。
- `validation.json`、`group_validation.json`：结构、数据、时间戳、TF 和姿态校验。
- `files_sha256.json`：MCAP 及 metadata 的大小与哈希；`*_first.png`、`*_measurement_last.png`：从包内解出的四相机首尾帧。

每组保留 13 PointCloud2、4 Image、4 CameraInfo、2 TFMessage、1 JointState、1 Clock。TF 包括 `world → swing_coordinate` 和该根参考下的 17 个传感器坐标系。`swing_coordinate` 沿用原生基线名称，含义是挖掘机根参考。

逻辑时间：[0.0, 29.900000000000002] s；原生消息时间：[0.36666666666666664, 30.266666666666666] s。保留初始化偏移 0.366666667 s，未重写 header、CDR 或消息录制时间。有效样本 10 Hz 指仿真时间频率，不是真实采集速度。

原始录包保留于 `/root/gpufree-data/semantic/output/native_scene18_capture_005/capture_20261012_111643/production/capture/bag/`。交付包只选择匹配冻结输出哈希和当前 TF/关节的消息，剔除原生预热和重复发布。原始消息字节不变；交付包另行完整复验。

## 结果与限制

- 平均每组 3.009 s，中位数 2.988 s；采集进程含初始化/收尾 944.46 s，不包含之后导出及校验耗时。
- 交付 MCAP 8.603 GiB；原始 MCAP 17.193 GiB。
- 根矩阵误差最大 1.16e-07；关节误差最大 1.3e-08 rad。
- 冻结时位姿变化最大 0；时间变化最大 0 s。
- 相机实际渲染矩阵误差最大 2.66e-15；雷达 5.87e-07。
- 场景与 18 个已加载 USD 依赖容器哈希未变。此范围不等于对所有纹理和系统文件进行全面审计。
- 正式引擎日志 Error 0 行、Warning 158922 行。大量是原生 PoseTree 对传感器/辅助 Xform 的类型提示；本轮数值 TF、渲染矩阵及数据一致性验证通过，未据此声称警告本身已修复。
- 一致性校验验证时间、坐标和消息对应关系，不替代物理传感器精度/真实场景标定评估。RT2 子帧数也不是离线路径追踪的精确射线 SPP。

原始阶段日志及 `resources.jsonl` 位于 `/root/gpufree-data/semantic/output/native_scene18_capture_005/capture_20261012_111643/production/capture`。资源记录为整卡 GPU busy、显存、功率、时钟和进程/线程 CPU 计数，不是 CUDA/RT/Tensor Core 各自利用率。
