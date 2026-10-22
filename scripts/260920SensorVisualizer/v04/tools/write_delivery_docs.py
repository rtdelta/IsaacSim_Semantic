"""Generate v04-only documentation; never modify older versions."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
docs={
'README.md':r'''# Sensor Visualizer v04

以用户确认的 v03 为基线创建的独立项目，版本 4.0.0。本目录包含所有源码，不导入旧版本。保留 v03 的关节、整机运动、安装位姿和采集面板，增加持续生成会话、全部传感器完成回调、明确天空光选择及原生性能关联日志。

旧 v02/v03 在双端 `../backups/20261009_before_v04` 保存 ZIP 和逐文件哈希。原始 USD 不 Save；运动、安装和灯光选择只写可移除的 Session 层。

## 运行

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v04
/usr/bin/python3 run_capture.py --gui
# 或离线严格阶段开关
/usr/bin/python3 run_capture.py --job config/offline.json
# 或离线保留传感器资源以提高吞吐
/usr/bin/python3 run_capture.py --job config/throughput.json
```

GUI 启动后打开 combine_scene_16_terrain_fisheye.usda，在 Script Editor 运行本项目 run_in_isaac.py。按钮顺序见 [完整流程](docs/startup_and_operation.md)，实测与失败实验见 [验收报告](docs/deployment_and_native_test.md)。

## 链路

```text
有界缓冲槽 → 运动/时钟推进 → 暂停并冻结姿态与时间
→ 同姿态预热 → 每个相机和雷达 schedule_write
→ step_async(delta_time=0, wait_for_render=True)
→ 全部回调复制为独立 CPU 数据 → 来源时钟/渲染矩阵校验
→ 后台打包 → 独立进程并行 PNG → CDR → 顺序 MCAP
→ 下一组；暂停/结束时停止并排空生成会话
```

默认 gated 在运动期间关闭相机和雷达；keepalive 仅供离线模式，活动组间保留实际更新，中间运动渲染不录制。空闲、暂停、背压、结束仍关闭全部传感器。两者不缩减传感器、1920×1080 分辨率、16 个相机预热子帧或 2 个正式子帧。

## 天空光

本场景同时有 HDR 与近黑色地形 DomeLight。原生实验发现持续会话与逐组停启会选到不同背景。默认 render.background_dome 选择 /environment_Fangshan_02/DomeLight，在临时层停用其他 DomeLight；方向光和区域光不受影响。公平性能对照也使用相同选择。

这是明确的渲染配置变化，不是静默保留所有光源。另一场景应指定其可见 DomeLight 路径。要保留原有所有光源，使用 background_dome: null 和 capture.backend: compatibility。持续后端遇到多盏可见 DomeLight 而未明确选择，会拒绝初始化。

## 数据、日志、限制

默认输出 /root/gpufree-data/semantic/output/sensor_visualizer/v04。保留 /clock、/tf、关节与整机位姿、点云、PNG、CameraInfo、相机位姿和 frame_index，坐标与 ROS 类型沿用 v03。

diagnostics_ref.json 指向 runs/<run_id>/diagnostics：事件、资源、警告、源码哈希、配置和渲染证据。新增线程累计 CPU 时长与可选 NVTX 原生标记，详见 [实现说明](docs/implementation.md)。原生 Kit/RTX 调用仍可能阻塞主线程，Pause/Stop 在完整组边界生效，不保证立即响应。

未下载、安装、升级任何驱动、库、系统或桌面组件。experiments 仅用于复现诊断，可以读取旧基线；生产入口不执行这些文件。

## 回退与检验

关闭 v04、等待写包结束，然后运行保留的 v03 入口，无须覆盖旧目录。双端备份保留。

```bash
source /opt/ros/jazzy/setup.bash
/usr/bin/python3 tools/validate_capture.py /本次采集绝对路径 --export-images
/usr/bin/python3 tools/analyze_trace.py /诊断目录绝对路径 --trace
/usr/bin/python3 -m unittest discover -s tests -v
/usr/bin/python3 tools/verify_project.py --originals
```
''',
'docs/startup_and_operation.md':r'''# v04 完整启动与运行流程

## GUI

1. 关闭其他采集控制器，在远端终端执行：

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v04
/usr/bin/python3 run_capture.py --gui
```

2. 打开 /root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_16_terrain_fisheye.usda，在 Script Editor 执行：

```python
from pathlib import Path
p = Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v04/run_in_isaac.py')
exec(compile(p.read_text(encoding='utf-8'), str(p), 'exec'))
```

3. 此入口只创建面板。不要手动按 Timeline Play。面板沿用 v03 的 Initialize / Start Capture 流程，不是更早版本的 Play Simulation / Start Recording。
4. 可先填写 Job JSON，按 Load Job (before Init)。选择传感器 ID，空白表示全选，再按 Initialize Current Stage，等待 Ready。第一次初始化仍可能卡顿，不要重复运行入口。
5. Joints and body tilt 支持 Direct、Target + speed、Periodic。Whole machine 支持 XYZ、Yaw、前进速度和转速，cab–track 保持初始角度。LiDAR mounts 可修改父节点局部 XYZ/RX/RY/RZ。采集中 Apply 在完整组边界生效。
6. 每次安装修改写入 pose_adjustments/.../pose_changes.jsonl；Save Current Poses 保存快照，Save Job 保存配置。需要保留时应在 Stop 前显式保存。
7. 设置 Groups、Hz、Interactive/Offline 与 ROS preview，按 Start Capture。程序自动运动→冻结→预热→采集→后台写入；只有组间运动推进仿真时间。10 Hz 是仿真时间网格，不等于墙钟吞吐。
8. Pause 完成当前组后停用传感器并排空会话；Resume 继续；Stop + Drain 完成当前组与后台写包后恢复初始运动/安装位置。等待 finished 才开始下一轮。Close / Restore 释放产品并恢复 Session 层和设置。

原生调用阻塞时，控制请求要等引擎恢复才会被处理，不保证即时停止。CLI 启动器保留已验证的 Motion BVH/MultiTick 兼容参数；已有 GUI 也可用，但不要同时启动第二个场景控制器。

## 资源与天空配置

config/interactive.json 限制交互倍率不超过 0.1。config/offline.json 不限速且运动期间关闭全部产品。config/throughput.json 仅供离线，组间保留实际传感器更新，丢弃没有正式请求的中间渲染；暂停/结束照常关闭。

默认 render.background_dome 选择现有 HDR DomeLight，在临时层停用近黑色地形 DomeLight以解决背景冲突，关闭后恢复。换场景应设置对应可见 DomeLight 路径。保留所有原有光源时使用 background_dome: null 和 capture.backend: compatibility。

## RViz

启用 ROS preview 后，在第二个终端执行：

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v04
/usr/bin/python3 launch_rviz.py --session /本次采集目录绝对路径
```

Fixed Frame 使用 world，各 PointCloud2 显示项独立勾选。取消显示不停止 Isaac 计算；preview 墙钟节流，MCAP 保存完整采集组。

## 离线及验证

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v04
/usr/bin/python3 run_capture.py --job config/diagnostic.json
# 正式任务：二选一
/usr/bin/python3 run_capture.py --job config/offline.json
/usr/bin/python3 run_capture.py --job config/throughput.json
source /opt/ros/jazzy/setup.bash
/usr/bin/python3 tools/validate_capture.py /本次采集目录绝对路径 --export-images
/usr/bin/python3 tools/analyze_trace.py /diagnostics_ref.json指向的目录 --trace
```

先用小组数确认画面和数据，再采集 100 组。smoke.json 只选前相机，不用于声称全传感器性能。

默认输出根目录 /root/gpufree-data/semantic/output/sensor_visualizer/v04。采集目录包含 bag_unified、capture_index.jsonl、writer_report.json、配置、注册表、来源证据和 diagnostics_ref.json。安装日志及快照独立保存在 pose_adjustments。

验证器全量检查 PNG、PointCloud2、TF、源时间、冻结状态、组完整性和 CDR 哈希。图像内容还需检查四路导出图；仅通过时间和矩阵检查不证明画面一致。

## 回退

关闭 v04 后直接使用保留的 v03 入口。双端备份目录为 260920SensorVisualizer/backups/20261009_before_v04，包含 v02/v03 ZIP 与哈希。没有系统层改动，不需要重装驱动或桌面。
''',
'docs/implementation.md':r'''# v04 调度、数据所有权与原生诊断

## 函数与接口

| 阶段 | 项目函数 | 外部接口/执行线程 |
|---|---|---|
| 背压与调度 | CaptureRunner.run、RecordPipeline.reserve | asyncio、有界槽；Isaac 主线程 |
| 运动 | SceneStepper.advance | Timeline play/pause/commit、Kit next_update_async、Articulation tensor；主线程，正式流程唯一推进时间的阶段 |
| 冻结 | SceneStepper.capture 的 frozen 检查 | SimulationManager、Timeline、UsdGeom.XformCache；主线程 |
| 预热 | SensorDrivers.warm_cameras、_step | Replicator step_async(delta_time=0)；主线程调用、GPU执行 |
| 请求 | SensorDrivers.acquire | 每路 Writer.schedule_write、step_async(wait_for_render=True) |
| 完成回读 | _receive、_copy_host、read | CUDA Annotator、Warp.numpy/NumPy、CameraParams、IsaacReadSimulationTime、RTX transform |
| 打包 | RecordPipeline.submit | asyncio.to_thread、mmap、socket；后台线程只使用独立CPU数据 |
| 编码/录制 | record_worker | Pillow、线程池PNG、rclpy CDR、rosbag2_py MCAP；独立进程 |
| 安全停启 | finish_generation、_drain_generation | wait_until_complete_async；暂停/结束边界 |

所有正式请求均在冻结姿态和时间下完成。回调立即复制 GPU payload 为独立 CPU 数组，全部相机和雷达收到并验证后才推进下一组。后台第N组编码/保存可与第N+1组采集重叠；线程不并发调用USD、Kit、Annotator或原生指针。

## 正确性

来源时间容差保留2ns，渲染矩阵误差阈值保留2e-3。group/request/sensor只关联请求；source_frame_id未暴露，保持null，不伪造。冻结验证同时检查原生时钟、Timeline、机器人部件矩阵和安装revision。

缺回调、晚回调和来源异常不重新贴时间戳。缺回调直接失败，遗留pending不能转交新组。重试只允许已完成请求且场景仍冻结的来源时间/矩阵异常。失败即停用产品，包含keepalive策略。

compatibility保留v03相机回调、LiDAR排空后轮询路径。persistent_gated使用所有传感器手动回调；每组不停止生成会话，暂停、结束、关闭时才全局排空。native渲染返回与独立回调所有权构成组完成屏障。

## 资源策略与灯光

gated默认在空闲、运动、背压、暂停和成功取得数据后关闭全部产品。预热时全部开启，以同姿态初始化RTX位姿；只预热相机的实验产生错误LiDAR矩阵，已拒绝。

keepalive仅允许offline持续后端。活动组间保持真实更新，减少CUDA/Vulkan再建；中间运动渲染没有正式请求，不保存。暂停、结束、失败、背压关闭产品。它增加中间渲染以减少CPU初始化，是否划算以有效组/秒实测判断，不能按GPU利用率升高判断。

select_dome在运行层明确选择一个可见DomeLight，停用其他DomeLight。原生实验中两盏光源同时有效导致持续会话天空黑色，图像PSNR仅4–7dB；临时停用近黑色地形光后恢复31–33dB。原始文件不修改，公平基线使用同样选择。null保留作者配置；持续后端在多盏可见光源且未选择时拒绝初始化。

## 日志与原生追踪口径

RunDiagnostics.begin/end记录monotonic_ns、UTC、PID/TID、group/request/sensor及span ID。thread_cpu_duration_ns是同一OS线程跨await的累计CPU，包含引擎与其他回调，不是函数自身CPU；跨线程结束为null。

可选native_profiler=nvtx使用已安装libnvToolsExt，以RangeStart/RangeEnd关联原生时间线，不使用跨await线程push/pop假设独占线程。默认off；短追踪与性能验收分开。

Nsight包含Vulkan、CUDA、OSRT、NVTX、原生栈和线程调度。实验仅在自己的进程中包装SDK，finally恢复，不改安装目录。direct Kit在profiler注入前整理环境，不修改全局LD_PRELOAD。

Nsight2025.1与CUDA13存在兼容警告，闭源符号不全。individual Vulkan溢出时记录并集只代表工作下界；batch覆盖区间可能包含内部空档，不能当成GPU持续100%。整卡nvidia-smi和进程采样也不是函数的资源消耗。等待、回读、后台编码与原生GPU工作重叠，不能简单相加。

## 保护范围

只部署v04，旧源码逐文件哈希检查，双端ZIP备份。USD变更仅Session层，关闭恢复。无外部下载、依赖安装、驱动/系统/桌面变更。诊断是项目性能排查，不是主机安全认证。
''',
}
for name,content in docs.items():
    (ROOT/name).write_text(content,encoding='utf-8')
print('Wrote v04 delivery documentation')
