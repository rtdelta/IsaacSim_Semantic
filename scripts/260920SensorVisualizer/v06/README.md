# Sensor Visualizer v06

独立于 v05 的性能优化版本。保留网页控制、原生键盘、关节三种运动方式、整机运动、传感器安装调整、轨迹导入导出、三种采集模式及统一 MCAP。

本轮优先降低交互主线程开销；正式图像仍为四路 1920×1080，完整场景仍采集十三路雷达。原始 USD 与 v05 没有作为优化目标修改。

## 启动

在云端桌面的两个 Linux 终端分别运行：

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06
/usr/bin/python3 run_web.py
```

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06
/usr/bin/python3 run_capture.py --interactive --job config/interactive.json
```

云端浏览器打开 `http://127.0.0.1:17875`。等待 `interactive_ready`，点击网页 **Play Simulation**，再调整或使用键盘。Isaac 原生 Timeline 暂停是规定运动时钟的设计，不能用它判断网页运动是否暂停。

网页服务使用 Python 标准库；暂缓的 FastAPI 等依赖没有下载或安装。无需执行 requirements-web.txt。

已有 Isaac GUI 可打开原场景，在 Script Editor 运行本目录 `run_in_isaac.py`。独立交互入口与 Script Editor 入口二选一。

## 文档与证据

- [完整操作、停止和回退](docs/startup_and_usage.md)
- [架构、内部调度和数据所有权](docs/architecture_and_data_contract.md)
- [本轮性能与验证证据](docs/performance_evidence.md)
- [CPU/GPU、Stream/Event 和 C++/CUDA 的取舍](docs/native_hotspots_and_gpu_design.md)
- [操作记录与边界](docs/operation_record.md)

性能结论以本轮 reports 中的实际记录为准。历史 v04/v05 长测不能代替 v06 验收；引擎回执延迟不包含浏览器、网络、远程桌面和屏幕呈现延迟。
