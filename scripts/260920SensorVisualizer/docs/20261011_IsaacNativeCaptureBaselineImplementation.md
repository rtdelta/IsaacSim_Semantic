# Isaac Sim 原生采集基线完整实现方案

日期：2026-10-11。保存用户批准的完整方案；实施记录另存于独立项目，方案本身不代表测试已通过。

你希望建立一条尽量由 Isaac Sim 自己完成更新、传感器生成和发布，再交给标准工具保存的独立基线，用实际结果判断现有脚本链路增加了多少成本。

参考 `20261011_IsaacNativeCaptureBaselinePlan.md`，按下面的目标执行。

## 一、核心目标

这次实验主要回答三个问题：

1. 脱离自定义调度后，重复 NVRTC 编译、CUDA 模块加载／卸载是否还存在？
2. 原生链路的帧率、主线程耗时，以及 CPU／GPU 负载是否更连续？
3. 保存的数据是否完整、质量是否相当，速度差异来自哪里？

不预设原生链路一定更快。尤其要防止“少渲染了、少采数据了”造成表面上的提升。

## 二、采用的最小链路

```text
同一个 USDA 场景
    ↓
Isaac 原生 Timeline／引擎逐帧更新
    ↓
原生 Render Product 和传感器处理
    ↓
官方 ROS 2 Bridge 发布
    ↓
DDS 传输
    ↓
标准 rosbag2 录制
    ↓
MCAP + metadata.yaml
```

项目脚本主要负责一次性配置和启动／结束。逐帧执行交给原生引擎与官方发布管线，不经过现有 CaptureTicket、逐组启停、共享内存打包和自定义录制进程。

这里仍会使用 Isaac 内部的 RTX、传感器插件及 SDG 后处理网络。官方 Camera Helper 会自动建立读取、处理和发布数据的管线；我们要验证的是这条官方组织方式的成本。

## 三、使用哪些原生接口

| 功能 | 优先采用的接口／节点 | 作用 |
|---|---|---|
| 场景与播放 | USD 加载接口、Timeline、原生引擎更新 | 加载场景并持续逐帧运行 |
| 渲染产品 | Isaac Create Render Product | 为现有传感器建立持续存在的渲染输出 |
| 点云发布 | ROS 2 RTX Lidar Helper，或官方 RtxLidarROS2PublishPointCloud Writer | 原生生成并发布 PointCloud2 |
| 图像与标定 | ROS 2 Camera Helper、Camera Info Helper | 发布图像和相机参数 |
| 空间关系 | Isaac Compute Transform Tree、ROS 2 Publish Transform Tree | 从场景计算并发布 TF |
| 仿真时钟 | Isaac Read Simulation Time、ROS 2 Publish Clock | 发布真实仿真时间 |
| 数据保存 | ros2 bag record -s mcap | 标准录制、索引及文件收尾 |

执行时核对实例实际安装版本的节点名称和输入定义。

## 四、实施顺序

1. **锁定同一份输入。**当前调查基线使用 `/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_16_terrain_fisheye.usda`。保留同样的 13 路 LiDAR、4 路 1920×1080 鱼眼、安装位姿、扫描参数、背景及渲染设置。独立创建测试配置，旧代码与 USD 保留。
2. **先运行固定姿态的原生采集。**排除运动控制的干扰。传感器和发布管线一次建立，采集期间持续运行，不逐组关闭、重开。
3. **进行三个分层测试。**A：原生渲染和传感器数据生成；B：A 加官方 ROS 发布及明确的订阅条件；C：B 加标准 MCAP 录制。分别定位引擎／传感器处理、发布／传输及录制／压缩／写盘的成本。A 保留必要的传感器后处理，避免通过取消点云生成减少工作量。分别记录初始化、首帧、稳态及结束阶段。
4. **再测试运动场景。**使用最小的官方关节／整机姿态接口输入同一条参考轨迹。运动输入单独计时，不带入原来的控制和采集框架。
5. **采集结束后检查数据。**检查话题、消息数量、时间跨度、点数字段、图像、标定、TF，以及缺帧、重复时间戳和旧位姿。检查在采集之外进行，不阻塞逐帧运行。

## 五、需要明确的两个对照边界

**逐帧运行不保证每帧每个传感器都有新数据。**当前官方 6.0 文档指出，传感器发布节拍涉及 `omni:sensor:tickRate`；核对实际扫描模式、完整扫描设置及实例版本，不沿用未经核对的原脚本频率假设。

**原生连续采集与原来的冻结姿态、16+2 子帧工作量不同。**因此分别报告：

- 原生连续基线：观察原生链路自然运行时的速度与负载。
- 等价条件对照：验证能否仅用官方接口保持原来的子帧工作量和采样条件；不能做到的部分明确列出。

原生图像编码、鱼眼 CameraInfo、自定义组索引和时间同步可能与原包不同。核对这些差异后才能判断是否生成了内容可比的数据包。

## 六、产出及约束

独立最小脚本、原生 MCAP、配置差异表，以及 CPU／GPU 原生时间线对照报告。优先使用已有依赖，缺失工具先列出并征得同意；不下载、安装或更新任何外部依赖。保持原代码和原 USD 不变。

## 官方参考

- [LiDAR 官方示例](https://docs.isaacsim.omniverse.nvidia.com/6.0.0/ros2_tutorials/tutorial_ros2_rtx_lidar.html)
- [相机官方管线](https://docs.isaacsim.omniverse.nvidia.com/6.0.0/ros2_tutorials/tutorial_ros2_camera.html)
- [TF 官方说明](https://docs.isaacsim.omniverse.nvidia.com/6.0.0/ros2_tutorials/tutorial_ros2_tf.html)
- [Clock 官方说明](https://docs.isaacsim.omniverse.nvidia.com/6.0.0/ros2_tutorials/tutorial_ros2_clock.html)
- [MCAP 标准录制](https://github.com/ros2/rosbag2/blob/rolling/rosbag2_storage_mcap/README.md)
