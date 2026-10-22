# Excavator LiDAR Visualizer

在 Isaac Sim GUI 中自动识别当前场景的挖掘机，控制或观察机构状态，发布实际已加载的 RTX LiDAR（当前场景 13 路）、四关节角、根位姿、TF 和时钟，并录制 MCAP。目标环境：远端 Isaac Sim 6.0.1-rc.7、Ubuntu 24.04、ROS 2 Jazzy。

## 启动

项目远端目录：`/root/gpufree-data/semantic/scripts/260907LidarVisualizer`。

1. 用本项目 `LidarVisualizer.desktop` 打开原生 Isaac GUI，或在远端图形桌面终端执行下面的 Python 入口。启动器直接执行 Kit，不需要 sh 脚本：

   ```bash
   /usr/bin/python3 /root/gpufree-data/semantic/scripts/260907LidarVisualizer/launch_isaac.py
   ```

2. 在 Isaac 打开所需 USD，例如 `combine_scene_11.usda` 或 `combine_scene_08.usda`，等待 Payload 载入。在 **Window → Script Editor** 打开项目的 `run_in_isaac.py` 并 Run；或执行：

   ```python
   from pathlib import Path
   entry = Path('/root/gpufree-data/semantic/scripts/260907LidarVisualizer/run_in_isaac.py')
   exec(compile(entry.read_text(encoding='utf-8'), str(entry), 'exec'))
   ```

3. **Excavator Connection** 显示当前 Stage、候选挖掘机和模式。唯一已知四关节机构自动连接；多个候选或未知命名需要选中后点击 **Connect / Apply mode**。切换 Stage 后重新识别，手动加载 Payload 后可点 **Rescan current stage**。
4. **LiDAR Visualizer** 显示实际传感器列表。点击 **Play Simulation** 开始采样。只修改目标数字不会启动关节；需要显式 Apply/Start。
5. 同机 RViz 可通过 `/usr/bin/python3 /root/gpufree-data/semantic/scripts/260907LidarVisualizer/launch_rviz.py` 打开，使用本次生成的配置。

桌面入口会自动运行 Script Editor 入口；空场景时连接面板等待打开资产。已有 GUI 若启动参数兼容，可以直接重跑 `run_in_isaac.py`，无需重启。更新前的源文件保留在 `backups/auto_stage_20260915_*`。

## 两种模式

| 项目 | Scripted control + publish（默认） | Observe + publish |
|---|---|---|
| 四关节角、根位姿、点云、TF、Clock | 发布实际读回值 | 发布实际读回值 |
| 大臂、小臂、铲斗控制 | Direct / Target + speed / Periodic / Hold | 不写入运动状态 |
| 回转关节 | 保持开始时角度，不提供回转控制 | 读取外部控制产生的实际角度 |
| 整机根位姿 | 默认保持初始位姿 | 跟随物理或外部控制的实际位姿 |
| 世界固定关节、关节驱动 | 暂时解除世界固定约束并抑制角驱动，避免与直接写状态竞争 | 保留原设置 |
| 重力、碰撞 | 运行 Session 层临时关闭 | 保留原设置 |

切换到 Scripted 需要 Stop 并重新建立物理视图，会恢复启动姿态。Observe 本身不调用根位姿、关节位置或速度设置接口。两种模式仍管理本工具的传感器发布、参考坐标和仿真节拍；用户主动使用安装调整功能时，才修改传感器临时位姿。

禁用的是“世界固定住履带”的固定约束，不是禁用四个转动关节。关闭连接面板会结束录制、释放本工具资源并恢复临时覆盖。仅关闭 LiDAR 窗口也会释放本次运行，连接管理器仍可用于重连。

## 自动识别与角度规则

识别依据是 `ArticulationRootAPI` 及 RevoluteJoint 的 `body0/body1` 链，支持五个刚体在 USD 中为同级节点。当前要求无分支、四个启用的转动关节；任意四轴机构不会仅凭关节数量被自动认定为挖掘机。

| 语义及消息数组索引 | 05 资产命名 | 03 资产命名 |
|---|---|---|
| 回转 / 0 | swing | track_operator_cab_joint |
| 大臂 / 1 | boom | platform_boom_joint |
| 小臂 / 2 | arm | boom_small_arm_joint |
| 铲斗 / 3 | bucket | small_arm_bucket_joint |

这些是角色映射，不是角度换算。保留每个资产自己的关节零点、正方向、限位和启动姿态；03 的角度不会自动换成 URDF 规则。05 在 stage11 中启动仍是约 `[0, 38, -106, -5.8741578]` 度的折叠姿态，不强制四关节清零。

自动传感器模式只绑定选定挖掘机下已加载、启用的 OmniLidar。保留安装父子层级和位姿，包括 MyOS0_up。未加载 Payload、非 OmniLidar 类型和机构外传感器需要另行配置。解析结果保存在 `generated/sensors.json`；切换 Stage 后重启外部 RViz 可刷新显示清单。

## ROS 2 接口与画图

| 话题 | 消息类型 | 内容 |
|---|---|---|
| `/joint_states` | `sensor_msgs/msg/JointState` | 四个实际 DOF 的 name 和 position，单位 rad；velocity、effort 留空 |
| `/excavator/root_pose` | `geometry_msgs/msg/PoseStamped` | world 中的根位置（m）和归一化四元数（x,y,z,w） |
| `/tf` | `tf2_msgs/msg/TFMessage` | world → swing_horizontal_coordinate → swing_coordinate → 各实际感知节点 |
| `/clock` | `rosgraph_msgs/msg/Clock` | 仿真时钟 |
| `/lidar/<id>/points` | `sensor_msgs/msg/PointCloud2` | 各雷达 SENSOR 坐标点云 |

`swing_coordinate` 初始与挖掘机模型容器对齐，之后跟随真实履带根刚体，业务上近似上车参考系，不加入 cab 回转角。水平系与它同原点，保留前向水平投影航向、Z 轴始终向上。PoseStamped 表示 swing 在 world 中的完整位姿。新资产、场景及操作方法见 [ORIGIN03_HORIZONTAL.md](ORIGIN03_HORIZONTAL.md)。

关节状态和根位姿同次采样、同一仿真时间戳。默认状态频率 60 Hz（仿真时间），QoS reliable / volatile / keep_last / depth 20。GUI 关节显示度数；ROS 保持弧度。画图时选择 `/joint_states/position[0]` 至 `[3]`，先确认 `name` 数组；根姿态可画 `/excavator/root_pose/pose/orientation/x`、y、z、w。若要直观的 yaw/pitch/roll，在消费端将四元数转换为角度；本版不另发欧拉角话题。

当前脚本控制不会主动旋转底盘，因而根四元数保持不变是正常结果。Observe 中外部控制改变底盘位置或方向时，消息跟随实际状态。

## 节拍、控制与录制

- 仿真步长 1/60 秒，`max_real_time_factor=0.1`，实际主循环上限约 6 FPS；状态 60 Hz 仿真时间对应上限约 6 Hz 真实时间。负载高时允许更慢，不追赶补帧。
- 雷达按资产的原生 scanRateBaseHz 和完整扫描发布，当前场景为 10 Hz 仿真时间。限频不意味着 RTX 内部计算次数等比例降低。
- Target + speed 和 Periodic 的速度单位为度/仿真秒；Direct 在初始化后的暂停状态也能 Apply。Hold 停止相应关节，Pause 冻结仿真，Stop 恢复启动姿态并清除运行中的关节命令。
- 选中需要录制的雷达后点击 Start Recording。每次 MCAP 除选中点云外，还记录 TF、Clock、四关节状态和根位姿；状态开关关闭时不录制这两个新话题。
- `session.json` 记录当前 Stage、绑定路径、语义映射、原生角度约定、单位、模式和采样配置。Stop、时间倒退、切换模式/Stage 或重跑入口会结束当前录制，需要重新点击 Start Recording。
- Pause 可以保留录制；Stop Recording 等待独立 ROS 录制进程完成写盘。回放前先关闭同名实时发布源，使用包内已录制的 Clock。

## 场景资源与兼容边界

Stage10BaseAnchor 和 Stage10SensorPipeline 均不需要从 USD 中删除。Scripted 临时覆盖固定约束；本工具临时停用已持久化的同传感器雷达 Render Product 及其创建节点，再建立自己拥有的发布链，退出后移除覆盖。摄像机分支保持原有设置；不删除其他工具创建的匿名 Render Product。

图 `/LidarVisualizer` 和参考节点 `/LidarVisualizerFrames` 写入可移除 Session 层。本工具不保存源 USD，不改变资产尺寸、零点、安装层级或物理参数文件。运行中不要把临时组合结果 Flatten 为正式资产。

当前预发布渲染器的 3DGS 与 Motion BVH 不兼容。Python 启动器配置必要的 ROS/RTX 库并关闭 Motion BVH、Multi-tick、perSensorTickTlas；这是逐帧兼容运行，未实现扫描期间的逐点运动去畸变。若其他程序同时向相同 ROS 话题或 TF child frame 发布，请关闭重复发布源或分配不同 ROS Domain。

## 文件与验证

- `run_in_isaac.py` / `session.py`：入口重跑、GUI 选择与场景切换。
- `robot_discovery.py`：依据刚体关节关系发现和绑定机构。
- `articulation_motion.py`：实际读回、脚本控制、运行根坐标与复位。
- `state_publication.py`：同帧 JointState / PoseStamped 发布。
- `render_lease.py`：场景雷达 Render Product 的临时停用与恢复。
- `runtime.py` / `cloud_rate.py`：TF、时钟、点云、GUI 与资源清理。
- `recording.py`：独立 ROS 录制进程和元数据。
- `config/sensors.json`：默认模式、话题、频率及 ROS Domain。
- `validation/test_auto_stage.py`、`validate_auto_stage_isaac.py`、`verify_state_bag.py`：纯逻辑、远端集成及实际 MCAP 消息验证。

完整验证范围及结果见 `VALIDATION.md`。历史文档和代码保留在升级备份目录中。
