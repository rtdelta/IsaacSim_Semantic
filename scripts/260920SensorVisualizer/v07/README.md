# Sensor Visualizer v07

以 v06 为基线的独立双卡版本。保留网页分类、键盘控制、关节 Direct／Target／Periodic、整机平移与旋转、传感器安装调整、轨迹导入导出、三种采集模式和统一 MCAP。运行代码不导入旧版包。

默认 GPU 0 负责交互视口，GPU 1 运行常驻采集服务。两者传递不可变姿态快照，正式采集仍按运动、冻结、渲染、检查、提交的顺序执行。保留十三路 Instant LiDAR、四路 1920×1080 鱼眼与正式画质。CPU 工作池按实例配额设置；交互异步渲染与正式同步采集分开配置。

## 启动

在云端桌面的两个 Linux 终端分别运行：

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v07
/usr/bin/python3 run_web.py
```

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v07
/usr/bin/python3 run_capture.py --interactive --job config/interactive.json --gpu 0
```

云端浏览器打开 `http://127.0.0.1:17875`。等待 `interactive_ready`，点击网页 **Play Simulation**，再调整或使用键盘。Prepare Capture Service 可提前加载 GPU 1；采集结束回到 idle 后可再次开始。Isaac 原生 Timeline 暂停是规定运动时钟的设计，不能用它判断网页运动是否暂停。

网页服务使用 Python 标准库；暂缓的 FastAPI 等依赖没有下载或安装。无需执行 requirements-web.txt。

已有 Isaac GUI 可打开原场景，在 Script Editor 运行本目录 `run_in_isaac.py`。独立交互入口与 Script Editor 入口二选一。

## 文档与证据

- [完整操作、停止和回退](docs/startup_and_usage.md)
- [架构、内部调度和数据所有权](docs/architecture_and_data_contract.md)
- [本轮性能与验证证据](docs/performance_evidence.md)
- [日志文件与完整性](docs/logging_contract.md)
- [操作记录与边界](docs/operation_record.md)

性能结论以本轮 reports 中的实际记录为准。历史 v04/v05 长测不能代替 v07 验收；引擎回执延迟不包含浏览器、网络、远程桌面和屏幕呈现延迟。

产出在 `/root/gpufree-data/semantic/output/sensor_visualizer/v07/`。原 v06、资产和源码备份保留。Fabric、CUDA 异步回读和双卡离线分片仍是后续实验，没有默认接入。
