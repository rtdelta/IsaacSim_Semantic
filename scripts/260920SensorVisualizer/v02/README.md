# Sensor Visualizer v02

独立子项目。父目录的 v01 入口、代码和磁盘 USD 不被覆盖。v02 自带所需的旧运动数学模块副本，来源哈希见 `provenance.json`，运行不导入父项目。

## 启动

远端目录：`/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v02`。

### 交互面板

1. 打开现有 `combine_scene_16_terrain_fisheye.usda`。关闭正在控制此场景的 v01 面板。
2. Script Editor 打开并运行 **v02/run_in_isaac.py**。
3. 按 **Initialize Current Stage**，等待 Ready。无需手动按时间轴 Play。
4. 调整关节、Pitch/Roll、整机位置或雷达安装位姿。模式是 Direct、Target + speed、Periodic；角速度单位为度／仿真秒。cab–track 保持初始角度。
5. 设置 Groups、10 Hz，选择 Interactive 或 Offline。前者不高于 0.1 倍速，后者不限墙钟速度。
6. **Start Capture** 同时开始完整组采集和 MCAP 记录。勾选 ROS preview 才发布 RViz 预览。
7. **Pause** 在完成当前组后暂停；Resume 继续；**Stop + Drain** 完成本组并排空后台队列，然后恢复初始机器人姿态和雷达安装位姿。
8. 调整值得保留时先按 **Save Current Poses** 或 **Save Job**，再停止。关掉窗口也会排空并恢复。

所有运动与安装调整命令只在组边界执行。编辑框是草稿，必须按 Apply。改变采样率／采集传感器清单后重新 Initialize。场景中的新传感器在重新初始化时发现。采集时不要另外操作时间轴或启动其他场景控制脚本。

若需新开 Isaac GUI，使用：

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v02
/usr/bin/python3 run_capture.py --gui
```

### 无界面离线采集

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v02
/usr/bin/python3 run_capture.py --job config/offline.json
```

默认 100 组、10 Hz，全部发现的 Instant LiDAR 和四路鱼眼。`config/offline.json` 可只写需要覆盖的参数；完整默认值在 `sensor_visualizer_v02/contracts.py`。保存面板任务后，可以将 `--job` 指向 `config/saved_job.json`。

默认先对相机进行 16 个冻结子帧预热，再启用雷达取得同时间的完整组，以改善 3DGS 细节。`--job config/throughput.json` 省去额外相机预热，速度较快、细节收敛较少；两者都保留严格时间和位姿检查。当前完整场景仍有原生推进／渲染瓶颈，实际性能与剩余警告见 [验收记录](docs/verification.md)。

一个组是同一冻结场景下所有传感器的输出；100 组的首末采样跨度为 9.9 仿真秒。离线不承诺实时运行，更不强制 GPU 满载。

### RViz

先启动勾选了 ROS preview 的采集，再在远端桌面的终端运行：

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v02
/usr/bin/python3 launch_rviz.py
```

也可 `--session /绝对路径/采集目录`。Fixed Frame 为 `world`，每路 LiDAR 都有独立 PointCloud2 显示开关，TF 显示传感器位置／方向。取消勾选只隐藏显示。离线默认关闭预览，防止 DDS/RViz 影响记录吞吐。预览按墙钟限频，MCAP 保存全部完整组。

## 采集顺序与并行边界

`CaptureRunner.run` → 预留槽 → `SceneStepper.advance` 推进固定物理步并应用规定运动 → Pause/Commit → `SensorDrivers.render(delta_time=0)` → 相机完成回调复制图像，渲染完成后立即复制 LiDAR 的主 XYZ 数组 → 验证时钟、机体／传感器位姿与渲染矩阵 → 快照 TF → `SlotPool.pack` → 下一组。

另一个系统 ROS Python 进程通过本机 UNIX socket 和 mmap 接收数据；四线程编码鱼眼 PNG，单一 writer 按序写标准 ROS 2 MCAP。Isaac 可以采下一组，同时后台编码／写上一组。队列满时等待，不静默丢帧。

GPU 渲染由同一次 Replicator 调度处理多个 Render Products；不从多个 Python 线程修改 USD。物理推进阶段只接受控制结果，正式采样只取冻结阶段结果；当前使用固定物理步，没有省略 PhysX 同步步骤。

## 数据目录

输出根目录：`/root/gpufree-data/semantic/output/sensor_visualizer/v02/`。

```text
日期时间_任务ID/
  bag_unified/             # ROS 2 bag；一个或多个 .mcap + metadata.yaml
  session.json             # 状态、组数、墙钟耗时；finished 才表示正常结束
  job_spec.json            # 完整任务参数
  sensor_registry.json     # sensor ID / prim / topic / frame / 原始标定
  render_profile.json      # 请求值、实际渲染设置、原生时钟起点
  asset_manifest.json      # 根 USD 哈希、已用层、加载状态
  mount_poses_at_start.json # 本次启动安装位姿
  capture_index.jsonl      # 已写入组和分段关闭记录
  writer_report.json       # 消息计数、序列化哈希、编码／写入耗时
  record_worker.log
  performance/             # 分阶段耗时、CPU/RSS、整卡 GPU 采样
```

安装调整审计：输出根目录的 `pose_adjustments/<会话>/pose_changes.jsonl`；显式保存位姿在同目录 `poses_<时间>.json`。这些操作不保存回原 USD。

MCAP 话题：

| 话题 | 类型／含义 |
|---|---|
| `/lidar/<id>/points` | PointCloud2；局部 XYZ 米；float32 × 3、12 字节／点，与旧 MCAP 相同 |
| `/camera/{front,back,left,right}/image_raw/compressed` | CompressedImage；原始畸变鱼眼 RGB，无损 PNG |
| `/camera/<id>/camera_info` | CameraInfo；equidistant；K 和 D 对应 USD 原生 OpenCV fisheye 配置 |
| `/camera/<id>/pose` | PoseStamped；世界坐标中的 optical 位姿 |
| `/tf` | world → swing_horizontal_coordinate → swing_coordinate → LiDAR／camera optical |
| `/clock`、`/joint_states`、`/excavator/root_pose` | 同组仿真时间、实际关节角弧度、根位姿 |
| `/sensor_visualizer/frame_index` | 组号、源时间、安装修订、点数、原始 USD 变换、渲染误差 |
| `/sensor_visualizer/run_metadata`、`camera_metadata` | 每个分段的任务与标定快照 |

同组消息 header 和 bag timestamp 使用一致的整数纳秒；源自 Isaac 原生仿真时钟，不是 UTC。Replicator 初始化期间的时钟偏移被记录并排除出正式采样。四路相机的光学坐标统一为 X 右、Y 下、Z 前。

## 验证与诊断

```bash
source /opt/ros/jazzy/setup.bash
/usr/bin/python3 tools/validate_capture.py /绝对路径/采集目录 --export-images
```

检查 CDR 回读哈希、组完整性、共同时间戳、PNG 解码、点云布局，以及 TF 合成结果与渲染／USD 矩阵一致性。`validation_report.json` 是读取验证结果；它不等价于所有场景素材的物理真实性认证。

`--diagnostic quality` 执行固定姿态下 DLSS Performance／Quality 与 2／8／16 子帧对照，输出 `reports/quality/`；`--diagnostic ui` 执行有限的面板／暂停／恢复／停止测试。这些命令均创建独立无界面 Kit，不操作已打开的 GUI。

性能日志中的 GPU 是整卡值；存在其他 GUI 或任务时，不能把它都归因于本采集器。比较前应同时看组／墙钟秒、各阶段耗时、队列等待与同等画质。

`render` 包括相机预热、共同采集和新结果等待；`camera_warmup`、`freshness_retry_render` 是其中的子项，不要重复相加。

## 环境与回退

复用 `/root/isaacsim`、`/opt/ros/jazzy`、已有 Pillow／NumPy；没有安装系统依赖或修改桌面环境。新启动器关闭扩展注册表下载、HTTP 服务和自动崩溃上报；仅约束本启动器设置，不代表全主机网络隔离。读取公开技术文档与项目传输保留操作记录。

旧入口仍在父目录 `run_in_isaac.py`，关闭 v02 后可继续使用。v02 的所有 USD 修改位于临时 Session 层；关闭后移除。远端 v02 自身每次部署前的变更副本保存在 `deploy_history/`。
