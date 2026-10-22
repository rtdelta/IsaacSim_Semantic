# single0602Headless 交付对接说明

更新日期：2026-10-22，北京时间。适用代码版本：`0.5.0`。

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

接收方使用本项目完成“GUI 操作挖掘机并录制轨迹 → 结束并排空轨迹 → 独立 Headless 重放采集 → MCAP 回读”。当前适用范围是静态兼容场景中的单台兼容挖掘机。历史 scene18 回归基线是 13 路雷达和 4 路鱼眼相机；现在会扫描完整 Stage，用户新增的环境相机也会出现在实际清单中。

首次运行按 [操作指南](OperationGuide.md) 执行；更换场景或挖掘机按 [换场景核验与操作](SceneSwitchGuide.md) 执行。坐标的完整定义以 [CoordinateFrames.md](../CoordinateFrames.md) 为准。

## 1 交付范围

| 交付项 | 接收方获得什么 | 对接要求 |
| --- | --- | --- |
| 独立项目 | 入口脚本、`single0602_headless/`、`config/`、`web/`、`tools/`、`tests/` 和正式文档 | 按当前 `project_manifest.json` 校验，保留 `source_provenance.json` 的历史来源身份 |
| 完整运行资产 | `IsaacSim_Asset/` 中的场景、挖掘机、地形、材质、纹理和传感器文件 | 保留目录层级，检查目录外依赖；Git clone 不会自动取得被忽略的大文件 |
| 运行环境记录 | Isaac 精确 build、GPU、驱动、OS、ROS 和实际解释器 | 采用下表中的已验证环境作为复现基线，环境变更后重新短采 |
| 轨迹和采集样例 | 完成排空的轨迹、任务私有轨迹快照、MCAP 及其配套 JSON | 样例必须来自同一套代码、场景和配置，连同回读所需路径一起交付 |
| 验收材料 | 本说明、操作指南、换场景清单、精选结果摘要 | 接收方重新完成一次录制和 3～5 组短采后签收 |

2026-10-19 的 capture 实例迁移已完成整个资产目录复制：600 个普通文件、4,339,056,580 字节，包含隐藏的 Git/LFS 文件；迁移前后及运行后的内容校验均一致。当次代码部署为 142 个文件，包含一个登记 141 个成员的项目 manifest。后续文档更新会改变文件总数，接收方以本次交付的 manifest 为准。

这次迁移没有搬运旧实例的历史轨迹和采集数据，也没有克隆 OS、驱动或虚拟环境。新机验收轨迹和约 70 MB 的短采 MCAP 是在接收端新生成的。对外制作发行包时，应另行选定并封存样例，不能把“资产和代码已迁移”当作 RViz、STL 制作包或 3DGS 环视套件也已全部交付。

## 2 部署目录与环境

首版保持下面的 Linux 路径。场景 profile 和轨迹依赖清单包含绝对路径，改变路径需要明确的配置及身份处理。

| 内容 | 路径 |
| --- | --- |
| 项目 | `/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless` |
| 资产根 | `/root/gpufree-data/IsaacSim_Asset` |
| 默认场景 | `/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_18_terrain_fisheye_mesh.usda` |
| 挖掘机资产 | `/root/gpufree-data/IsaacSim_Asset/excavator_module_set/Excavator_Mesh_Contract/Excavator_Mesh_Contract.usda` |
| 输出根 | `/root/gpufree-data/semantic/output/sensor_visualizer/single0602Headless` |
| 交互 IPC | 输出根下的 `runtime/engine.sock` |
| Isaac | 默认 `/root/isaacsim`；已有安装在其他位置时设置 `ISAACSIM_PATH` |
| ROS | `/opt/ros/jazzy/setup.bash` |
| 网页 | 远端 `http://127.0.0.1:17877`，只监听回环地址 |

| 2026-10-19 接收端基线 | 实际值 |
| --- | --- |
| OS | Ubuntu 24.04.4 LTS |
| GPU | 单卡 NVIDIA L40，驱动报告总显存 46,068 MiB |
| NVIDIA 驱动 | `580.126.09` |
| Isaac Sim | `6.0.1-rc.7+release.42383.32955d8d.gl` |
| ROS | ROS 2 Jazzy，已有 rosbag2 MCAP 存储插件 |
| Python 分工 | 系统 Python 启动网页和监督进程；Kit 内运行仿真；系统 ROS 环境写入和回读数据 |

标准网页使用 Python 标准库，不需要安装网页框架。ROS 工作进程还需要现有 `rclpy`、`rosbag2_py`、NumPy 和 Pillow。验收本次复用了已有环境，没有安装新依赖。不要用系统 Python 能否直接 `import pxr` 判断 Kit 内 USD 是否可用；ROS 导入检查则应先加载 ROS setup，且不要使用会忽略其 `PYTHONPATH` 的 `python -I`。

SSH 地址、密码、凭据引用和主机身份登记由本地私有实例配置管理，不放入可分享的交付文档。运维角色分为 `isaac-test` 和 `isaac-capture`，具体连接信息另行提供。

## 3 运动与坐标对接

### 3.1 运动结算范围

交互以 1× 为目标，取消旧方案的 `≤0.1×` 限制。脚本按原生仿真步写入离散位置和角度，清零物理线速度、角速度和 DOF 速度。界面的 m/s、°/s 用于计算每步位置增量；位置随时间变化与物理速度读回为零可以同时成立。

本版不要求真实碰撞、受力、接触、液压或机构动力学响应，不新增加速度估计或发布字段。USD 刚体和 Articulation 仍是位置控制接口，关节连接和局部坐标必须正确。运行时会在匿名会话层禁用受控挖机的重力、碰撞和继承驱动力，不应据此评价真实机械性能。

### 3.2 原点与关节零位

| 名称 | 定义 | 对接时避免的误用 |
| --- | --- | --- |
| 业务根 `swing_coordinate` | 当前模型容器声明的业务参考点，经固定参考偏移与实际底盘姿态关联；本版语义等效于 track 参考系 | 不把名字直接解释为驾驶室刚体原点、重心或接地点 |
| 水平系 `swing_horizontal_coordinate` | 与业务根同原点，Z 对齐世界 Z，X 为整机前向轴的水平投影，随航向更新 | WASD 不使用固定世界 X/Y，也不自动贴地 |
| 工作关节零角 | USD 原生关节轴、`localRot0/1` 和装配绑定姿态共同定义 | “启动姿态”不等于“各关节为 0”；不能按截图重新定义零位 |
| scene18 mesh 零角 | 该重建资产的 bind pose；不是大臂水平、小臂竖直或斗底水平 | 不添加历史 URDF 或 `bag_2` 的零偏 |
| cab–track/swing | 工程角假定为 0；以 profile 声明的原生零角执行并读回核验 | 仿真核验不代表真实设备回转角已测量 |

工作关节初始角来自当前 Stage 初始化后的原生 DOF 读回；界面和轨迹直接使用这些原生角。识别器中的 `urdf_names` 仅表示关节名是 `swing/boom/arm/bucket`，不表示已经套用了 URDF 的历史角度定义。

scene18 的固定 cab 安装高度 0.6 m 仍保留。换挖掘机时应记录新资产自己的安装偏移、轴、限位和零位证据，不能照搬 0.6 m 或 scene18 的视觉缩放。

### 3.3 单位与接口约定

| 数据 | 当前约定 |
| --- | --- |
| Stage 单位和轴 | `metersPerUnit=1`，按 Z 向上使用；米制由运行器检查，Z 向上列入资产核验 |
| 位置 | 米，根位置在 world 中 |
| 轨迹 `joints_deg` | 三个工作关节的原生角，单位度；swing 零位另有契约记录 |
| ROS `JointState.position` | swing 加三个工作关节，单位弧度；`velocity` 和 `effort` 是空数组，不是四个实测零值 |
| 轨迹和 ROS 四元数 | `xyzw`；Tensor/部分 USD 接口使用 `wxyz`，转换要显式进行 |
| 安装位姿导出 `poses_*.json` | 单独声明 `quaternion_order=wxyz`，不能沿用轨迹的排列假设 |
| 矩阵 | USD/Gf 使用行向量；跨库使用列向量时先按约定转置并调整乘法顺序 |
| 雷达 XYZ | 各雷达原生局部 frame；转到 world 使用同组 TF |
| 相机 optical | X 右、Y 下、Z 前；与 USD 相机 X 右、Y 上、−Z 前区分 |

TF 主链为：

```text
world
└── swing_horizontal_coordinate
    └── swing_coordinate
        ├── 各雷达 frame
        └── 各相机 optical frame
```

业务 TF 不自动提供五部件机械 link 树。安装在运动部件上的传感器，其相对业务根变换会变化，应逐组读取。对接 RViz/STL 或 3DGS 时，另按 [原交付方案](../DeliveryPlan.md) 的机械部件与视觉资产适配要求验收。

## 4 文件与数据接口

| 目录或文件 | 用途 | 交接要求 |
| --- | --- | --- |
| `trajectories/<id>/metadata.json` | 完整性、场景、契约、原点、关节、安装 revision、文件哈希 | `recording_complete=true` 且无录制错误 |
| `states.jsonl` | 完整状态序列，包括位置、四元数、工作关节和 revision | 作为实际重放状态源，不单独丢弃 metadata |
| `trajectory.csv` | 便于查看、导入导出的辅助状态表 | 不能单独充当缺少身份信息的可兼容轨迹 |
| `control_events.jsonl` | 控制事件记录 | 随完整轨迹保留 |
| `tasks/<task_id>/` | 启动配置、不可变轨迹快照、状态、控制文件和 `kit.log` | CLI 返回 task ID 后仍需检查任务状态 |
| `<capture_session>/bag_unified/` | MCAP 分段及 `metadata.yaml` | 连同会话 JSON 和任务轨迹快照一起保留 |
| `job_spec.json`、`trajectory_metadata.json` | 本次采集计划与源轨迹身份 | 用于区分计划采完和用户提前停止 |
| `sensor_registry.json`、`render_profile.json` | 实际传感器、标定、轴向及渲染配置 | 下游按实际登记表解码 |
| `asset_manifest.json` | 场景根、已使用 USD 层、profile 和哈希 | 当前不穷尽所有独立纹理；完整交付清单另行核验 |
| `writer_report.json` | 写入组数、话题计数、消息摘要和结果 | 与 MCAP 独立回读对照 |
| `pose_adjustments/` | 安装调整日志和显式导出的位姿快照 | 保存快照不等于修改源 USD，也不等于下次自动载入 |

默认传感器配置产生 32 个 topic、每组 19 条 TF 边：

| 话题 | 数据类型或语义 |
| --- | --- |
| `/clock` | 本次采集原生仿真时钟 |
| `/tf` | 同组业务参考与传感器变换 |
| `/joint_states` | 原生关节弧度角 |
| `/excavator/root_pose` | world 中的业务根位姿 |
| `/lidar/<id>/points` | `PointCloud2`，XYZ little-endian float32，每点 12 字节 |
| `/camera/<id>/image_raw/compressed` | RGB PNG，默认四路 1920×1080 |
| `/camera/<id>/camera_info` | `equidistant`，4 个畸变系数和实际内参 |
| `/camera/<id>/pose` | world 中的相机 optical 位姿 |
| `/sensor_visualizer/frame_index` | 组号、轨迹源时间、采集时间和实际传感器矩阵 |
| `/sensor_visualizer/run_metadata`、`/sensor_visualizer/camera_metadata` | 会话级定义与标定 |

若另行变更传感器数量，话题和 TF 数量随 registry 变化，不能继续机械要求 32 和 19。

## 5 时间与重放一致性

新轨迹 `time_base=native_simulation_seconds`。兼容的旧完整轨迹保留 `prescribed_control_simulation_seconds`，不因 GUI 倍率而二次缩放。轨迹源时间、采集原生时间和墙钟是三个量：同一组通过 `frame_index` 建立映射，不能直接把源时间当 MCAP 的绝对 stamp。

“完整轨迹”按 `k / sample_hz` 采有效时间网格。忽略 `1e-8 s` 的边界容差后，组数为 `floor(duration × sample_hz) + 1`。26.5 s、10 Hz 为 266 组；26.53 s 也采到 26.5 s，不追加非等间隔尾帧。10 Hz 是仿真时间采样率，不表示每墙钟秒完成 10 组。

每个采集任务使用自己的轨迹快照，GUI 退出后仍可继续。重放核验场景、原点版本、根参考偏移、swing 映射、关节定义和记录的 USD 层哈希。修改场景或挖机后，应在新组合中重新录制。

## 6 接收验收与职责

| 负责方 | 应提供或完成的内容 |
| --- | --- |
| 资产提供方 | 初始 USD 场景、完整引用、统一模型层级、关节装配与原生零位、传感器类型和标定 |
| 程序维护方 | 配套代码及配置、经过核验的 asset profile、manifest、运行与数据说明 |
| 操作和接收方 | 指定环境启动、录制结束排空、短采、独立回读、实际键盘焦点检查及结果确认 |

| 验收项 | 通过标准 |
| --- | --- |
| 文件一致性 | 本次交付清单缺失和哈希不符均为 0 |
| 初始场景 | 米制、Z 向上、唯一兼容挖机、关节和零位匹配、依赖及传感器可用；详见换场景清单 |
| 交互 | 开关键控和 Hold 不暂停场景；Pause/Play 续同一录制；Stop 完成当前文件，下一轮新建文件 |
| GUI 速率 | 1× 为目标；既有短测采用 0.9～1.1× 判断，需记录实际值和负载，不作为任意新场景性能保证 |
| 短采 | 3～5 组，采集、写入、排空、退出和锁释放全部确认 |
| MCAP | 使用 `tools/validate_capture_data.py` 成功回读；载荷摘要、标定、源时间和组数一致 |
| 源文件保护 | 运行后原场景及受控资产哈希保持不变 |

当前回读工具的自动门槛是：根位置误差 `<2e-5 m`、四元数正负等价后的 L2 误差 `<2e-5`、工作关节角误差 `<2e-5 rad`、TF 对实际传感器 world 矩阵的最大元素差 `<2e-5`。四元数 L2 阈值不是弧度角阈值，矩阵元素误差也不是雷达测距精度。swing 使用 profile 指定容差，scene18 为 `1e-5 rad`。更严格的几何模型或实测传感器精度验收另行约定。

2026-10-19 capture 实例结果见 [迁移验收摘要](../reports/acceptance_20261019/capture_migration_summary.json)：54 项 Linux 测试通过，GUI 稳态约 1.000157×，Headless owner 约 0.999914×，物理速度读回最大值 0；5 组、13 雷达、4 相机的 MCAP 回读通过。实体键盘没有在新机上自动注入测试，接收人应实际点击视口后按键确认。

## 7 当前边界与后续事项

| 事项 | 本版处理 |
| --- | --- |
| 更换场景或挖机 | 初始接口核验、完整重启；新录轨迹或选择更换环境采集复用兼容轨迹 |
| 运行中 File/Open 或热切换 | 不作为交付流程；Stage 变更会使旧句柄失效 |
| 多台挖机、多分支机构、任意传感器类型 | 不属于当前统一资产接口，需另行适配 |
| 其他对象的运动 | TODO：尚不记录或重放；本版使用静态环境验收 |
| 真实碰撞、受力、液压、物理速度和加速度估计 | 不纳入本版目标 |
| 任意资产目录、旧轨迹跨资产迁移 | 需明确路径与身份映射，不能靠关闭哈希检查完成 |
| RViz 五部件 STL 与 3DGS 环视 | 独立交付和适配项，不能由主程序采集通过推定已完成 |

交接确认至少记录：代码与资产清单、场景 profile ID、挖机原点版本、环境、接收方新轨迹、短采会话、回读结果、实际键盘检查和未解决事项。源实例或上一份完整代码与配置可作为回退依据，回退时恢复对应资产与配置组合后再录制。
