# 261013RViz2Viewer：实施方案与边界

## 本轮授权目标

1. 使用自制 single06/v06 链路在 Scene18 重录 300 组，沿用上次整机/关节运动及全部传感器。
2. 创建独立 RViz2 回放工具，源码保存在指定本地目录，并部署到单卡实例。
3. 实现原始录制时间回放与按消息时间归组回放、暂停/整组单步/跳转、逐雷达显示、模型相对点云偏移诊断及时间日志。

## 参数

场景为 `combine_scene_18_terrain_fisheye_mesh.usda`，SHA-256 `e44ff38c21caaaccf20aa44a9b834e33d7109407e737df27198a63ad95e9fb79`。13 路 Instant LiDAR、4 路 1920×1080 鱼眼。10 Hz、300 组，逻辑时间 0～29.9 s。

整机世界 X 0.1 m/s，末组偏移 2.99 m；Yaw/Pitch/Roll 同相 ±15°，3°/s，0° 向正方向起步，20 s 三角波周期；boom/arm/bucket 同参数；cab-track 初始角度保持。旋转 `R_initial @ Rz(yaw) @ Ry(pitch) @ Rx(roll)`。直接复用上次 `input_trajectory.jsonl` 的位置与四元数，不重新构造 Euler 轨迹。

自制链路 `persistent_gated + keepalive`，RT2 `RealTimePathTracing`、DLSS=2、AA=3、帧生成关闭、16 子帧预热 + 2 正式子帧。先推进原生时钟，再冻结并设置目标姿态，再渲染/接受数据/独立 CPU 复制/后台 PNG 编码及单写者 MCAP 保存。保持源码副本、完整源文件哈希、独立输出和既有校验。

## 坐标与数据完整性

从成功冻结采集后的实际 USD 刚体世界矩阵生成逐组部件位姿。mesh 局部点经过原始 mesh→body 变换后烘焙为 STL，包含原始缩放和对齐。回放采用单位缩放，不重复缩放。关节父子锚点直接读取 USD，列向量计算 `T_child=T_parent @ F0 @ Rot(axis,q) @ inverse(F1)`；用实际捕获的五部件矩阵验证运动学。

时间审计同时保留 header、Clock、MCAP 录制时间、逻辑组号和初始化偏移。SQLite 保存源消息 CDR 和两种时间，原始 MCAP 不重写。原始模式依照录制时间发送，根/关节随实际 ROS 话题到达更新；同步模式按消息时间形成完整组，先 TF 后点云。不同话题的 DDS 到达与 RViz 刷新不具备原子性，定格核对与连续播放分别验证。

## 工具与接口

官方已有 `rosbag2_py.SequentialReader/StorageFilter` 读取 MCAP；`rclpy`、`deserialize_message`、ROS 标准消息负责发布和接收；`MarkerArray/MESH_RESOURCE` 显示挖掘机。NumPy 完成刚体变换；标准库 sqlite3 提供可跳转缓存，单后台预读线程缓存未来三组，避免把全部数据放进内存。单调时间绝对截止点控制 10 Hz，避免每组渲染/发送耗时与 sleep 累积漂移。标准库 HTTPServer 提供仅监听 127.0.0.1 的网页，HTML/CSS/JS 无外部依赖。

## 验收

3 组试采集通过后才启动 300 组。检查数量/话题、消息字节、时间、TF、根及关节位置、图像参数和场景哈希。回放验证前进/后退/跳转、±1 组模型偏移、两种时间模式、网页控制、13 话题接收数据哈希。之后用完整 300 组测定 10 Hz 推送间隔，再启动实际 RViz 检查 mesh/点云/坐标轴显示，保留截图、ROS 接收日志、RViz 日志及未验证项。

没有外部下载、安装、升级、桌面/驱动修改或无关进程终止。运行仅创建本项目代码、输出、缓存和自己的诊断进程。
