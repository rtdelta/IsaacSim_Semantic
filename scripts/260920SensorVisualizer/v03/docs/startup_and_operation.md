# Sensor Visualizer v03 完整启动与运行流程

适用版本：2026-10-08 已部署并完成 GUI、无窗口采集验收的 v03。以下 Bash 命令在**云端电脑的终端**执行；Script Editor 中的 Python 代码在**云端 Isaac Sim** 中执行。

## 1. 路径与运行方式

| 内容 | 路径 |
|---|---|
| 云端项目 | `/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v03` |
| 默认场景 | `/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_16_terrain_fisheye.usda` |
| 默认采集输出根目录 | `/root/gpufree-data/semantic/output/sensor_visualizer/v03` |
| 本地源码项目 | `D:\learning\IntelligentDepartment\CodesSet\Self\260707IsaacSIm\scripts\260920SensorVisualizer\v03` |

有两种使用方式：

- **GUI 调整与采集**：启动 Isaac → 打开场景 → Script Editor 打开 v03 面板 → 初始化 → 调整 → 开始采集。需要实时看点云时另开 RViz。
- **无窗口离线采集**：运行 `run_capture.py --job ...`，脚本自动打开场景、初始化、按配置采集、关闭录制进程并退出 Isaac。

一次使用一种方式，避免同时运行多个采集控制器。项目沿用已安装的 Isaac 和 ROS 2 Jazzy 环境，使用 `/usr/bin/python3` 启动。正常运行不需要安装新依赖，也不需要另开一个 rosbag 录制脚本。

## 2. 启动 Isaac GUI

进入云端网页远程桌面，打开桌面终端：

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v03
/usr/bin/python3 run_capture.py --gui
```

等待 Isaac 窗口打开。该命令只启动 GUI，不自动打开采集面板，也不开始录制。

如果已经有打开的 Isaac，可在其中使用后续 Script Editor 流程，不必再启动一份。上一轮的采集面板应先完成停止和关闭。

通过 SSH 启动 GUI 时需要有效的桌面 DISPLAY；上次验收使用的是 `:20`。日常操作推荐从网页桌面的终端启动，直接继承桌面环境。

## 3. 打开场景和 v03 面板

在 Isaac 中打开：

```text
/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_16_terrain_fisheye.usda
```

等待场景加载完成。当前默认场景验收时发现了 4 路鱼眼相机和 13 路 Instant LiDAR；如果你后来修改过场景，实际数量以初始化后的面板为准。

打开 Script Editor，粘贴并运行：

```python
from pathlib import Path

p = Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v03/run_in_isaac.py')
exec(compile(p.read_text(encoding='utf-8'), str(p), 'exec'))
```

出现 **Sensor Visualizer v03** 面板。不要手动按 Isaac Timeline 的 Play，v03 会控制运动、暂停和渲染时序。

## 4. 初始化前设置采集参数

第一次建议先采 3 组，确认输出后再增加组数。

| 面板项 | 含义与建议 |
|---|---|
| `Groups` | 本次采集组数；首次填 `3`，默认是 `100` |
| `Hz` | 按仿真时间计的采样频率；默认 `10`，修改后需要重新初始化 |
| `Interactive <=0.1x` | 交互模式，仿真推进速度上限为真实时间的 0.1 倍；实际负载可能让它更慢 |
| `Offline unrestricted` | 离线模式，不加 0.1 倍速节拍限制，仍受实际渲染耗时约束 |
| `ROS preview` | 勾选后，采集期间向 ROS 发布数据，供 RViz 订阅；GUI 默认勾选 |
| `LiDAR IDs` | 留空自动选择全部雷达；指定多个 ID 时用英文逗号分隔 |
| `Camera IDs` | 留空选择全部四相机；可填 `front,back,left,right` 或其中一部分 |

“一组”表示同一冻结姿态和时间戳下的一套数据。当前全选时，一组包含 4 张相机图像、13 路点云，以及 TF、时钟、关节状态等信息。`10 Hz` 不代表真实时间每秒能录到 10 组。

频率必须能整除默认 60 Hz 物理步频，例如 5、10、15、20、30。当前只支持 Instant LiDAR。雷达 ID 来自场景自动发现，不需要修改源码；初始化后的注册表包含实际 ID 和话题。

如果要恢复此前保存的任务，先在 `Job JSON` 中填完整路径，点击 **Load Job (before Init)**，然后打开该任务对应的场景。载入任务不会替你在 GUI 中切换场景。如果已经 Initialize，需要 **Close / Restore**、重新打开面板后再 Load Job。

## 5. 初始化

点击 **Initialize Current Stage**，等待状态变成：

```text
Ready. Start Capture; timeline is controlled automatically.
```

初始化会发现传感器、准备关节与运动控制、创建渲染产品、完成预热。上次全传感器测试约需 35 秒；这一阶段没有正式录制采集组。

初始化后展开运动、整机和雷达安装位姿控制区域。空闲时相机和雷达采集产品的更新关闭，Isaac 视口仍可继续显示场景。

## 6. 调整运动与雷达位姿

### 6.1 关节、整机 Pitch / Roll

在 **Joints and body tilt (degrees; speed degrees/s)** 中，为每个关节或倾斜轴选择模式，填参数，再点击该行 **Apply**。

| 模式 | 需要填写 | 行为 |
|---|---|---|
| `Direct` | `Target` | 直接跳到目标角度 |
| `Target + speed` | `Target`、`Speed` | 以指定角速度逐步接近目标 |
| `Periodic` | `Lower`、`Upper`、`Speed` | 在上下限之间往返运动 |

角度单位为度，速度为度/仿真秒。角度以面板的 `Actual` 和显示的关节限位为准。Periodic 的 Lower 必须小于 Upper，速度必须大于 0。点击 **Hold** 保持该关节或倾斜轴的当前角度。cab–track 连接保持初始角度。

Target 和 Periodic 在仿真推进阶段更新；面板空闲或采集暂停时不会自行连续运动。第一组记录当前姿态，后续组之间才按采样间隔推进运动。

### 6.2 整机位置与转向

展开 **Whole machine: world position / yaw / velocity**。

- 输入 `x/y/z`（米）和 `yaw`（度），点击 **Apply XYZ / Yaw**，设置整机位置和转向。
- 输入 `m/s` 和 `deg/s`，点击 **Start Velocity**，设置向前/向后移动与转向速度。正负速度可用于反向运动。
- 点击 **Hold Base**，停止整机平移和 Yaw 速度。

这里的位置是世界坐标。Z 高度可以手动调节；当前不会自动贴地或依据地形接触调整高度。整机 Pitch / Roll 使用上一节的独立倾斜控制。

### 6.3 雷达安装位置和旋转

展开 **LiDAR mounts: parent-local pose**：

1. 在下拉框选择雷达 ID。
2. 修改 `X/Y/Z`（米）和 `RX/RY/RZ`（度）。
3. 点击 **Apply at Next Boundary**。
4. 满意后点击 **Save Current Poses**，保存所有选中雷达的当前位姿快照。

位置按安装节点的父坐标系表达，旋转沿用 Kit Euler 约定。特殊世界参考情况以快照中的 `reference` 字段为准。当前面板提供的是雷达安装编辑，没有四相机安装位姿编辑控件。

采集空闲时调整立即应用；采集正在运行时排队到安全边界应用。若希望看清修改效果，可先 **Pause**，等面板显示 `paused`，再调整、保存，最后 **Resume**。下一组会完成安装变更的同步/预热，再发布新数据。

**Reset Mounts** 恢复本次初始化时的雷达安装位置。调整是临时 Session 改动，不会自动改写磁盘 USD。

### 6.4 保存供下次使用的任务

在 `Job JSON` 中指定保存路径，例如：

```text
/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v03/config/saved_job.json
```

点击 **Save Job**。该文件保存当前场景、采集配置、关节/整机控制状态、当前初始角度和雷达安装位姿，可供下次 Load Job 或无窗口采集使用。Save Job 生成的是离线任务配置。

**Save Current Poses** 保存位姿快照；**Save Job** 保存可直接用于本项目运行的任务 JSON。位姿快照不是同一种 Job JSON，不能直接传给 `run_capture.py --job`。

如果需要保留临时调整，务必在本次采集结束或 Stop 前保存；正常完成采集也会恢复初始运动和雷达安装位姿。

## 7. 开始采集

确认组数、模式和 `ROS preview` 设置后，点击 **Start Capture**。

面板自动完成采集与 MCAP 录制，不需要再运行第二个录制脚本。状态会显示阶段、`acquired`、`written`、等待的传感器以及本次输出目录。

每组执行顺序为：

```text
等待可用缓冲槽
→ 推进运动到下一采样位置（第一组使用当前位置）
→ 暂停仿真，固定机器人和传感器位姿
→ 相机预热
→ 正式渲染与数据就绪等待
→ 读取、复制并校验同组图像/点云/位姿/时间
→ 关闭传感器更新
→ 后台并行编码图像、有序写入 MCAP
```

背景编码和写盘可与下一组采集重叠。读取失败或来源时间/位姿不一致的组不会被当作有效完整组保存。

上次 4 相机 + 13 雷达的静止采集约为 12.3 秒/组，3 组约 37 秒，初始化另计。这是短时测试参考，实际耗时取决于场景与负载。图像和点云准备期间状态更新可能较慢；看到 `acquired` 领先 `written` 表示后台仍在写包。

## 8. 在 RViz 中查看实时点云与传感器位置

保持采集运行，并确保**在 Start Capture 之前**勾选了 `ROS preview`。采集中才修改该复选框不会直接重建当前录制进程；需要结束本次采集、按新设置再次开始。

在云端桌面另开一个终端，进入项目：

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v03
```

复制面板显示的本次输出目录，将下面引号中的占位路径替换成实际路径：

```bash
SV_SESSION='/root/gpufree-data/semantic/output/sensor_visualizer/v03/本次采集目录'
/usr/bin/python3 launch_rviz.py --session "$SV_SESSION" --domain 0
```

`--session` 指向包含 `sensor_registry.json` 的采集目录，不能指向 `bag_unified` 或 `runs/<run_id>`。运行一次 Start Capture 后注册表才会生成。

启动器自动生成：

- `Fixed Frame: world`。
- 每路雷达对应一个 **PointCloud2** 显示项，话题为 `/lidar/<雷达ID>/points`。
- **Sensor Poses**（TF）显示项，显示雷达、相机的坐标轴及名称。
- 使用仿真时钟，点云订阅使用 Best Effort。

在 RViz 左侧勾选/取消勾选某路 PointCloud2，即可控制显示。取消勾选只改变 RViz 显示，不停止该雷达的采集。若要减少采集负载，应在面板中选择较少的 LiDAR IDs 并重新 Initialize。

TF 链路为 `world → swing_horizontal_coordinate → swing_coordinate → 各传感器坐标系`，传感器相对挖掘机根参考系表达，同时具备世界坐标关系。

RViz 默认配置显示点云和 TF，没有自动添加相机图像窗口或挖掘机 3DGS 模型。鱼眼图像已录入 MCAP，可按第 11 节解码检查。

默认 ROS Domain 为 0。使用自定义 Job 时，如果 `preview.ros_domain_id` 已改变，RViz 的 `--domain` 要填相同值。预览真实时间更新频率上限为 5 Hz，但实际只在完整采集组写入后发布；采一组耗时十余秒时，RViz 同样按这个节奏刷新。

## 9. 暂停、结束与再次采集

| 操作 | 使用方法 |
|---|---|
| 暂停 | 点击 **Pause**，等待当前组完成并显示 `paused`；此时姿态保留，传感器更新关闭 |
| 继续 | 点击 **Resume**，从下一组继续推进运动与采集 |
| 提前结束 | 点击 **Stop + Drain**，等待 `finished`，后台写包完成后恢复初始位姿 |
| 达到组数 | 自动完成并 drain，显示 `finished`，恢复初始位姿 |
| 再采一轮 | 在就绪面板中重新调整运动/安装位置、组数，点击 **Start Capture**；生成新的采集目录 |
| 更改频率或传感器选择 | 先结束采集，再点击 **Initialize Current Stage**；重新初始化会恢复之前的临时调整，按需提前保存 |
| 全部结束 | `finished` 后点击 **Close / Restore**，释放产品、恢复 Session 层和设置，再关闭 Isaac/RViz |

当前 v03 的 Pause/Stop 管理整套采集，不需要执行旧版的“Stop Recording 再 Pause Simulation”。不要用手动 Timeline 操作代替这些按钮。

关闭面板窗口也会触发关闭与停止流程，因此需要保留的安装位姿/Job 应先保存。若出现采集失败或场景被替换，状态会提示重新初始化；先处理错误，再 Initialize。

## 10. 无窗口离线运行

结束并退出 GUI 采集后，在云端终端使用：

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v03

# 首次小样本：前鱼眼相机 + 自动发现的全部 Instant 雷达，3 组
/usr/bin/python3 run_capture.py --job config/smoke.json
```

任务会自动加载默认场景、初始化、录制三组，关闭写包和 Isaac 后退出。终端打印 `[SV03 RESULT]` 后的路径是本次采集目录。

其他任务按需选择一条命令：

```bash
# 四相机 + 全雷达，10 组，详细诊断与时间线
/usr/bin/python3 run_capture.py --job config/diagnostic.json

# 四相机 + 全雷达，100 组，10 Hz 仿真采样
/usr/bin/python3 run_capture.py --job config/offline.json

# 使用 GUI 中通过 Save Job 实际生成的任务
/usr/bin/python3 run_capture.py --job config/saved_job.json
```

这三条是备选任务，按需要执行，不必依次全部运行。`saved_job.json` 必须已经保存；默认 Job JSON 字段指向这个路径不代表文件已经存在。

无窗口任务按配置组数自动结束，没有交互面板的 Pause/Stop。需要随时手动暂停和正常提前停止时，使用 GUI 模式；首次离线任务先用有限组数，不要依赖强制终止进程完成写包。

默认 CLI 配置的 ROS preview 为关闭，结束后可回放包。GUI 保存的 Job 可能包含启用预览的配置，应以其 `preview.enabled` 和 `preview.ros_domain_id` 为准。

## 11. 检查输出与解码图像

在云端终端设置实际采集目录，后续命令沿用这个变量：

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v03
SV_SESSION='/root/gpufree-data/semantic/output/sensor_visualizer/v03/本次采集目录'
```

本次目录的主要内容：

```text
<采集目录>/
  session.json                 本轮状态、完整组数、停止与错误信息
  job_spec.json                实际任务配置
  sensor_registry.json         传感器 ID、USD 路径、话题、相机标定
  mount_poses_at_start.json     采集开始时的雷达安装位姿
  capture_index.jsonl           写入组的索引
  writer_report.json           写包结果、话题计数、载荷摘要、编码/写入统计
  record_worker.log            录制进程日志
  diagnostics_ref.json         对应运行诊断目录
  render_profile.json          渲染请求与实际设置
  asset_manifest.json          场景及资产记录
  performance/summary.json     常用阶段耗时
  bag_unified/
    metadata.yaml
    *.mcap                     一个或多个分段
```

查看状态：

```bash
/usr/bin/python3 -m json.tool "$SV_SESSION/session.json"
/usr/bin/python3 -m json.tool "$SV_SESSION/writer_report.json"
```

确认 `session.json` 的 `state` 为 `finished`，`complete_groups` 与预期一致；提前 Stop 时允许少于 requested_groups。后台 `writer_report.json` 也应为 `finished`，组数匹配。

校验并导出样图：

```bash
source /opt/ros/jazzy/setup.bash
/usr/bin/python3 tools/validate_capture.py "$SV_SESSION" --export-images
```

成功时打印 `passed: true`，生成 `validation_report.json`。`validation_images/` 保存每路相机的**第一张**解码 PNG，用于检查，不是全部图像的批量解包。

MCAP 内主要话题：

| 话题 | 内容 |
|---|---|
| `/clock` | 仿真时钟 |
| `/tf` | 世界、挖掘机根参考系和传感器的 TF |
| `/joint_states` | 关节状态 |
| `/excavator/root_pose` | 挖掘机根参考位姿 |
| `/lidar/<ID>/points` | 各雷达的 PointCloud2，XYZ 为传感器局部坐标 |
| `/camera/<ID>/image_raw/compressed` | 鱼眼 RGB PNG |
| `/camera/<ID>/camera_info` | 相机尺寸、内参、畸变参数 |
| `/camera/<ID>/pose` | 相机光学坐标系在世界中的位姿 |
| `/sensor_visualizer/frame_index` | 本组身份、来源时间、位姿与校验信息 |
| `/sensor_visualizer/run_metadata`、`camera_metadata` | 运行配置和相机元数据 |

复制或归档 ROS 2 bag 时保留整个 `bag_unified`，包括 metadata.yaml 和所有 MCAP 分段。

## 12. 离线回放给 RViz

结束实时采集后，在桌面终端 A 按第 8 节启动 RViz，`--session` 指向要回放的采集目录。

在云端终端 B：

```bash
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=0
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
SV_SESSION='/root/gpufree-data/semantic/output/sensor_visualizer/v03/本次采集目录'
ros2 bag info "$SV_SESSION/bag_unified"
ros2 bag play "$SV_SESSION/bag_unified"
```

包中已经有 `/clock`，直接回放即可。RViz 使用仿真时间。回放时关闭实时采集的 ROS preview，避免同一话题出现两个数据来源。回放的默认节奏按包内仿真时间，通常会比原来十余秒一组的实际采集快很多。

## 13. 查看安装位姿记录与性能日志

雷达调整日志和手动快照在默认输出根目录下：

```text
/root/gpufree-data/semantic/output/sensor_visualizer/v03/
  pose_adjustments/<初始化时间_编号>/
    pose_changes.jsonl
    poses_<保存时间>.json
```

`pose_changes.jsonl` 包含调整请求、调整前后值、仿真时间、revision 和重置记录。`poses_*.json` 是 Save Current Poses 的结果。如果 Job 修改了 output_directory，相应记录也在该输出根目录下。

性能诊断从本次 `diagnostics_ref.json` 获取：

```bash
SV_DIAG=$(/usr/bin/python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["directory"])' "$SV_SESSION/diagnostics_ref.json")
/usr/bin/python3 tools/analyze_trace.py "$SV_DIAG" --trace
```

生成 `analysis.json` 和 `trace.json`。运行日志主要包括：

- `events_isaac_*.jsonl`：初始化、运动、渲染、回调、数据读回与控制请求。
- `events_writer_*.jsonl`：PNG 编码、CDR、MCAP 写入与收尾。
- `resources_*.jsonl`：CPU、内存、GPU 和资源配额采样。
- `warnings*.json`：聚合 Warning；`warnings_*.jsonl`：样例及阶段关联。
- `summary*.json`：计数、日志丢失与 I/O 错误。

日志阶段耗时包括原生/GPU 等待，不能直接当作 GPU kernel 时间。当前 Hydra 已释放接口 Warning 仍存在，完整问题与实测性能见 [部署与原生测试报告](deployment_and_native_test.md)。

## 14. 常见卡点

| 情况 | 处理 |
|---|---|
| 运行 `--gui` 后没有 v03 面板 | 打开场景并在 Script Editor 执行第 3 节入口 |
| 填了 Job 路径但没有载入 | 需在初始化前点击 Load Job；默认 saved_job.json 不一定存在 |
| 改了 Target/Speed 但关节不运动 | 点击该行 Apply；渐变/周期运动需要 Start Capture 推进仿真时间 |
| 修改位姿后按钮显示 Queued | 等当前组结束或进入 paused 后，命令才在安全边界应用 |
| 采集时界面长时间不更新 | 原生渲染可能阻塞，检查阶段、计数和日志；当前全负载约十余秒一组 |
| RViz 没有点云 | 检查 preview 是否在采集开始前启用、是否已经产生完整组、Domain 是否一致、session 是否正确、是否仍在采集 |
| RViz 某路缺失 | 检查面板选择、sensor_registry.json 和该 PointCloud2 的 topic/勾选状态 |
| 停止后位姿回到原来 | 这是本版设计；下次沿用需要停止前 Save Job 或 Save Current Poses |
| 改 Hz 后 Start Capture 提示重新初始化 | 先结束采集，再 Initialize；频率和产品选择需重新建立 |
| CLI 显示 `[SV03 RESULT]` 但状态为 failed | RESULT 表示输出位置；成功以 session.json、退出状态和校验结果为准 |

日常最短顺序：**启动 GUI → 打开场景 → Script Editor 运行入口 → Initialize → 设置并 Apply → Start Capture → 另开 RViz → 保存需要保留的调整 → Stop + Drain → 校验输出 → Close / Restore**。
