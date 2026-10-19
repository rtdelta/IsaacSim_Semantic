# single0602Headless

更新日期：2026-10-19（北京时间）。独立运行包：`single0602_headless`，版本 0.3.0。

保留网页配置，在 Isaac GUI 中通过网页或键盘录制完整状态轨迹，结束并排空后，用独立 Headless Isaac 进程沿轨迹采集。正式链路固定为 `offline / persistent_gated / keepalive`。工程上将 cab 相对 track 的角度假定为 0°；启动和每组状态核验原生 DOF，不能将这个假定标记为真实设备实测值。

- [坐标系与键盘运动契约](docs/CoordinateFrames.md)
- [single0602Headless 实现方案](docs/ImpPlan/001_single0602Headless_实现方案.md)
- [连续交互改进方案（002）](docs/ImpPlan/002_连续交互改进方案.md)
- [完整轨迹采集改进方案（003）](docs/ImpPlan/003_完整轨迹采集改进方案.md)

002 已将 GUI 改为原生 Timeline 连续播放，以 1× 为交互目标，继续逐仿真步设置位置并清零物理速度，原生 Stop 结束当前录制。实际倍率显示在网页中，性能与验证范围见 [验证记录](docs/Testing.md)。

业务名称继续为 `world → swing_horizontal_coordinate → swing_coordinate → sensors`。WASD 沿当前水平参考系移动，方向随航向更新且不改变世界高度；Z/X 单独升降。传感器保留实际部件安装偏移。

## 云端启动

在远端桌面的第一个终端运行：

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless
/usr/bin/python3 run_web.py
```

第二个终端运行 GUI 交互入口：

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless
/usr/bin/python3 run_capture.py --interactive --job config/interactive.json
```

在远端浏览器打开 `http://127.0.0.1:17877`。网页服务仅监听回环地址，使用现有系统 Python 标准库；无需下载或安装网页依赖。启动器默认使用现有 `/root/isaacsim`，其他安装位置通过 `ISAACSIM_PATH` 指定。若使用 Script Editor，运行本目录 `run_in_isaac.py`；两种交互入口二选一。

## 一轮操作

1. 等待网页显示 `interactive_ready`。键盘模式默认关闭；编辑输入框只是修改草稿，Apply/Execute 后才改变运动。
2. 点击 **Start Trajectory**，然后 **Play Simulation**。可以使用网页整机、关节 Direct/Target/Periodic、倾斜和安装设置。
3. 勾选键控，等实际应用回执，再点击 Isaac 三维视口。应用和视口都必须获得焦点。网页本身也可以接收按键，输入框编辑时不驱动运动。
4. 录制中可以反复关闭、开启键控；当前姿态、会话和文件保持连续。关闭键控或 Hold 只保持挖机姿态，原生 Timeline 继续播放并记录静止区间；原生面板与网页 Pause 暂停同一个 Timeline 和录制时间，Play 后继续同一文件。
5. 点击 **End Trajectory**，等待 `recording_complete=true` 的实际排空回执。可导出 ZIP，或通过网页导入本版完整轨迹。
6. 选中已完成轨迹，在“采集范围”默认的 **完整轨迹** 下设置采样 Hz，等待预计组数和末次采样时间显示，再点击 **Start Recording**。若只采前段，切换 **指定最多组数** 后填写组数。交互控制器及 GUI 可以在此之前退出；离线任务从自己的不可变轨迹快照取源。
7. 用 **Pause Capture / Resume / Stop + Drain** 管理任务。完成、保存排空、进程退出和资源锁释放是分别观察的状态；资源锁未释放时不启动下一任务。

Isaac 面板 Stop 或网页 **Stop Simulation** 会结束当前轨迹并排空。再次 Play 后等待物理绑定恢复，再点击 Start Trajectory 创建新文件；旧按键与旧运动目标不自动恢复。Stop 后显示的位姿是末次有效状态，重新绑定后才刷新为当前实际状态。

正式采集也可脱离网页启动：

```bash
/usr/bin/python3 run_capture.py --trajectory /root/gpufree-data/semantic/output/sensor_visualizer/single0602Headless/trajectories/完整轨迹目录 --all-trajectory --sample-hz 10
```

该命令返回任务 ID 后退出，独立子进程继续工作。指定组数时将 `--all-trajectory` 换为 `--groups 100`，两者互斥；旧命令未提供这两个参数时仍按最多 100 组处理。轨迹必须位于本版输出目录内；外来文件通过网页 Import 导入。任务的 `job.json`、控制文件、状态文件及日志保存在输出目录的 `tasks/<task_id>/` 下。

“完整轨迹”表示按所选频率采集全部有效时间网格：26.5 秒、10 Hz 自动计划 266 组；26.53 秒同样采至 26.5 秒，不追加非等间隔尾帧。采样组数与运动轨迹状态条数分别计数。任务卡显示范围、计划/已采集/已写入组数；提前 Stop + Drain 会明确显示部分保存结果，数据排空后继续等待进程退出与资源锁释放。

## 键位

| 按键 | 动作 |
| --- | --- |
| W/S、A/D | 当前 H 系前后、左右；水平斜移归一化 |
| Z/X | 世界 Z 升降 |
| Q/E | 整机航向；不改变 cab–track 回转角 |
| R/F、T/G | 横滚、俯仰参数偏移 |
| U/J、I/K、O/L | 大臂、小臂、铲斗原生关节角增加/减少 |
| F8 | 经同一模式入口开关键控 |

原生及网页输入共享 epoch、速度和来源状态。失焦、暂停、网页显式运动命令及模式切换清键；重新控制必须有新的按下事件，KEY_REPEAT 不恢复旧按键。输入来源不叠加。

## 文件和兼容约束

- 本地代码全部位于本目录。云端部署路径同上；输出独立保存在 `/root/gpufree-data/semantic/output/sensor_visualizer/single0602Headless`，IPC 为其下 `runtime/engine.sock`。
- 默认场景为 scene18。`config/asset_profiles.json` 固定场景和 mesh contract 资产哈希、原点版本、swing 原生零位及声明。未知资产或哈希不符时拒绝启动；变更资产前必须建立经过核验的 profile。
- 轨迹保存完整位置、四元数、工作关节和安装 revision；控制事件另存 `control_events.jsonl`。后台队列有界，过载显式失败。direct 和安装 revision 边界不做连续插值。
- 新轨迹采用 `native_simulation_seconds`，旧完整轨迹保留 `prescribed_control_simulation_seconds` 的原始时间含义。导入和重放分别验证时间版本，不重新乘倍率。位置变化率仅用于计算离散位置增量，不下发物理速度或加速度命令。
- GUI 默认允许异步视口渲染；可通过任务的 `interactive.async_rendering=false` 关闭。正式 Headless 采集继续同步冻结状态。其他对象的运动记录和重放尚未实现，已进入 002 方案 TODO。
- 缺少本版坐标契约、原点、关节映射、swing 零位核验或完整标记的旧轨迹会被拒绝。没有证据时应重新录制；不通过补版本字符串或禁用资产哈希来迁移。
- 正式配置保留至少 16 个相机预热子帧和 2 个采集子帧。四相机默认 1920×1080；13 路雷达沿用原生输出轴向。数据编码为 PNG、ROS2 CDR，统一写入 MCAP。
- 只在本项目匿名 USD 会话层设置运行状态。源 USD、旧 v06、single0601 和系统 Python/驱动均不作为本版修改目标。

## 验证与维护

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless
/usr/bin/python3 -m unittest discover -s tests -v
source /opt/ros/jazzy/setup.bash
/usr/bin/python3 tools/validate_capture_data.py /完整采集会话目录
```

本地可使用 `D:\Anaconda3\python.exe -X utf8 -m unittest discover -s tests -v`，运行时工作目录为本项目。实际 Isaac、视口输入及 MCAP 回读使用云端已有环境。

- [实现模块与方案对照](docs/ImplementationStatus.md)
- [验证结果和性能边界](docs/Testing.md)
- [操作记录与回退](docs/OperationRecord.md)
- [移植来源及源码哈希](source_provenance.json)

性能和验收结论只引用本版 reports 中的实际记录，不沿用旧版本测试结论。

## 报告与验收证据

正式报告、精选验收摘要和必要配图见 [报告索引](docs/reports/README.md)。原始采集、逐帧状态和性能追踪保留在原运行目录，由仓库忽略规则排除。
