# v03 面板与本次运行报错排查

检查日期：2026-10-08；远端取证时间：北京时间 16:20—16:22。

本次只读取源码、项目诊断和当前 Isaac 日志，没有修改任何既有项目代码、USD、系统配置，也没有启动采集、操作控制面板、停止或重启远端进程。本地新增本报告与取证结果；SSH 操作通过 cloud-instance-ops 留痕。

## 直接结论

这次 v03 运行只创建了初始面板，没有进入初始化流程。点击 Start Capture 时触发 `RuntimeError: Initialize first`。关节、整机控制和 LiDAR 位姿控件的创建依赖初始化完成，因此本轮没有出现这些控件。此次异常发生在录制进程与采集会话创建之前。

用户已经确认熟悉的是 `Play Simulation / Start Recording / Adjust LiDAR` 这套旧面板。因此不能把界面差异只解释为未初始化：v03 使用了另一套 `Initialize Current Stage / Start Capture` 采集面板，操作流程确实改变了。重构保留了控制逻辑，却没有保留用户期望的交互布局和独立运动/预览体验。

当前 v03 并未删除这些控制功能。磁盘上独立 v02 与 v03 的 `build_details()`、运动控制行及其字段布局一致，但它们不是用户指明的界面基准。匹配用户所述按钮的旧界面代码仍保留在项目根目录的 `sensor_visualizer/runtime.py` 与各 panel 模块中。这里只静态对照，没有调用旧代码。

| 交互 | 用户熟悉的旧界面 | 当前 v03 |
|---|---|---|
| 启动 | 入口执行场景连接和初始化后创建完整控制面板 | 入口只创建初始面板，需手动 Initialize 才创建控制区块 |
| 运动/预览 | Play Simulation 与 Start Recording 分离 | 渐进运动由 Start Capture 的组间调度推进 |
| 保存 | Start/Stop Recording 独立控制 | Start Capture 同时启动组采集与录制 |
| LiDAR 调整 | Adjust LiDAR / Done / Resume；逐传感器编辑行 | 传感器下拉选择；Apply at Next Boundary |
| 未就绪按钮 | 旧 runtime._refresh_controls 根据仿真/录制状态禁用 | Start Capture 未初始化仍可点击，随后抛出异常 |

## 本轮日志证据

运行 ID：`20261008_160315_282822_8228e84a`。

诊断目录：

```text
/root/gpufree-data/semantic/output/sensor_visualizer/v03/runs/20261008_160315_282822_8228e84a/diagnostics
```

原始 Kit 日志：

```text
/root/.nvidia-omniverse/logs/Kit/Isaac-Sim Full/6.0/kit_20261008_160127.log
```

| 北京时间 | 证据 |
|---|---|
| 16:03:15 | `run_in_isaac.py` 调用 `CapturePanel`，诊断 run_opened |
| 16:13:48 | `ui.py:207` 的 capture 入口抛出 `RuntimeError: Initialize first` |
| 16:14:05 | 面板诊断 run_closed |

本轮 `summary.json` 的 spans 为空；没有 initialize、sensor_initialize、motion_command_applied 或 capture_finished 事件，manifest 的 job 仍为空。没有 initialize_failed 记录。因此证据支持“没有进入初始化”，并不支持“初始化过程中关节或传感器报错”的说法。

虽然 warning 汇总同时记录了异常栈与异常文本，原始 Kit 日志将这一条 `Initialize first` 标记为 Error；不是多次独立采集故障。

## 控制功能在哪里

源码位置：`v03/sensor_visualizer_v03/ui.py`。

调用顺序：

```text
run_in_isaac.launch()
  → CapturePanel.__init__()：初始面板，details 尚未填充
  → 点击 Initialize Current Stage
  → CapturePanel.initialize()
  → await SceneStepper.initialize(open_scene=False)
  → CapturePanel.build_details()
  → 创建关节、整机、LiDAR 安装控件
```

| 功能 | 控件所在区块 | 默认状态 | 调用链 |
|---|---|---|---|
| 大臂、小臂、铲斗角度；整机 Pitch/Roll | Joints and body tilt | 初始化后展开 | apply_motion → command → SceneStepper.apply_commands → ArticulationMotion.command / command_tilt |
| 整机 XYZ、Yaw | Whole machine: world position / yaw / velocity | 初始化后折叠 | apply_base → command → apply_commands → command_base |
| 平移速度、转向角速度 | 同上 | 初始化后折叠 | velocity → command → apply_commands → command_base |
| LiDAR 安装位置、旋转 | LiDAR mounts: parent-local pose | 初始化后折叠 | apply_mount → command → SensorPoses.apply |
| 安装位姿快照 | 同上，Save Current Poses | 初始化后折叠 | save_poses → SensorPoses.save |

此处安装位姿面板针对 LiDAR，相机安装编辑尚未在该面板提供；不要将“传感器位姿”解读为所有类型都可编辑。

Direct 在应用命令时改变目标姿态；Target + speed、Periodic、整机速度需要采集调度推进组间运动。初始化之后在空闲状态点击这些渐进模式的 Apply，只设置运动命令，机器人不会自行连续运动。暂停时保持当前姿态。这里与根目录旧项目“按 Play 后独立运动/预览、另行开始录制”的方式有实质区别。

## 部署文件核对

远端与本地以下文件 SHA256 一致：

```text
v03/run_in_isaac.py
  e379975400f2e3a263bbdb64f02a57607525ad8652e7b84a5f59dd2472511634
v03/sensor_visualizer_v03/ui.py
  c19510587811fbbba411b28b4d35bdc542777ca92b5c5e17ede6181232110ec8
v03/sensor_visualizer_v03/scene.py
  8a166496a1fece6cd97bb6d9fff8fe192605202dcd9a11bf2e53d06debda3474
v02/sensor_visualizer_v02/ui.py
  5f5f9f65be0fb84907dd53d5113c2f2fb2c311cb5f25b087c23b88ef1dc090c5
```

当前日志的调用路径明确来自 v03。没有证据表明本次运行了错误版本或漏部署 UI 源码。

## 已确认的易用性问题与验证缺口

1. 未初始化时所有控制区块都不创建，没有占位提示，容易被理解为功能被删掉。
2. 未初始化时 Start Capture 按钮仍可点击，通过异常阻止操作，产生红色报错而不是就绪状态引导。
3. 整机和 LiDAR 区块默认折叠，初始化完成后仍需展开。
4. 渐进运动依赖采集推进；面板缺少独立运动预览入口，不等同于旧项目的连续 Play 控制。
5. Actual 角度标签主要由 CaptureRunner 的更新回调刷新，空闲直接应用命令没有立即同步该标签；读数可能让人以为没有生效。
6. 先前原生验收通过调用 panel.initialize、scene.apply_commands 和 SensorPoses.apply 验证了底层功能与数据，不是逐个点击 UI 的人工交互验收，也没有证明未初始化界面的引导足够清楚。

本次日志在脚本启动时还有 `get_update_event_stream is deprecated. Use Events 2.0` 信息，来源为诊断监听。它没有阻止面板创建，与本次 Initialize first 的直接原因不同。

Kit 日志记录过主 Viewport 销毁和重建，但没有操作来源。仅凭这条记录不能归因于 v03 脚本。静态入口与 CapturePanel 构造函数没有加载桌面布局或主动关闭主 Viewport 的调用。如果用户说的是整个 Isaac 界面/主视窗发生变化，这部分尚未建立因果证据。

## 现有版本的最小正确操作

打开目标 combine stage → 在 Script Editor 运行 v03 入口 → 点击 Initialize Current Stage → 等待 Ready → 展开对应控制区块。

直接姿态调整使用 Direct 或 Apply XYZ / Yaw；渐进/周期运动需 Start Capture 驱动。无需手动按 Timeline Play。本次排查没有替用户执行以上操作，避免改变当前场景和产生新的采集数据。

## 后续改进建议（本次未实施）

- 控制区块始终显示，未就绪时禁用并说明初始化状态；采集按钮未就绪时禁用。
- 保留明确的初始化进度、失败信息和重试入口。
- 以用户已经确认的 Play Simulation / Start Recording / Adjust LiDAR 界面为基准，统一名称、布局和操作顺序。
- 区分独立运动预览与正式采集，同时保持采集时运动—冻结—渲染的顺序。
- 在直接命令应用后同步角度和位姿显示，执行真正的按钮交互验收。

## 取证记录

本地原始摘录：`remote_readonly_evidence.json`。

cloud-instance-ops 操作 ID：

```text
20261008T082008Z_3fb2b4895bbc   当前进程、目标路径及资源状态只读检查
20261008T082133Z_b512c3f4aeea   源码哈希、最近诊断与 Kit 日志只读检查
```

这两次操作没有部署、更改服务、停止进程或运行项目。SSH 工具记录不代表整台实例的完整审计。
