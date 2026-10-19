# v04 完整启动与运行流程

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
