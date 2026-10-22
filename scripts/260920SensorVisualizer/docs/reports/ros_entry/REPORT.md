# Script Editor Run 闪退排查与修复

日期：2026-09-21；目标：新实例 `120.209.70.195:30729`，`gpufree-container`。执行渠道：Codex 经 SSH 的项目级排查、部署和独立验证。

## 用户这次闪退的直接原因

北京时间 10:42:30 启动的 Isaac Full 6.0.1-rc.7 使用新项目原来的 `open_combine_stage.sh`，由 NVIDIA 通用启动入口打开场景。该入口没有准备旧 LiDAR 发布项目所需的完整 ROS 库路径。启动日志先出现：

```text
Create Factory Failed: Could not load ROS2 Bridge due to missing library dependencies
ROS2 Bridge startup failed
```

10:57:27 执行 Script Editor，10:57:28 崩溃。Python 主线程堆栈停在旧 `lidar_visualizer/runtime.py` 的 `bridge.get_startup_status()`（修改前第 111 行）。扩展显示 enabled 不代表其原生 ROS factory 已成功启动；此构建在查询失败接口时发生段错误。这是我提供的新场景启动器与已有发布器没有统一启动环境造成的对接问题。

证据：本目录 `kit_20260921_104230.log` 的 20497 / 20499 行及 `crash_python_stack.txt`。原始远端日志位于 `/root/.nvidia-omniverse/logs/Kit/Isaac-Sim Full/6.0/kit_20260921_104230.log`。

未发现本次原始崩溃由内存配额耗尽造成的证据，检查时 cgroup 的 oom / oom_kill 为 0。后续崩溃报告界面的退出失败是后果，不作为原始原因。

## 已部署修复

1. `260920SensorVisualizer/tools/open_combine_stage.sh` 统一调用 `260907LidarVisualizer/launch_isaac.py`，继续自动打开场景 13，同时获得该发布器已使用的 ROS / 原生库环境、句柄上限和渲染设置。
2. `260907LidarVisualizer/lidar_visualizer/runtime.py` 在接触原生 ROS 接口之前检查本项目启动约定：ROS_DISTRO 为 jazzy，LD_LIBRARY_PATH 包含 Isaac ROS core 的 bin 与 jazzy/lib。缺失时返回可读错误，要求重启 Isaac，不再继续查询失败接口。该检查覆盖本次已确认的缺失路径问题，不承诺捕获所有原生 ROS 故障。
3. 新项目保存旧运行模块的补丁副本 `compatibility/legacy_runtime.py`，新增独立验证工具 `tools/validate_ros_entry.py`，更新 `COMBINE_STAGE.md` 的一致启动方式。

本地备份：`diagnostics/20260921_gui_crash/before/`。远端备份：新项目的 `reports/ros_entry/backups/`。需要回退时，可分别恢复对应的启动器和旧 runtime；回退也会恢复本次启动路径缺陷。

## 验证结果与独立发现

最终使用有窗口的 Isaac Full GUI 进程，与用户工作流相同；测试专用 ROS domain 为 137，输出写入 `reports/ros_entry/`，未启动正式录制。

- 缺失 ROS 路径的模拟检查被 Python RuntimeError 拒绝，没有查询原生接口。
- 13 个雷达自动发现、Scripted 模式初始化成功。
- 独立 ROS 订阅者接收每路至少 2 条非空点云；各路观测到的最大点数为 27,883～76,343。
- 13 个传感器 TF 均收到，父坐标为 `swing_coordinate`，并收到世界到参考坐标的链路以及 26 条 `/clock`。
- 状态采样计数：Scripted 28，切换 Observe 后 25。Observe 模式初始化也通过。
- 最终进程退出码 0，本轮日志无 `[Error]`。退出前出现保存场景确认框，人工选择 Don't Save 后正常退出；不是退出崩溃。验证工具随后补充直接关闭测试 Stage 的清理代码，以免自动测试停在该对话框；这一测试辅助代码的后续版本未另行重跑 GUI。
- 场景磁盘 SHA256 始终为 `780cab54e1067c3fef6c2a66b0e6b5776c06164645957f7716bbc159c9e8c4d6`，未保存测试姿态到场景。

完整接收结果、命令和日志见 `reports/ros_entry/result.json`、`received.json`、`attempt_command.json`、`kit.log`、`process_exit_code.txt`。

独立发现：最初采用 Full GUI experience 加 `--no-window --/app/window/hideUi=1` 做测试，在绑定点云 writer 时发生 `Line.pixel.hlsl` GPU page fault / ERROR_DEVICE_LOST，退出 139。清空偏好、调整显示项、增加渲染切换等待、减小 RenderProduct 和限制输出到 GMO 均未解决。恢复普通 GUI 模式后，同一发布链路通过。此问题的底层着色器机制尚未定位，不把它作为用户原始 ROS 崩溃的原因，也不把无窗口模式宣称可用。失败证据保留在 `attempts/01_*` 到 `attempts/05_*`。

仍有音频设备、Fabric 接口版本、关闭 Motion BVH 和关闭/重建渲染产品时的接口释放警告。测试没有验证长期稳定性、RViz 实际显示、MCAP 新录制和完整 3DGS 合同接口。

## 改动边界

仅修改上述项目源码、文档和项目证据目录，启动独立 Isaac / ROS 验证进程；没有安装或升级库，没有修改驱动、系统服务、桌面组件、SSH、全局预加载或系统 Python。没有修改挖掘机和传感器资产。原始用户 Isaac 已崩溃退出，测试只清理本任务创建的进程。
