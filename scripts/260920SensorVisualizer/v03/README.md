# Sensor Visualizer v03

独立的 Isaac Sim 多传感器采集项目。按方案 002 实现统一传感器启停、冻结采集就绪检查、异步 CPU 数据交接和贯穿整个运行过程的诊断日志。

本目录包含所有项目代码和配置，不导入或执行相邻旧版本代码。场景资产、Isaac Sim、系统 ROS 2 属于外部运行环境。2026-10-08 已部署至远端同名 `v03` 目录并进行真实 Isaac/RTX/ROS 验收；测试结果、性能限制和未消除的原生警告见 [部署测试报告](docs/deployment_and_native_test.md)。

首次使用请按 [完整启动与运行流程](docs/startup_and_operation.md) 操作，包含面板按钮、RViz、离线任务、正常停止和输出校验。

## 已实现的链路

```text
面板 / 离线配置
  → 等待可用缓冲槽（所有传感器关闭，仿真暂停）
  → 原生 Kit 步进和关节/整机运动（所有传感器关闭）
  → 冻结原生时间、Timeline、机器人和传感器位姿
  → 相机预热（16 子帧，LiDAR 关闭，不请求正式图像）
  → 手动请求相机 Writer + 正式渲染（2 子帧，选中传感器开启）
  → 等待回调、读取 LiDAR、复制为独立 CPU 数据、检查来源时间和渲染位姿
  → 关闭所有传感器更新
  → 后台线程打包到 mmap 槽和发送 IPC
  → 独立录制进程：并行 PNG → ROS 消息/CDR → 顺序 MCAP → 可选 ROS 预览
```

第 N 组后台编码/保存与第 N+1 组采集可以重叠。场景和渲染资源始终由 Isaac 主线程拥有；CPU 线程不操作 USD、Kit、Annotator 或原生 GPU 指针。

保留 Instant LiDAR 自动发现、四路鱼眼、关节/整机 Pitch/Roll 三种运动模式、XYZ/Yaw/速度控制、安装位姿编辑和快照、TF/时钟/图像/标定/点云录制。相机参数和画质设置不变；交互模式上限 0.1 倍速，离线模式不限速。停止后恢复初始运动与安装位姿，暂停保留当前状态。所有 USD 变更只写可移除的 Session 层。

## 目录

| 入口或模块 | 用途 |
|---|---|
| `run_in_isaac.py` | Script Editor 打开独立 v03 面板 |
| `run_capture.py` / `kit_entry.py` | 使用已安装 Isaac 启动 GUI 或离线采集 |
| `launch_rviz.py` | 按当前传感器注册表生成 RViz 显示配置 |
| `sensor_visualizer_v03/scene.py` | 运动、冻结验证、预热、采集与恢复 |
| `sensors.py` / `tickets.py` / `gating.py` | 产品生命周期、接收窗口、每组就绪和更新开关 |
| `pipeline.py` / `buffers.py` / `record_worker.py` | 独立 CPU 数据、有界缓冲、后台编码与写包 |
| `diagnostics.py` / `resources.py` / `analysis.py` | 异步日志、资源采样、离线分析 |
| `robot/` | 本项目内完整的运动、发现、位姿与参考系实现 |
| `config/` | 完整默认值在 `contracts.py`；JSON 文件提供覆盖配置 |
| `tools/validate_capture.py` | ROS 环境中校验 MCAP 时间、TF、PNG、点云和摘要 |
| `tools/analyze_trace.py` | 不依赖 Isaac 的日志分析和时间线导出 |
| `tools/verify_project.py` | 静态依赖检查，以及可选的旧文件哈希核对 |
| `tests/` | 本地可运行的状态机、异步边界、缓冲和日志测试 |

## 运行前提

沿用现有 Linux Isaac Sim 与 ROS 2 Jazzy 环境，默认 Isaac 路径 `/root/isaacsim`，可通过 `ISAACSIM_PATH` 指定。系统 ROS Python 需已有 `rosbag2_py`、MCAP 存储插件、`rclpy`、消息包、NumPy、Pillow；Isaac 内使用自带 RTX、Replicator、USD、Articulation、`omni.ui`。

本项目不安装依赖，不下载资产，不修改系统配置。默认场景为已有的 `/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_16_terrain_fisheye.usda`。需要支持 `Writer.attach(trigger=None)`、`schedule_write()`、`wait_until_complete_async()`。最后一个接口在当前构建中会停止并排空 Replicator，具有真实停启开销；原生测试证明当前适配路径仍需保留此兼容边界。

## GUI 操作

1. 关闭其他采集脚本面板，确保只有一个控制器管理场景。
2. 用已安装的 Isaac 打开默认 combine scene；不要自行按 Timeline Play。
3. 在 Script Editor 运行本项目的 `run_in_isaac.py`。若部署到默认位置，可直接执行：

```python
from pathlib import Path
p = Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v03/run_in_isaac.py')
exec(compile(p.read_text(encoding='utf-8'), str(p), 'exec'))
```

4. 可先填写 Job JSON 路径、点击 **Load Job (before Init)**；再点击 **Initialize Current Stage**。
5. 设置关节、整机或安装位姿；选择采集组数、频率、Interactive/Offline 和 ROS preview。频率及传感器选择改变后需重新 Initialize。
6. 点击 **Start Capture**。面板显示阶段、已取得/已写入组数、等待的相机；采集中修改控制参数会在安全边界生效。
7. **Pause** 在当前组完成后暂停；**Resume** 继续；**Stop + Drain** 完成当前组和后台写包后恢复初始位姿。等待 `finished` 后再退出。缺帧或场景失效后必须重新 Initialize。
8. 不需要后续采集时点击 **Close / Restore**，释放本项目产品、恢复 Session 层和原有设置。

原生渲染调用本身仍可能占用主线程；Python 的异步不能使已阻塞的原生函数立即响应按钮。停止请求不会强行销毁正在使用的 GPU 资源。

## 命令行

以下命令在远端桌面终端的系统环境运行。

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v03

# 打开 Isaac GUI，随后按上述 Script Editor 流程运行面板
/usr/bin/python3 run_capture.py --gui

# 先做三组小样本：前相机 + 自动发现的 Instant LiDAR，保持默认预热画质
/usr/bin/python3 run_capture.py --job config/smoke.json

# 四相机 + 全部 Instant LiDAR，10 组，导出详细日志时间线
/usr/bin/python3 run_capture.py --job config/diagnostic.json

# 正式离线任务
/usr/bin/python3 run_capture.py --job config/offline.json

# GUI 中已启用 ROS preview 后，在第二个终端启动 RViz
/usr/bin/python3 launch_rviz.py --session /绝对路径/本次采集目录

# 采集结束后检验包；只对项目产出的副本/输出进行读取
source /opt/ros/jazzy/setup.bash
/usr/bin/python3 tools/validate_capture.py /绝对路径/本次采集目录 --export-images

# 依据 diagnostics_ref.json 找到运行诊断目录
/usr/bin/python3 tools/analyze_trace.py /绝对路径/runs/运行编号/diagnostics --trace
```

`--gui` 只打开 Isaac，不会自动启动面板。`smoke.json` 不代表全传感器负载测试；性能验收需要使用 `diagnostic.json` 或与基线完全一致的选择/分辨率/预热配置。

## 输出和日志

默认根目录：`/root/gpufree-data/semantic/output/sensor_visualizer/v03`。

```text
v03/
  runs/<run_id>/diagnostics/
    manifest.json                 版本、源码哈希、配置、资产、渲染设置和能力
    events_isaac_<pid>.jsonl       初始化/空闲/运动/渲染/回调/回读/缓冲/控制
    events_writer_<pid>.jsonl      PNG、CDR、MCAP、ROS 分阶段记录
    resources_<role>_<pid>.jsonl   低频进程/主线程/RSS、GPU、cgroup 数据
    warnings_<role>_<pid>.jsonl    警告样例与阶段关联
    warnings*.json                各警告累计数、首次和最后时间
    summary*.json                 定期检查点、丢日志统计和汇总
    anomaly_*.jsonl               有界异常前历史，循环保留最多 32 份/进程
    analysis.json                 运行 tools/analyze_trace.py 后生成
    trace.json                    按需导出，供本地时间线工具读取
  <采集时间_编号>/
    diagnostics_ref.json          指向本次面板/CLI 运行日志
    job_spec.json / session.json
    sensor_registry.json / render_profile.json / asset_manifest.json
    mount_poses_at_start.json
    capture_index.jsonl / writer_report.json / record_worker.log
    performance/summary.json      保留常用阶段统计；细节转入统一事件文件
    bag_unified/                  metadata.yaml 和 MCAP 分段
```

安装位姿调整日志为 `pose_adjustments/<时间编号>/pose_changes.jsonl`，手动快照为同目录下的 `poses_<时间>.json`；具体路径也会由面板 Save Current Poses 返回。

包内保留 `/clock`、`/tf`、`/joint_states`、`/excavator/root_pose`、各 LiDAR 点云和 `/camera/{front,back,left,right}` 的压缩 PNG、CameraInfo、Pose；`/sensor_visualizer/frame_index` 增加运行/采集/请求/重试/场景代次和来源验证信息。ROS 消息类型与坐标含义不变。

## 验证与边界

本地测试命令：

```powershell
python -m unittest discover -s tests -v
python tools/verify_project.py --originals
```

本地测试不导入 Isaac 或 ROS，不代表 GPU 渲染正确性或吞吐已经验收。具体实现、诊断口径和必须进行的原生验收见 [implementation.md](docs/implementation.md)。历史方案参考见 [002_design_reference.md](docs/002_design_reference.md)。
