# v06 完整启动与停止流程

## 1. 运行环境

远端已安装的 Isaac Sim 6.0.1-rc.7、ROS 2 Jazzy、NumPy/Pillow/rosbag2_py 继续沿用。默认网页后端为 Python 标准库 HTTP，前端为本项目 HTML/CSS/JavaScript，无 CDN。

本次未下载或安装外部依赖，未升级系统、桌面、驱动或 Isaac。不要执行 requirements-web.txt 的安装命令；这批依赖已按用户决定暂缓。

以下命令在**云端桌面的 Linux 终端**运行。先结束其他版本的采集并关闭旧脚本所在 Isaac，避免残留 RenderProduct 或同时控制同一场景。v06 不会结束其他项目的进程。

## 2. 启动网页

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06
/usr/bin/python3 run_web.py
```

保持终端打开。云端浏览器打开 `http://127.0.0.1:17875`。仅监听实例 loopback，不通过公网暴露控制接口。此时 `disconnected` 表示 Isaac 交互入口尚未启动。

需要保存网页进程日志时，可以使用 shell 重定向保存到自己的文件，避免覆盖已有日志。

## 3. 启动 Isaac 交互入口（二选一）

推荐在第二个云端桌面终端运行：

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06
/usr/bin/python3 run_capture.py --interactive --job config/interactive.json
```

自动打开 `/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_16_terrain_fisheye.usda`。等待网页状态为 `interactive_ready`。加载阶段需要时间，尚不能用键盘移动。

也可以使用已经打开的 Isaac GUI：

1. 加载同一 combine stage，确保没有运行旧版控制脚本。
2. 在 Script Editor 中打开并运行 `/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/run_in_isaac.py`。
3. 如果 Script Editor 使用文本粘贴，可运行：

```python
entry = '/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/run_in_isaac.py'
exec(compile(open(entry, encoding='utf-8').read(), entry, 'exec'))
```

不要重复点击 Run。不要同时启动独立交互入口和 Script Editor 入口，它们会争用同一控制 Socket。

## 4. 控制和轨迹

网页 **Play Simulation** 开始规定运动，**Pause** 暂停运动，**Hold Motion** 取消持续速度和自动关节运动。**Stop / Restore** 停止并恢复初始整机、关节和传感器安装位姿，控制器仍然连接，可以再次 Play。**Reset** 同样复位，但显示为暂停。复位前需结束轨迹及传感器采集，并等待排空完成。

Isaac 原生 Timeline 保持暂停，这是控制时钟的设计，不表示网页运动已暂停。以网页上“运动运行中 / 运动已暂停 / 已停止复位”的状态为准。交互动作使用独立规定运动时钟，速度上限为真实时间的 0.1 倍，视口与输入仍可高频更新。不要使用 Isaac 原生 Stop，否则可能释放 Articulation 句柄；误用或切换 Stage 后应退出控制器，再重新初始化。

### 面板参数

- XYZ 为挖掘机约定参考帧的世界位置，单位米；Yaw 为世界 Z 轴航向。
- Pitch/Roll 为相对初始整机姿态的偏移，单位度。
- 关节 Direct 立即应用目标；Target 按角速度接近目标；Periodic 在上下限间往返。超出资产限制会拒绝。
- 传感器位姿相对页面列出的父安装帧，没有继承父变换时相对世界。旋转沿用已安装 Kit 的 Euler 约定。
- Apply 是应用输入参数；上方“实际”值和命令回执用于确认应用结果。页面不会不断覆盖正在编辑的输入框。
- Read Current Base / Read Current Mount 可显式把实际状态重新填入输入框，便于丢弃草稿或在 Reset 后继续调整。

### 键盘

初始化后默认开启键控；点击网页 Play 才开始运动。网页空白区域和 Isaac 视口可接收按键；F8 切换键控。Isaac Script Editor 或其他文本框获得输入焦点时，按键用于编辑，不控制挖掘机；先点击视口。

| 操作 | 按键 |
|---|---|
| 前后、左右、升降 | W/S、A/D、R/F |
| Yaw、Pitch、Roll | Q/E、I/K、J/L |
| 大臂、小臂、铲斗 | U/O、T/G、Y/H |

网页输入框编辑时不触发移动，松键/失焦会清空键状态；网页按键心跳过期 0.5 秒也停止。使用云端浏览器窗口按键时，Isaac 窗口失焦不影响网页键控。速度以仿真秒计算，0.1x 下真实移动更慢。原生输入只处理 KEY_PRESS / KEY_REPEAT / KEY_RELEASE，CHAR 文本事件不会转成运动指令。

页面“已接收”表示指令进入队列，“已实际应用”表示 Isaac 完成该命令处理。keys 命令应用的是输入状态，实际位姿由运动更新推进；参数 motion/mount 命令则完成对应姿态操作。性能表中的回执延迟不包括屏幕显示。输入状态显示原生焦点/阻塞原因、最近按键到姿态应用延迟和错误；详细记录在 `runtime/control_events.jsonl`。

Start Trajectory 后，记录实际应用到 Articulation 的整机与关节状态。End Trajectory 等待后台排空并生成完成标记。轨迹目录为：

```text
/root/gpufree-data/semantic/output/sensor_visualizer/v06/trajectories/<时间_标识>/
  trajectory.csv
  states.jsonl
  metadata.json
```

Export ZIP 导出 CSV 与 metadata.json。修改 CSV 时保留列名、非递减时间和原始元数据；不要只上传一个无坐标/安装位姿定义的 CSV。重复时间行取最后状态，Direct 跳变不跨越插值。导入写入新目录，不覆盖原始轨迹。

## 5. 选择采集方式

### 轨迹离线重放（推荐首轮验收）

结束轨迹 → 下拉选择轨迹 → 模式选“轨迹离线重放” → 设置最多组数/仿真采样 Hz → Start Recording。

离线采集不限速，不必继续 Play；独立采集进程根据轨迹依次移动、冻结、渲染和保存。默认 10Hz 必须能整除 60Hz 物理步率。组数会裁剪到轨迹可覆盖的网格。

### 实时优先最新状态

Play → 模式选“实时采集 · 优先最新状态” → Start Recording。完成一组后取得下一个更新的源快照。预览状态可以继续改变；当前正式采集组始终冻结。慢采集时会跳过中间网格，MCAP 时间戳间隔可能不均匀。

### 实时完整轨迹网格

Play → 模式选“实时采集 · 完整轨迹网格” → Start Recording。若尚未录轨迹，会自动启动轨迹记录。采集读取轨迹文件中的完整 10Hz 网格，不静默跳样。

结束交互时点击 End Trajectory，再等采集追上最后网格；或使用 Stop + Drain 提前结束传感器采集。轨迹写入快于渲染时，会有延迟和磁盘积压。最多组数也是结束条件；达到组数时轨迹记录可能仍在继续，需要单独 End Trajectory。

### 采集中调整

网页输入仍可操作。当前组使用独立采集进程中已经固定的快照；新的运动和安装参数作用于后续源快照。若采集优先最新状态，不能保证记录每一个瞬时手动调整；需要完整记录时选择完整轨迹模式或事后离线重放。

Save Current Poses 单独保存安装位姿快照。临时调整不改磁盘 USD；关闭交互入口或 Reset 恢复初始位姿。快照不是自动回写资产。

## 6. RViz

Start Recording 前勾选“发布 ROS / RViz 预览”。第三个终端运行：

```bash
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=0
ros2 topic list
rviz2 --ros-args -p use_sim_time:=true
```

RViz Fixed Frame 选 `world` 或 `swing_coordinate`，按需增加 PointCloud2 并选择 `/lidar/<id>/points`，Reliability 选 Best Effort；每路独立勾选。添加 TF 可观察雷达及相机光学帧。

RViz 显示正式采集进程产出的组，完整轨迹模式下可能落后于交互视口。没有新组时不会持续刷新传感器话题。取消 RViz 显示不停止正式采集计算。

相机话题 `/camera/<front|back|left|right>/image_raw/compressed` 为 PNG；CameraInfo 为 equidistant 标定，完整参数另见 `/sensor_visualizer/camera_metadata`。

## 7. 停止与重复运行

1. 结束传感器采集：Stop + Drain；等待任务 `finished` 且进程退出、资源锁释放。出现 `releasing_resources` 表示仍在清理，继续等待。停止在组边界生效，正在进行的正式组可能需要十余秒。
2. 若仍在记录轨迹：End Trajectory，等待 `applied` 回执。
3. Pause / Hold Motion 停止交互运动。
4. 可以继续调参并再次采集；同一网页服务同一时刻只允许一个采集任务。
5. 退出网页服务：其终端 Ctrl+C。它不会强杀采集子进程；先执行步骤 1。
   常规停止使用 Stop / Restore，它保留控制连接。需要释放控制器时，展开“控制器退出与重新初始化”，点击 Exit Controller；界面进入已退出，Play 禁用。之后点击 Reinitialize Controller，等待完成，再 Play。两者都不会关闭 Isaac 应用本身。旧的 Close / Restore 已移除。
6. Script Editor 入口需要关闭时运行：

```python
import asyncio
asyncio.ensure_future(_sv06_runtime.close())
```

独立交互窗口可退出 Isaac；正式采集和轨迹先结束，以便完整写盘。网页服务重启可以找回已登记的 v06 任务，进程锁阻止误开第二个采集。旧测试进程如未登记，不会伪装成可管理任务。

## 8. 双 GPU

目前测试机只有一张 L40，双卡分配未运行验证。以后交互启动可用 `--gpu <GPU UUID或编号>`；网页“采集 GPU”输入另一张卡。两进程各载入一份场景，各自需要足够显存；不是自动把一个 RTX 扫描分成两卡。

查看现有卡：

```bash
nvidia-smi --query-gpu=index,uuid,name,memory.total --format=csv
```

本项目不设置 CUDA_VISIBLE_DEVICES 或升级驱动来猜测设备映射。

## 9. 性能配置与定位

默认开启精确姿态缓存、轻量状态发布，单次更新的消息预算为 2 ms。正式渲染参数、完整传感器配置保持原值。需要性能明细时改用：

```bash
/usr/bin/python3 run_capture.py --interactive --job config/interactive_diagnostic.json
```

`runs/<标识>/diagnostics/` 包含采样主线程阶段、慢帧、资源和 warning；`runtime/control_events.jsonl` 保留按键、失焦、生命周期、主线程长间隔等事件。正式采集的 diagnostics 在对应 runs 目录，MCAP session 内的 job_spec、writer_report 和 session 提供采集配置与完成状态。

查看统计时区分：frame_gap 是相邻引擎回调间隔，owner_ms 是本项目回调耗时；低 owner_ms 加上长 frame_gap 说明问题位于回调之外，不能继续归罪于控制参数处理。CPU thread_time 是线程实际 CPU 时间，墙钟时间还包括等待。资源日志整卡百分比不能直接归给某个函数。

高级采集配置 `scheduling.cooperative_yield_ms` 可设 0..100，默认 0；让步在完整组边界执行且不丢组。`yield_only_with_owner` 为 true 时只在同实例新鲜交互心跳存在时让步。它不能中断正在执行的原生渲染。`cpu_nice` 默认 0；不会设置 GPU 硬件优先级。配置实际适用性与实验结果见 performance_evidence.md。

网页启动的新采集任务从 `config/capture_policy.json` 读取 capture/scheduling/diagnostics/pipeline 策略；正在运行的任务不随文件修改而变化。交互配置则通过 `--job` 读取。原场景、传感器选择和相机画质不由该策略文件改写。

`config/throughput.json` 保留资源 keepalive 配置：活动组间实际传感器更新不会关闭，运动期间渲染的数据不保存。本轮完整配置对照中，仅采集 8 组从约 71 秒缩短到 43 秒，但并发控制 P95 比 v06 默认增大，长尾没有消除，默认仍为 gated。

若偏重离线吞吐，把 `config/capture_policy.json` 的 `capture.resource_policy` 从 `gated` 改为 `keepalive`；下一次网页启动的任务生效，既有任务不改变。完成后改回 `gated` 即可回退。保持其他画质、预热、传感器和时间配置。具体适用范围、单次对照的限制见 performance_evidence.md。

`tools/start_performance_suite.py` 为开发对照工具，默认针对 v05，启动前拒绝已有 Kit；不要把它当成用户采集入口。`tools/start_native_trace.py` 依赖已有基线和已安装 nsys，仅供有界原生诊断，profiler 会增加开销。

## 10. 回退

先 Stop + Drain 并等待采集进程退出，End Trajectory 排空，再退出 v06 交互控制器和网页服务。回到保留的旧目录即可：

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v05
/usr/bin/python3 run_web.py
```

另一个终端运行旧目录的 `/usr/bin/python3 run_capture.py --interactive`，旧网页端口为 17865，输出仍在 v05。不用复制 v06 文件回旧目录。不要同时运行两个版本控制同一个 GUI 场景。

本轮本地备份位于 `../backups/v05_performance_baseline_20261010_114432`；远端备份位于 `../backups/v05_performance_baseline_20261010T034525Z`。原 v05 校验清单在 v06/baseline_manifest.json；最终隔离检查见 reports/performance_validation.json。
