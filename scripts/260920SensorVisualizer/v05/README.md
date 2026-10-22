# Sensor Visualizer v05

独立网页控制、连续键盘运动、可导入导出的实际姿态轨迹，以及独立 Isaac 进程的完整传感器采集。

本地目录：`scripts/260920SensorVisualizer/v05`。远端目录：`/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v05`。

当前默认网页服务只用 Python 标准库，**不需要 pip install**。用户已暂缓网页依赖下载；FastAPI/WebSocket 是保留的可选入口，尚未运行验证。

## 最快启动

在云端桌面终端运行网页服务：

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v05
/usr/bin/python3 run_web.py
```

另开一个云端桌面终端，启动专属 v05 Isaac 窗口，自动加载场景：

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v05
/usr/bin/python3 run_capture.py --interactive
```

云端桌面浏览器访问 **http://127.0.0.1:17865**。等状态显示 `interactive_ready` 后点击网页上的 **Play Simulation**。Isaac 原生 Timeline 的 Play/Stop 不用于这一控制时钟。

保留已有 Isaac GUI 的替代方式：打开 `combine_scene_16_terrain_fisheye.usda`，在 Script Editor 中运行本项目 `run_in_isaac.py`；不要同时使用两个交互入口。建议先结束旧脚本并关闭其 Isaac 窗口，避免旧传感器产品继续运行。

## 使用顺序

1. 调整 XYZ/Yaw、关节、整机 Pitch/Roll 和传感器安装位姿。各关节与 Pitch/Roll 支持 Direct、Target + speed、Periodic。
2. 键盘默认开启，Play 后用 W/S、A/D、R/F 平移，Q/E、I/K、J/L 旋转，U/O、T/G、Y/H 操作大臂、小臂、铲斗；速度以仿真秒计。输入框编辑与失焦时停止键控。Isaac 时间轴的暂停是设计行为，以网页运动状态为准。
3. **Start Trajectory → 操作 → End Trajectory** 生成实际已应用姿态的 CSV 和元数据。Export ZIP；编辑后用 ZIP 或 CSV + 原 metadata.json 导回。
4. 采集可选：轨迹离线重放、实时优先最新状态、实时完整轨迹网格。点击 **Start Recording** 后，另一个无窗口 Isaac 进程采集 13 路 Instant LiDAR 和 4 路鱼眼相机。
5. **Stop + Drain** 在完整组边界停止并封闭 MCAP。等任务 `finished` 且进程退出后可以再次采集。
6. 结束轨迹后用 **Stop / Restore** 复位，仍可再次 Play；**Exit Controller → Reinitialize Controller** 用于释放和重新建立控制器。

交互控制 ≤0.1x，但画面与输入循环限速 60Hz；离线采集不限速。完整轨迹模式可能延迟，最新状态模式可能跳过中间网格。两种实时模式均可选。

## 文档

- [完整启动与停止流程](docs/startup_and_usage.md)
- [架构、时间契约与数据结构](docs/architecture_and_data_contract.md)
- [验证结果及边界](docs/validation.md)
- [2026-10-10 键盘与重复运行修复](docs/20261010_interaction_fix.md)
- [暂缓的网页依赖批次](docs/web_dependency_batch.md)

原 v04 保留；备份位于项目父目录的 `backups/20261009_before_v05`，部署时替换的 v05 文件另存于远端 `v05/deploy_history`。当前版本不在运行时导入旧版本。
