# single0602Headless 换场景核验与操作

更新日期：2026-10-22（北京时间）。适用版本：0.5.0。

新场景使用 `--scene` 指定，程序自动加载、机械绑定、全场景传感器发现与检查。
不再为普通换场景复制 job 或修改共享相机路径，也不登记新场景整文件哈希。
每次切换前完整结束旧流程；录制与采集中不热换 Stage。

## 1 核心接入条件

| 项目 | 要求 |
| --- | --- |
| 场景入口 | 目标 Linux 实例可读取的完整 `.usd/.usda/.usdc` 绝对路径，必要引用、payload 和纹理可解析 |
| 世界约定 | 米制、Z 向上；挖机外部环境按静态验收 |
| 机器人数量 | 恰好一台兼容挖掘机；外层节点路径可变化 |
| 机械接口 | 五刚体、四转动关节，连接、轴向、两侧关节坐标与零位符合已选 profile，限位和实际 Articulation 有效 |
| 传感器 | 机械结构不要求任何传感器；不限制名称、数量或是否位于车上 |
| 灯光 | 零个或一个可见 DomeLight 自动保留；多个时明确指定 `--background-dome` |

标准机械结构如下，`<robot_root>` 由程序发现；五刚体保持平级，机械连接由 joint 的 body0/body1 表达：

```text
<robot_root>
├── track_link
├── swing_link
├── boom_link
├── arm_link
├── bucket_link
└── Joints
    ├── swing    track_link → swing_link
    ├── boom     swing_link → boom_link
    ├── arm      boom_link → arm_link
    └── bucket   arm_link → bucket_link
```

传感器可以挂在部件、模型根、三脚架或建筑上，使用有效 USD 类型和属性识别，不按名字猜型号。
节点名称相同仍需机械接口兼容；修改枢轴、轴向、零位或机械尺寸属于新的接口适配。
profile 中历史文件哈希只说明基线来源，机械原点和 swing 工程假定零位继续检查。

## 2 结束上一轮

1. End Trajectory，等待 `recording_complete=true` 和轨迹排空完成。
2. 正式采集完成或 Stop + Drain，等待进程退出及资源锁释放。
3. Exit Controller，并正常结束旧网页服务；新场景重新启动本轮流程。
4. 保留旧轨迹和输出，不删锁文件绕过仍在运行的任务。

## 3 直接指定新场景

在远端图形桌面的第一个终端运行：

```bash
export PROJECT=/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless
/usr/bin/python3 "$PROJECT/run_web.py"
```

第二个终端运行：

```bash
export PROJECT=/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless
/usr/bin/python3 "$PROJECT/run_capture.py" --interactive \
  --scene /root/gpufree-data/IsaacSim_Asset/combine_stage/new_scene.usda
```

将示例场景路径替换为实际文件，浏览器打开 `http://127.0.0.1:17877`。
不传 `--scene` 时使用默认 scene18 交互配置；`--job` 仍用于高级配置。
含空格的路径加引号。当前命令入口不支持 URI/Nucleus、USDZ 或相对场景路径。
Script Editor 的入口仍使用已打开 Stage；常规换场景优先使用上面的独立交互启动器。

多个可见 DomeLight 时在同一条交互命令追加：

```bash
--background-dome /World/Lighting/ChosenDome
```

需要独立输出根时，网页和交互命令都传入相同的 `--output`，例如 `/root/gpufree-data/semantic/output/s06site02`。
默认输出与 socket 不会因为场景名而自动改变。Unix socket 路径长度有限，输出根宜简短。
同一卡仍按已有资源约束运行，不能通过更换输出根并发启动采集。

## 4 查看自动绑定与选择结果

网页“场景绑定与传感器选择”显示实际场景、挖机根、profile、发现/可采集/已选数量。
默认选择全部可采集候选，包括原来没有写入四相机配置的 overview Camera。
录制前可取消或调整设备，点击 Apply Sensor Selection；正在录制或排空时不允许改变清单。

| 设备/安装 | 当前处理 |
| --- | --- |
| 普通透视 Camera | 从 USD 读取光学参数，输出尺寸默认 1920×1080，可由 job 的 `sensors.camera_resolution` 指定 |
| 原生 OpenCV pinhole / fisheye | 读取各自原生 imageSize、内参和畸变，按真实模型输出 CameraInfo |
| Instant RTX LiDAR | 保留既有冻结采集、原生输出轴和位姿/时钟检查 |
| 车载部件设备 | 随实际承载刚体运动 |
| 模型根附属设备 | 通过运行会话层的独立安装参考随底盘运动，不移动整个模型容器 |
| 环境固定设备 | 保持世界位置，TF 直接以 world 为父参考；挖机 placement 不移动它 |
| 预留官方 IMU | 列出类型和状态；官方物理步探针独立验证，正式同步尚未启用，不生成占位消息 |
| 暂不支持或参数无效的设备 | 显示具体原因，默认不选入；显式请求该设备时失败，不静默少采 |

可识别、可采集和可编辑安装是不同能力。只读安装可支持采集；程序不为了编辑而移动共享支架或建筑。
其他运动对象携带的设备可发现，但其动态重放不在范围内。
零设备允许机械操控和轨迹录制；正式采集至少需要一个已支持且选中的设备。

本次解析后的 job 和绑定结果位于输出根的 `runtime/launches/<launch_id>/job.json`、`launch.json` 和 `binding.json`。
最终轨迹保存实际 registry、选择、profile 和接口；高级参数优先级为显式 CLI、显式 job、通用默认。
显式 job 含旧灯光路径时保留该选择，失效则提示修正；直接 `--scene` 使用通用灯光规则。

## 5 录制和首次短采

1. 等待 `interactive_ready`，确认实际场景、机器人和设备清单正确。
2. Start Trajectory，然后 Play Simulation，按既有网页或键盘方式操控。
3. End Trajectory 并等待完整排空；原生 Stop 同样结束文件，再录会创建新文件。
4. 首次接入先采少量组数，回读图像/点云、标定、TF、时间和写入数量，再采完整轨迹。

```bash
export PROJECT=/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless
/usr/bin/python3 "$PROJECT/run_capture.py" \
  --trajectory /root/gpufree-data/semantic/output/sensor_visualizer/single0602Headless/trajectories/完整轨迹目录 \
  --groups 4
```

该新轨迹默认使用自身记录的场景和设备，不必再次填写 scene。正式任务与轨迹具有各自的快照。
外部轨迹先通过网页 Import 导入本版输出目录，不能绕过采集监督器的目录约束。
完整轨迹使用 `--all-trajectory`；采样范围和排空行为见 [操作指南](OperationGuide.md)。

## 6 旧轨迹配合新环境

场景策略和传感器策略分别选择：

| 选择 | 含义 |
| --- | --- |
| `--scene-policy original`（默认） | 使用原场景与记录设备，继续检查已记录 USD 身份 |
| `--scene-policy environment --target-scene ...` | 显式改变环境，同路径编辑版也使用此模式 |
| `--sensor-policy recorded`（默认） | 恢复来源设备及安装 revision；目标可有其他设备，但不会自动替换来源清单 |
| `--sensor-policy target_scene` | 用目标场景自身的可采集设备，不套用来源安装；只用于 environment |

例如，只复用旧机械轨迹，使用新场景自己的设备：

```bash
export PROJECT=/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless
/usr/bin/python3 "$PROJECT/run_capture.py" \
  --trajectory /root/gpufree-data/semantic/output/sensor_visualizer/single0602Headless/trajectories/完整轨迹目录 \
  --scene-policy environment \
  --target-scene /root/gpufree-data/IsaacSim_Asset/combine_stage/new_scene.usda \
  --sensor-policy target_scene --all-trajectory
```

按需追加 `--placement X_M Y_M Z_M YAW_DEG`，顺序为绕世界原点旋转后平移。
placement 作用于机械轨迹和实际车载设备，世界固定设备保持不动；不做自动贴地、避障和轨迹缩放。
target_scene 的观测属于新传感器配置，不表示复现了原来的视角。来源与目标身份分别保存。
旧接口版本继续兼容读取；缺少来源证据时应重新录制，不从目标设备补造旧接口。

## 7 必须核验及不要求核验的事项

必须核验：组合资源可用、米制与 Z 向上、唯一标准机械接口、零位读回、有效传感器参数和承载参考、
实际选择与输出一致、轨迹完整、采样时钟、写入排空和结果可回读。
首次接入需要确认图像内容、点云和静态环境约定；程序不能证明不存在所有外部运动脚本。

不要求地形或外观与 scene18 一致，不登记场景白名单，不做真实碰撞/受力/液压验收，
不新增机械速度或加速度求解，不要求四相机或任何传感器属于挖机。
IMU 原始测量另有物理时钟和语义边界，不能用离散位置差分伪造惯性数据。

## 8 常见失败

| 提示 | 处理 |
| --- | --- |
| Scene does not exist | 检查目标实例上的实际路径与依赖，不使用本地 Windows 路径 |
| Multiple visible DomeLights | 指定有效 `--background-dome`，不让程序猜目标 |
| Expected one supported excavator | 检查实际组合后的机器人数量、Articulation 和关节关系，不只改最强 USD 层的节点文字 |
| Incompatible excavator.joints | 按具体轴、枢轴、零位或连接差异修复资产，或单独适配 profile |
| Unknown/Recorded sensors missing | 检查选择清单、来源策略和真实路径；不要随意重命名旧设备 ID |
| No selected capture-ready sensors | 选择有效相机或 Instant LiDAR；预留 IMU 暂不能单独启动正式采集 |
| slot_bytes 不足 | 按实际图像尺寸和设备数量增加 job 的缓冲容量或减少选择，不能静默少采 |
| unrecorded moving carrier | 该设备依赖未记录的外部运动，首版不能作为固定设备采集 |

设计、验证范围及官方 IMU 接口见 [005 方案](../ImpPlan/005_单参数场景加载与自动绑定_实现方案.md)；
实际证据见 [验证记录](../Testing.md)。
