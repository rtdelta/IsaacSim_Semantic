# single0602Headless 操作指南

更新日期：2026-10-22，北京时间。适用版本：`0.5.0`。

本轮 0.5.0 在 test 实例实现与验证；capture 仍保留其原部署版本。详细结果见 [本轮验收摘要](../reports/acceptance_20261022/scene_binding_summary.json)。

0.5.0 接入说明：启动交互入口时可直接使用 `--scene /完整场景.usda`，无需新建 job。
挖机标准结构只约束机械接口，不要求任何传感器；Camera、RTX LiDAR 和预留 IMU 从整个 Stage 发现。
默认选择全部可采集设备，录制前可在网页调整；零设备可录轨迹，正式采集至少一个已支持设备。
场景固定设备保持世界位姿，普通相机与鱼眼分模型导出；设备数量和类型以实际 registry 为准。
IMU 官方探针与正式图像/点云采集分开，正式 IMU 同步仍待后续验收。
当前场景接入规则以 [换场景指南](SceneSwitchGuide.md) 和 [005 方案](../ImpPlan/005_单参数场景加载与自动绑定_实现方案.md) 为准。




0.4.0 场景编辑与跨环境采集：取消场景整文件哈希白名单，新启动按组合 Stage 的运动接口核验。
网页可选择“原场景复现”或“更换环境采集”，后者显式指定目标场景和可选平移/绕 Z 旋转，
不修改原轨迹。原场景复现仍校验已记录 USD 身份。
操作与边界见 [场景编辑与跨环境采集方案](../ImpPlan/004_场景编辑与跨环境轨迹采集_实现方案.md)。

操作顺序是：启动网页和 GUI → 录制完整轨迹 → 结束并等待排空 → 先短采 → 回读通过后采完整轨迹。默认场景和资产已经按 scene18 profile 配置。换场景应先执行 [换场景核验与操作](SceneSwitchGuide.md)，再按本指南运行。

## 1 启动前检查

确认自己连接的是本次指定的实例；具体 SSH 地址和凭据使用私有实例登记。当前 capture 与旧 test 是两个独立目标，不按旧别名中的 new 字样判断实例。

| 检查项 | 操作 |
| --- | --- |
| 运行环境 | 使用已有 Linux GPU、Isaac、ROS Jazzy 和 MCAP 插件，参见 [交付说明](DeliveryHandoff.md) |
| 场景和资产 | 默认 scene18 及其 profile、挖机与完整引用均存在 |
| 剩余空间 | 为轨迹、MCAP、日志和本次计划留出空间；先短采估算，5 组历史样例约 70 MB，不直接当所有场景的固定数据率 |
| 旧任务 | 确认没有仍在写入、排空或释放资源的任务；同一卡不并发启动多份正式采集 |
| 入口 | 独立 GUI 启动器和 Script Editor 入口二选一；首选下面的独立启动方式 |

原生启动耗时和稳态速度分开看。新机首次 GUI 启动曾超时，后续 GUI 与 Headless 验收通过；不能仅凭启动期间画面尚未出现判断脚本已经暂停了仿真。检查当前所属任务日志，不要反复启动多个 Kit 进程。

## 2 启动网页与 GUI

在远端图形桌面的第一个终端运行：

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless
/usr/bin/python3 run_web.py
```

第二个终端运行：

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless
/usr/bin/python3 run_capture.py --interactive
# 换场景时附加 --scene /root/gpufree-data/IsaacSim_Asset/combine_stage/new_scene.usda
```

远端浏览器打开 `http://127.0.0.1:17877`，等待 `interactive_ready`。网页和 Isaac 窗口要指向同一实例、同一输出目录。键控默认关闭；网页连通不等于控制器已经初始化。

若从 SSH 终端连接已有远端图形桌面，可先设置实际 DISPLAY 和 Xauthority。当前验收桌面使用：

```bash
export DISPLAY=:20
export XAUTHORITY=/root/.Xauthority
```

这些值属于当前桌面环境，新机器应先核对。Isaac 已安装在其他目录时，在第二个终端设置 `ISAACSIM_PATH`，例如 `export ISAACSIM_PATH=/opt/isaacsim`。

需要从本地浏览器访问时，另开本地终端建立转发，把下面的 HOST 和 PORT 替换成私有登记值：

```bash
ssh -N -L 17878:127.0.0.1:17877 -p PORT root@HOST
```

保持转发终端运行，再打开本地 `http://127.0.0.1:17878`。网页转发不提供三维视口，实际视口操作仍在远端桌面中进行。

Script Editor 的 `run_in_isaac.py` 使用当前已打开 Stage 和固定的 `config/interactive.json`，不会替用户选择新场景。首次交付和换场景流程优先使用独立 GUI 启动器，避免两种入口同时持有控制器。

## 3 录制一条轨迹

1. 等待 `interactive_ready`，查看实际根位姿、三个工作关节和传感器清单，确认没有 profile、零位或绑定错误。
2. 点击 **Start Trajectory**。这一步开始记录状态，不等于开始采相机和雷达。
3. 点击 **Play Simulation**，原生 Timeline 开始连续运行。
4. 勾选“挖掘机键控”，等应用回执，再点击 Isaac 三维视口取得焦点。网页空白处也可接收按键；输入框编辑时不驱动挖机。
5. 录制整机平移、转向和三个关节动作。网页输入框先编辑草稿，再点 Apply/Execute 才应用。
6. 点击 **End Trajectory**，等待排空结束及 `recording_complete=true`。看到按钮回执后仍要确认文件已完成。
7. 在轨迹列表中选中该轨迹。需要交给其他人时使用 **Export ZIP** 导出完整文件。

轨迹保存的是完整状态和控制事件。每帧位置变化、轨迹状态行数与后续采集组数是不同概念；后续采集根据轨迹时长和采样率重新选时间网格。

### 键位

| 键 | 动作 |
| --- | --- |
| W/S | 当前水平系前进/后退 |
| A/D | 当前水平系左移/右移，斜向平移归一化 |
| Z/X | 世界 Z 轴升高/降低，不自动贴地 |
| Q/E | 增加/减少整机航向，不驱动 cab–track 回转 |
| R/F | 增加/减少横滚参数偏移 |
| T/G | 增加/减少俯仰参数偏移 |
| U/J | 大臂原生关节角增加/减少 |
| I/K | 小臂原生关节角增加/减少 |
| O/L | 铲斗原生关节角增加/减少 |
| F8 | 开关键控 |

各关节正方向由资产局部轴决定，不把所有增加角度都称作抬起。界面的平移、旋转和关节变化率只控制每步位置增量，物理速度保持零。

### 按钮的不同作用

| 操作 | 仿真时间 | 挖机姿态与录制文件 |
| --- | --- | --- |
| 松键、关闭键控 | 继续推进 | 挖机保持；正在录制时继续写静止区间 |
| Hold Motion | 继续推进 | 停止当前运动目标并保持姿态；不结束轨迹 |
| Pause | 暂停 | 当前文件保留，Play 后续录同一文件 |
| End Trajectory | 不负责暂停 Timeline | 结束当前文件并排空，可以随后新建轨迹 |
| Isaac 原生 Stop 或 Stop Simulation | 停止 | 结束当前轨迹；再次 Play 等绑定恢复，再 Start Trajectory 新建文件 |
| Exit Controller | 释放交互控制器 | 先结束并排空轨迹；已启动的独立离线任务可以继续 |

失焦、暂停、开关键控、网页显式运动操作会清除旧按键。恢复时重新按下，不靠 KEY_REPEAT 恢复旧输入。

## 4 先做 3～5 组短采

1. 选择已经结束并排空的完整轨迹。
2. 在“采集范围”选择 **指定最多组数**，填写 5，采样 Hz 先用 10。
3. 单卡通常留空 GPU 选择；ROS/RViz 预览按需启用，基础回读验收可以关闭。
4. 等待计划显示预计组数和末次采样时间，再点击 **Start Recording**。这里才启动独立 Headless 相机和雷达采集。
5. 观察任务卡的计划、已采集、已写入、会话目录和完成状态。
6. 确认排空、进程退出和锁释放后，执行第 7 节的独立回读。

交互 GUI 在轨迹完成后可退出。单卡做正式采集时，退出闲置 GUI 能减少 GPU 竞争；独立采集从任务自己的轨迹快照读取，不依赖网页持续打开或交互控制器存活。

“指定最多 5 组”表示在轨迹有效网格内最多取 5 组；轨迹不足 5 个采样点时只采实际可用组数。

## 5 采集完整轨迹

短采与回读通过后，选择同一已完成轨迹，将“采集范围”切换为 **完整轨迹**，设置采样 Hz，确认计划后启动。此模式不填写组数。

默认 `physics_hz=60`，采样 Hz 必须为正、不超过 60，且 `60 / sample_hz` 是整数。例如整数 1、2、3、4、5、6、10、12、15、20、30、60 可用，7 不可用。当前监督入口按默认 60 Hz 规划；其他物理频率需要单独对齐配置与监督入口，本操作流程保持 60 Hz。

| 轨迹时长 | 采样率 | 完整计划 |
| --- | --- | --- |
| 0.2 s | 10 Hz | 3 组：0、0.1、0.2 s |
| 0.25 s | 10 Hz | 3 组，最后 0.2 s；不追加 0.25 s |
| 26.5 s | 10 Hz | 266 组 |
| 26.53 s | 10 Hz | 266 组，最后 26.5 s |

完整模式表示覆盖全部有效等间隔采样点，不表示逐条采集录制时的所有状态行，也不强行追加非网格尾帧。采样率依据仿真时间；墙钟速度取决于传感器、场景、编码和写盘负载。

### 命令行入口

先在项目目录设置实际轨迹路径，再二选一执行。变量中的路径必须是已完成轨迹目录，不是 CSV 文件：

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless
TRAJECTORY=/root/gpufree-data/semantic/output/sensor_visualizer/single0602Headless/trajectories/实际轨迹目录
```

完整轨迹：

```bash
/usr/bin/python3 run_capture.py --trajectory "$TRAJECTORY" --all-trajectory --sample-hz 10
```

最多 5 组：

```bash
/usr/bin/python3 run_capture.py --trajectory "$TRAJECTORY" --groups 5 --sample-hz 10
```

`--all-trajectory` 与 `--groups` 互斥；两者都省略时保留旧 CLI 行为，最多 100 组，不等于完整轨迹。启动命令返回 task ID 后正常结束，独立子进程继续运行。

轨迹必须位于本次输出根下。其他来源使用网页 Import 导入；优先使用完整 ZIP，避免手工拆开 CSV 和 metadata。换过输出根时，网页的 `--output`、交互 job 的 `output_directory` 与采集 CLI 的 `--output` 必须一致。

## 6 暂停与停止采集

| 操作 | 结果 |
| --- | --- |
| Pause Capture | 在安全边界停止推进，等待当前组和写入边界完成；组数不会凭点击瞬间立刻变化 |
| Resume | 在同一任务内继续，不新建轨迹 |
| Stop + Drain | 提前结束本次任务，把已经接受的数据排空保存 |

完整完成应同时满足：

- `state=finished`、`completion_reason=completed_plan`，采集数和写入数均等于计划数。
- `capture_complete=true`、`record_drain_complete=true`。
- `process_exited=true`、`resource_lock_released=true`，退出码为 0。

提前 Stop + Drain 可以成功保存部分数据，此时 `completion_reason=stopped_by_user`、`capture_complete=false`。保存成功不能标记成完整轨迹已采完。

等待资源锁释放再开始下一任务。不要手工删除 `capture.lock` 或 socket 来绕过活动进程；不同输出目录的锁也不能用来保证同一卡上的全局互斥。

## 7 回读与找文件

任务卡给出的 `session` 是采集会话目录；`tasks/<task_id>/` 是任务控制目录，两者不同。

```text
输出根/
├── trajectories/<trajectory_id>/
├── imports/<import_id>/
├── tasks/<task_id>/
│   ├── job.json
│   ├── trajectory/
│   ├── task.json
│   ├── status.json
│   ├── control.json                 按控制操作生成
│   └── kit.log
├── <capture_session>/
│   ├── bag_unified/                 MCAP 与 metadata.yaml
│   ├── job_spec.json
│   ├── sensor_registry.json
│   ├── render_profile.json
│   ├── asset_manifest.json
│   ├── trajectory_metadata.json
│   └── writer_report.json
├── pose_adjustments/
└── runtime/
```

先加载系统 ROS 环境，再读取实际会话：

```bash
source /opt/ros/jazzy/setup.bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless
SESSION=/实际采集会话目录
/usr/bin/python3 tools/validate_capture_data.py "$SESSION"
```

通过时输出 `VALIDATION_JSON=`，其中 `passed=true`，命令退出码为 0。工具验证 MCAP/CDR、PNG 解码、图像尺寸、标定、话题计数、消息摘要、TF、swing 零位和源轨迹一致性。

完整回读还会访问 `job_spec.json` 中的任务私有轨迹和 `asset_manifest.json` 中的源 USD。因此复制样例时同时保留任务轨迹快照和对应资产路径；仅拷贝一个 MCAP 到新目录不足以运行所有身份检查。

程序逻辑检查：

```bash
/usr/bin/python3 -m unittest discover -s tests -v
```

逻辑测试通过不替代新资产的加载、实际按键和短采回读。

## 8 安装位姿调整

选择传感器后先 Read Current Mount，核对其父节点和编辑坐标，再 Apply Mount。默认调整在匿名会话层中进行。**Save Current Poses** 把快照和日志写到输出根的 `pose_adjustments/`，不保存源 USD，也不保证下一次启动自动加载该快照。

轨迹保存安装 revision，离线任务按录制时的安装状态重放。不能录完后换一套安装配置，再把旧轨迹解释为新安装采集结果。新场景使用独立输出根，可以避免把不同资产的安装日志混在一起。

若界面提示挂载节点是实例代理、刚体或复杂/动画变换栈，先在资产中提供独立可编辑的安装 Xform，再重新核验；不要为了调整传感器直接移动承载它的挖机刚体。

## 9 常见问题

| 现象 | 先检查什么 | 操作 |
| --- | --- | --- |
| 网页“等待连接” | 网页所在实例、输出根、`engine.sock`、GUI 日志 | 只启动一份正确入口，等 `interactive_ready` |
| profile 报错 | 选定运动 profile、关节框架、`angleZero` 与实际传感器接口 | 按换场景清单重新核验，不关闭校验 |
| 开键控没有动作 | 是否 Play、回执是否应用、应用与视口焦点、输入框是否占焦点 | 点视口后松开并重新按键 |
| 关闭键控后挖机不动 | Timeline 与仿真时间是否继续 | 保持姿态是预期；要移动需新命令 |
| 原生 Stop 后旧录制不能续写 | 当前轨迹是否已结束、绑定是否恢复 | 再 Play，等绑定完成，再 Start Trajectory 新建文件 |
| 采集按钮不可用 | 轨迹是否完整、Hz 是否有效、计划是否算完、上一锁是否释放 | 修正前置条件后再启动 |
| CLI 很快退出 | 是否已返回 task ID | 查看网页任务卡及 `tasks/<id>/status.json` 和 `kit.log` |
| 帧率或采集慢 | GUI 稳态倍率、启动耗时、墙钟每组耗时和资源竞争 | 分开记录，先用短采确认；不恢复旧 0.1× 限制 |
| 缺相机或雷达 | USD 路径、active/loaded、鱼眼属性、Instant LiDAR 和材质引用 | 由资产维护人修正初始场景并重启 |
| DomeLight 报错 | 默认 Fangshan 灯是否仍存在、是否可见、有无多个背景灯 | 使用新 job 的实际 `render.background_dome`；`null` 时最多一个可见 DomeLight |
| 回读报路径不存在 | 任务轨迹快照、USD 和会话 JSON 是否配套 | 恢复原路径或执行明确的路径适配流程 |

## 10 结束与下一轮

结束轨迹并等排空；正在采集时等计划完成，或 Stop + Drain 后等退出和锁释放；再 Exit Controller 并正常关闭本轮 GUI、网页终端。只结束本轮所属进程，不按 `python` 或 `kit` 的宽泛名称批量停止。

同一场景下一轮可以重新启动并新录制。换场景或挖机时，按 [换场景核验与操作](SceneSwitchGuide.md) 准备新组合、新输出和新轨迹，重新运行全部流程。
