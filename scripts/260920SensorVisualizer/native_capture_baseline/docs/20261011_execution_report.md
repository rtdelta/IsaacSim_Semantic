# 原生采集基线：实现与实测报告

日期：2026-10-11。日志使用 UTC，换算北京时间加 8 小时。

## 1. 完成了什么

本地与单卡实例部署了独立 `native_capture_baseline` 项目。核心执行不导入 v06、single06_lab 或旧录制 Worker；使用持续存在的原生 Render Product、官方 ROS Helper/Writer、标准 DDS 与 `rosbag2_storage_mcap`。项目自己的逐帧代码只等待引擎更新、可选输入姿态、记录计时，没有读取或打包传感器数组。

实际运行链路：

```text
combine_scene_16_terrain_fisheye.usda
  → Timeline / SimulationManager / Kit update
  → 13 LiDAR + 4 鱼眼 Render Product
  → 官方 SDG / ROS2 Helper / Writer
  → Fast DDS（domain 187，仅本机）
  → ros2 bag record -s mcap --use-sim-time
  → bag/*.mcap + metadata.yaml
  → 采集后的标准 ROS 解码、完整性与性能分析
```

MCAP 录制期间不使用 CaptureTicket、逐组启停、mmap、自定义编码进程或项目自定义 MCAP Writer。

## 2. 输入与环境

- NVIDIA L40 单卡；Isaac 6.0.1 rc7；已有 ROS Jazzy、MCAP 插件和 Nsight Systems。
- 场景 `/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_16_terrain_fisheye.usda`。
- 根 USD SHA256：`ab2a2ef736030adba3420450f916420e705952a04fec163c05b545655fc7f0ae`。
- 13 路 Instant LiDAR，4 路 1920×1080 鱼眼；从 USD 自动发现。
- `RealTimePathTracing`、DLSS quality（2）、AA 3；Motion BVH 关闭；默认 Multi-tick 关闭，匹配先前调查配置。
- 仿真步长 1/60 秒；离线不限速；不用于替代交互面板或测量网页响应。
- 安装位姿、相机标定和扫描参数来自同一场景。LiDAR 原生输出坐标系为 `SENSOR`。
- 仅 Session 层建立图、参考坐标系和运动实验设置，不保存磁盘 USD。
- 没有外部依赖下载、安装或更新。官方网页资料访问已单独登记。

## 3. 普通分层测量

同样预热 24 次原生更新，随后测量 60 次更新；每段推进 1 秒仿真时间。这是短测量，不代表长时间稳定吞吐。

| 实验 | 60次更新墙钟 | 更新/真实秒 | 每次墙钟均值 | 主线程CPU均值 | Kit CPU核当量 | GPU NVML均值/范围 |
|---|---:|---:|---:|---:|---:|---|
| A 原生生成，GPU annotator，不读数组 | 13.325 s | 4.503 | 221.94 ms | 218.80 ms | 2.344 | 62.4%，22–97% |
| B 原生生成与官方发布，标准订阅但暂停写盘 | 14.166 s | 4.235 | 235.96 ms | 233.04 ms | 2.865 | 55.8%，17–97% |
| C 加标准MCAP录制 | 14.197 s | 4.226 | 236.49 ms | 233.52 ms | 2.890 | 64.5%，19–97% |
| D 同C，输入参考关节轨迹 | 14.242 s | 4.213 | 236.04 ms | 231.67 ms | 2.962 | 53.1%，3–97% |

CPU 核当量 1 表示一个 CPU 核持续工作，不是整个机器的 100%。NVML 是 1 Hz 全卡采样；不能用于精确描述几毫秒级脉冲。主线程 CPU 计时跨越 await，包含同线程其他引擎回调。

B 的录制器日志确认订阅 24 个目标话题，避免无订阅导致发布成本虚低。C 录制器约消耗 0.212 个 CPU 核当量，B 约 0.145。C 比 B 的短测量只多约 31 ms，不能把这点差异视为稳定、精确的写盘成本。A/B 后处理出口不同，差值也不能解释成纯 DDS 时间。

**当前证据支持：主要耗时在原生生成/处理和引擎侧；标准 MCAP 写盘不是本轮明显的主要瓶颈。原生采集仍存在 GPU 高低负载交替。**

## 4. 更底层的确认

使用现有 Nsight 采集独立的稳态 24 帧窗口，初始化与 profiler 导出不包含在窗口内。采样运行不与普通运行混算速度。

| 指标 | C 官方发布+MCAP | A 只生成、不发布、不录制 |
|---|---:|---:|
| 稳态窗口 | 5.729 s | 5.375 s |
| cuLink / cuModule 生命周期调用 | 未观察到 | 未观察到 |
| cudaHostAlloc | 624次，累计0.883 s | 624次，累计0.878 s |
| cudaFreeHost | 624次，累计3.024 s | 624次，累计3.130 s |
| 最长单次 cudaFreeHost | 123.00 ms | 126.00 ms |

这说明之前逐组启停对应的重复模块生命周期不是这条持续原生链路的稳态行为。结论不覆盖启动时正常的首次编译和模块加载。

固定页内存分配/释放在没有 ROS 发布、没有 MCAP 的 A 中依然存在，所以这项热点并非由项目录制 Worker 或 MCAP 写盘产生。624/24=26 对/更新，和 13 路 LiDAR 的数量关系值得继续验证；**本次尚未证明每一对缓冲具体归属哪个传感器或插件内部结构。**

C 窗口主线程实际被调度约 5.522 秒。主线程 CPU 采样叶模块主要为 NVIDIA `libcuda.so.580.126.09`（3845 个样本），随后为 Fabric 等模块；剥离符号不能据此命名其私有函数。

C 的底层样本均值：GR Active 48.98%、SMs Active 27.51%、SM Issue 4.24%、Tensor Active 0.78%、PCIe RX/TX Throughput 2.78%/2.91%。GR 的峰值为 100%，SM Issue 峰值为 39%。本次 ad10x 指标集没有给出 RT Core 专项指标，不能填成 0。

CUDA/Vulkan GPU区间并集约 5.308 秒，Vulkan batch 区间约 5.290 秒。**batch区间、GR活动、SM活跃、指令发射利用率含义不同**，不能用某个长区间证明所有 CUDA 核持续满载。

`cudaFreeHost` / `cudaHostAlloc` 是含等待的 API 墙钟区间，可能与 GPU、其他 CPU 调用重叠；3.02秒不是纯释放操作的 CPU 计算时间，也不是可直接消除的确定收益。尚需进一步定位缓冲生命周期及驱动同步关系。

## 5. MCAP与对齐检查

标准 bag 包含 24 个核心话题：

| 层次 | 话题 | ROS类型 |
|---|---|---|
| 雷达，13路 | `/lidar/<自动发现ID>/points` | `sensor_msgs/msg/PointCloud2` |
| 图像，4路 | `/camera/fisheye_{front,back,left,right}/image_raw` | `sensor_msgs/msg/Image` |
| 标定，4路 | 对应 `/camera_info` | `sensor_msgs/msg/CameraInfo` |
| 坐标树 | `/tf` | `tf2_msgs/msg/TFMessage` |
| 仿真时钟 | `/clock` | `rosgraph_msgs/msg/Clock` |
| 关节 | `/joint_states` | `sensor_msgs/msg/JointState` |

图像为无损原生 `rgb8`；点字段为 float32 XYZ，与旧项目 XYZ 布局一致。鱼眼标定采用原生 `equidistant` 模型、4个畸变系数，与 USD 的 K/D 核对通过。所有读到的 XYZ 有限。

TF 为 `world → swing_coordinate → 13个LiDAR帧 / 4个相机optical帧`，共18条边。相机 optical 使用 ROS 的右/下/前轴约定。末帧 TF 与 USD 数值核对通过；C 的最大位置偏差约 0.85 微米。**这不证明点云与3DGS物理配准已经完全正确，也不替代逐时刻的运动/曝光对齐验证。**

C 原始实验录到每路传感器85条消息，共85个全传感器共有stamp，MCAP约2.687GB（含预热）。其正式60更新窗口最初各录到59条，原因是原生发布滞后一帧。

最终版本仅在结束时保持最后姿态，再做2次原生更新排空尾帧；单列这2帧，计入总过程但不计测量帧率。最终12帧复核中，13路点云、4路图像、4路CameraInfo及JointState各有12条正式窗口消息，严格计数检查通过。没有逐组新增自定义握手。

D 的原生 JointState 确认 boom/arm/bucket 实际从0移动到约2.349127°，swing始终0°。参考轨迹整机位置和姿态恒定，本次不能声称验证了整机平移/旋转回放。

`--use-sim-time` 使 bag 接收时间使用接收时的仿真时钟；它不保证等于传感器 header 的采集时间。应分别查看 header、Clock 与 bag 时间。正式测量窗口由 `engine_result.json` 界定，包内还包含初始化播放、预热和尾帧。

## 6. 两个额外实验的边界

**冻结时间、18子帧：**2次官方 `rep.orchestrator.step_async(delta_time=0, rt_subframes=18)` 用8.436秒，仿真时间保持0.533333秒。但包内各传感器25条消息的 header 均在0.116667–0.516667秒，全部早于测量开始，没有得到可辨识的两组新冻结采集消息。旧检查显示 `ok` 只代表包中存在24话题/标定/TF；**该实验的冻结快照等价性未通过，不能用0.237“组/秒”作有效采集吞吐。** 新验证器也专门记录此限制。

**Multi-tick：**60次更新用9.134秒；LiDAR消息恢复10Hz；front图像83条却有15个重复header stamp。此模式改变了传感器工作量，图像时间语义仍需处理，不作为默认参数，不把6.569更新/秒解释成同一工作量的确定加速。

## 7. 与旧包不完全相同的地方

- 同 USD、分辨率和渲染质量配置；新包原生 Image，旧包 PNG CompressedImage。新包更大，也少了旧 PNG 编码成本。
- 默认原生连续更新，旧项目每组冻结并16+2次渲染。不能直接计算同质量完整组的加速倍数。
- 默认原生消息实际约60Hz仿真节拍，旧项目采样/门控约10Hz；不能只比较文件量或条数。
- 原生独立话题没有项目自定义 group index、PoseStamped 和 horizontal 帧；它是一份核心传感器标准包，不是旧包接口完全兼容的替换品。
- 已查看导出的原生鱼眼图像，场景和挖掘机均正常出现；没有进行严格主观质量验收或相对旧图像的客观质量判定。

## 8. Warning与实现修正

- `capture_on_play=False` 会让官方 Writer 不执行：首轮只录到TF/Clock/JointState，失败证据保留；改为True后图像/点云发布成功。
- 一个采集后 Gf Matrix 构造签名错误已修正；不隐去失败日志。
- 传统 TF targetPrims / JointState targetPrim 接口有弃用提示；实际采用实例内验证通过的节点。后续新计算/读取节点迁移需要核实实例版本。
- PoseTree 的 `eInvalid` 在非刚体传感器/Xform路径上重复出现。最终USD数值对照通过，所以不能直接等同于TF丢失；仍保留原始warning，不全局屏蔽。
- Motion BVH关闭的运动效果警告与先前基线一致。Instant扫描及规定运动不等于已验证所有运动畸变效应。
- 启动时音频、Fabric版本和schema等警告单独保留，未通过修改系统组件消除。

## 9. 保存位置与复现

代码：

```text
本地 scripts/260920SensorVisualizer/native_capture_baseline/
云端 /root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_baseline/
```

核心MCAP：

```text
/root/gpufree-data/semantic/output/native_capture_baseline/
  wave_ordinary_20261011_124852/C_record/bag/bag_0.mcap
  wave_ordinary_20261011_124852/D_moving/bag/bag_0.mcap
  wave_final_20261011_130446/E_final_record/bag/bag_0.mcap
```

普通、诊断和最终复核的日志、配置、数值检查、图片及两个Nsight原始报告已拉回本地 `reports/runs/`；大型MCAP保留云端。汇总为 `ordinary_analysis.json`、`diagnostic_analysis.json`、`final_analysis.json`。SFTP使用已有凭据引用与主机/实例验证，逐文件哈希核对，独立审计。

启动详见 [README](../README.md)。关闭当前Isaac GUI后在云端运行：

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_baseline
python3 run.py --mode record --frames 60 --warmup 24
```

保存方案、运行文档和报告均同步到云端。测试进程全部退出；与既有备份核对141个旧v06文件无变化；19个所用USD层哈希无变化。该检查不等于扫描所有贴图/PLY文件，但本轮没有对它们执行写操作。

## 10. 下一步应该优化哪里

这条基线可以继续作为独立对照。优先定位原生 pinned 分配/释放的调用来源、GPU等待及缓冲生命周期，判断能否通过已有SDK配置或不同官方出口减少它；不能把Python数组池当成已经管理到插件内部的缓冲。

在转为正式采集方案前，需另行解决：冻结快照官方发布、Multi-tick相机重复时间戳、逐帧运动/曝光对齐与旧包接口兼容。当前不会以降低图像质量或未经测量的CUDA优化替代这些验证。
