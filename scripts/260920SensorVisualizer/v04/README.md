# Sensor Visualizer v04

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
