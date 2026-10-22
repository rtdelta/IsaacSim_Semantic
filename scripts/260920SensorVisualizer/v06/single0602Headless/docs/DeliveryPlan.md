# single0602Headless 同事交付方案

日期：2026-10-19，北京时间。运行代码基线：0.3.0。本文是包含仿真采集、模型制作、RViz 和 3DGS 的综合交付设计。

主程序已完成向独立 capture 单卡实例迁移，完整资产目录 600 个文件校验一致，并通过 GUI 交互及 5 组全传感器 MCAP 回读。当前可执行材料为 [交付对接说明](handoff/DeliveryHandoff.md)、[操作指南](handoff/OperationGuide.md) 和 [换场景核验与操作](handoff/SceneSwitchGuide.md)，接收端结果见 [迁移验收摘要](reports/acceptance_20261019/capture_migration_summary.json)。下面的综合发行目录、配套 STL/RViz、3DGS 扩展和最终同事签收仍按各自范围推进，不能由主程序迁移通过推定全部完成。

建议以 **single0602Headless 源码、完整 scene18 资产依赖、同源演示数据、操作与对齐说明** 组成一个有版本号的发行套件。首版沿用现有 Linux 运行目录，先完成同事独立回放、录轨迹、短程采集，再考虑任意安装路径与 3DGS 环视接入。

## 1 交付目标与范围

接收同事应能独立完成三件事：使用已有数据检查模型与点云；操作仿真录制完整轨迹并进行 Headless 采集；解释模型原点、关节零位、传感器外参和时间戳的关系。接手资产制作的同事还应能从封存五部件 mesh 重建挖掘机。

默认接收环境为具有图形桌面的 Linux GPU 机器，采用发行时记录的 Isaac、ROS 2 Jazzy 和 Python 环境。Windows 当前有逻辑测试记录，不能据此承诺原生 Windows 完整采集可用。只回放数据的同事采用 ROS/RViz 环境，无需启动 Isaac。

| 使用目的 | 必交内容 | 完成标志 |
| --- | --- | --- |
| 仿真操作和数据采集 | 主程序、完整场景资产、示例轨迹、操作手册、环境记录 | 新录轨迹完成采集和独立回读 |
| 模型与点云回放 | 独立 RViz 工具、同源 STL 和 manifest、示例 MCAP、数据字典 | 可暂停、单步并核对同一组几何关系 |
| 模型制作与修改 | 完整 mesh 重建交接包、装配和关节定义 | 包校验及重建验收通过 |
| 3DGS 环视接入 | 指定版本 PLY、渲染器及 YAML、显式 TF 适配和绑定说明 | 单关节动作及倾斜对接通过；作为扩展项单独验收 |

3DGS PLY 不是本版 mesh 场景采集的运行依赖。需要环视时，应交付实际渲染程序及其配置；只交 PLY 与历史说明不足以形成可运行环视包。

## 2 发行套件结构

以下是发行目录设计，不移动仓库现有源码与资产目录。大文件可以按同一个 release ID 分卷传输。

```text
single0602_delivery_<release_id>/
  START_HERE.md                  接收角色、首次运行步骤和文件导航
  release_manifest.json          源码版本、各分卷与契约版本、示例身份
  checksums.sha256               套件内文件的大小与 SHA256 清单另附机器可读版
  code/
    single0602Headless/           当前独立运行项目
    Rviz2Viewer/                 回放入口及运行模块
  runtime_assets/
    IsaacSim_Asset/              保持场景依赖的原目录结构
  examples/
    smoke/                      完整轨迹、任务快照、短程 MCAP 与回读结果
    motion_alignment/           同源运动轨迹、采集会话和 viewer_assets
  authoring/
    mesh_scene18_handoff/        输入、装配蓝图、金标准、重建与校验工具
  docs/
    QuickStart.md                按同事操作顺序编写
    AssetCatalog.md              每种资源是什么、给哪个程序使用
    AlignmentGuide.md            坐标、矩阵、单位、零位和时间
    DataDictionary.md            话题、frame、标定、文件与完成状态
    Acceptance.md                接收检查与故障定位
  environment/
    runtime_versions.json       发行时实测环境
    dependency_inventory.json   Python、ROS、Isaac 扩展及资产依赖
  acceptance/
    source/                     发送端验收摘要
    receiver/                   接收端验收结果
  optional_3dgs/                需要环视时才提供完整扩展
```

`release_manifest.json` 至少绑定：release ID、源码提交与工作树差异、项目 manifest 哈希、资产清单哈希、frame contract、asset origin、示例轨迹与采集 ID、viewer mesh manifest、环境记录和验收结论。套件清单不包含自身，最外层归档摘要另行记录。归档校验与解压后的逐文件校验分别执行。

Git 用于源码、配置和精简报告；USD、纹理、PLY、STL 和 MCAP 使用同事可访问的文件存储。当前仓库忽略这些大文件，Git clone 不是完整资源交付。发送端先冻结文件，再统计每卷大小、总解压大小和接收端所需空间，避免对运行中持续写入的数据制作发行包。

### 源码包

主程序交付整个独立项目的源码、`config/`、`web/`、`tests/`、必要工具和正式文档，排除 `reports/`、缓存、socket、临时任务与历史原始采集。保留 `source_provenance.json` 的历史身份，按最终字节生成当前 `project_manifest.json`。

回放包从 `scripts/261013Rviz2Viewer` 选取 `run_viewer.py`、`launch_viewer.sh`、`make_rviz_config.py`、`rviz_viewer/`、必要测试和文档。正式命令显式指定 capture 与 assets，避免默认 `latest` 依赖旧机器的 `reports/latest_capture.json`。`capture_runtime/` 是旧采集链路副本，不作为 single0602 的采集入口。

现有 `tools/build_deployment.py` 只生成本项目源码部署脚本，目标目录写死；它不打包 USD、STL、MCAP 或完整运行环境，不能直接充当上述套件生成器。

### 运行资产包

| 资源 | 用途与交付要求 |
| --- | --- |
| `combine_stage/combine_scene_18_terrain_fisheye_mesh.usda` | 正式场景根层，保留当前内容和引用 |
| `excavator_module_set/Excavator_Mesh_Contract/` | 主 USDA 与五个几何 USDC，保留装配变换、材质和关节 |
| scene18 的 sublayer、reference、payload 递归依赖 | 根层直接包含 scene15 sublayer、地形引用及 mesh payload；继续解析每个被引用层 |
| 地形、环境、灯光及纹理 | 保留实际使用资源与相对路径，不能只复制挖机 |
| 雷达、相机、材质及传感器配置 | 从组合后的 Stage 和实际传感器注册表提取；区分场景资产与 Isaac 扩展内资源 |

完整依赖清单需在现有可用 Isaac/USD 环境生成：解析所有有效层及资产属性，覆盖纹理、材质资源、传感器配置等非 USD 文件；记录原引用、解析路径、归档路径、大小和 SHA256。对运行所需的扩展内资源，明确由哪个已记录版本的环境提供。对网络或缓存解析得到的资源，必须明确随包封存或列为外部先决条件。

当前 `SceneStepper.build_asset_manifest()` 已记录已使用 USD 层，但明确不穷尽外部纹理；它可作为盘点起点。必须在脱离源机器缓存与源资产目录的接收环境实际打开场景，检查依赖解析，并完成相机和雷达短采，才能判定依赖闭合。

### 模型制作包

直接使用现有 `mesh_scene18/handoff/` 的完整文件夹，保留自己的 `package_manifest.json`，不重排内部目录。正式重建起点为 `inputs/waji_mesh_corrected.usdc`，包含已经拆好的五部件；更早合并 mesh 的完整拆分流水线不在已验证范围内。

该包能复现独立挖机的主 USDA 与五个 USDC，但 `scene_context/` 仅是场景根层对照。它明确没有封存背景、传感器的全部外部资源，必须与运行资产包配套。

### 演示数据包

至少提供一份 3～5 组短采样例，以及一份覆盖整机平移、航向、倾斜和三工作关节独立动作的运动样例。运动样例组数按实际轨迹时长与采样频率规划，首包规模以便于传输和检查为准。两者都必须由本次发行源码和同一资产生成。

每份样例包括：

- 已结束排空的完整轨迹：`metadata.json`、`states.jsonl`、控制事件及文件哈希；CSV 作为辅助查看材料。
- 实际采集会话：`bag_unified/` 中的 MCAP 与 `metadata.yaml`，以及 `job_spec.json`、`sensor_registry.json`、`render_profile.json`、`asset_manifest.json`、`trajectory_metadata.json`、`writer_report.json`。
- `job_spec.json` 引用的任务私有轨迹快照及必要目录映射，避免只保留来源路径字符串。
- 配套 `viewer_assets/`：五部件 STL、导出 manifest、关节锚点与 mesh 校验；一组与实际 USD 刚体状态的数值对照。
- 独立回读结果、预期组数、末次源时间和少量标注组号的截图。回放缓存可以重建，不作为原始数据。

## 3 部署路径与环境

### 首版采用原路径复现

| 内容 | 接收端首版路径 |
| --- | --- |
| 主程序 | `/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless` |
| 运行资产 | `/root/gpufree-data/IsaacSim_Asset` |
| 输出、轨迹及任务 | `/root/gpufree-data/semantic/output/sensor_visualizer/single0602Headless` |
| Isaac 安装 | 默认 `/root/isaacsim`；其他已有安装通过 `ISAACSIM_PATH` 指定 |
| ROS 环境 | `/opt/ros/jazzy/setup.bash` |

选择原路径是为了保持场景哈希、轨迹资产身份和现有检查逻辑。`config/asset_profiles.json` 按场景绝对路径匹配，并核验 scene 和独立挖机主文件的哈希；`offline_job.verify_replay_identity()` 还按轨迹记录的路径核验依赖层。

接收端先检查目标目录和已有内容，再部署到空目录；存在冲突时保留原文件并记录处理。原路径不具备部署条件时，转入单独的可迁移路径改造，不通过关闭哈希检查或批量改写旧轨迹绕过身份验证。

可迁移路径版本需统一处理 job、profile、USD 引用和轨迹依赖路径。若重写 USD 字节导致哈希变化，应建立新的资产 profile 并重新验收、录制示例；若只做位置映射，也须记录原身份到接收路径的可核验映射。

### 环境记录

发行时从实际可运行环境提取 OS、GPU、驱动、Isaac 精确 build、扩展版本、系统 Python、ROS Jazzy、rosbag2 MCAP 插件，以及 NumPy/Pillow 等实际依赖的版本。现有报告提到单卡 L40；它是历史验证环境，不能代替接收机器的兼容性测试。

网页默认采用系统 Python 标准库，无需额外网页框架。Isaac 进程、系统 ROS 写入/回读进程和普通网页进程使用的解释器及动态库需要分别记录，不用一份泛化的 `pip freeze` 代替。首版复用已安装环境；需要新安装时依据缺失清单准备明确版本、来源和安装位置。

## 4 资源对齐的统一约定

### 本版采集坐标与时间

以 [CoordinateFrames.md](CoordinateFrames.md)、`frame_contract.py`、实际轨迹元数据和采集 `sensor_registry.json` 为准。当前版本为：

```text
frame_contract_version = s0602_track_equivalent_v1
asset_origin_version   = scene18_contract_base_link_raw_reconstruction_v1
cab_track_angle_source = assumed_zero
```

本版 MCAP 的实际 TF 主链为：

```text
world
  └─ swing_horizontal_coordinate
       └─ swing_coordinate
            ├─ 13 路雷达 frame
            └─ 4 路 camera optical frame
```

五部件机械链不作为五条 link TF 自动包含在这棵采集树中；回放模型使用记录的根位姿、关节和真实 USD 锚点重建，或使用逐组实际刚体矩阵。不能因为 TF 中没有 `boom_link`，就把其 mesh 直接挂在业务根上保持静止。

| 项目 | 对接规则 |
| --- | --- |
| 业务根 B | `swing_coordinate`，本版等效于底盘业务参考系；不能按名称解释为驾驶室部件原点 |
| 水平系 H | 与 B 同原点，Z 对齐世界 Z，X 是当前整机前向轴的水平投影；WASD 使用 H |
| cab 与 track | 相对回转角采用 0 的工程假设，启动及每组核验原生 DOF；两部件的固定 0.6 m 安装高度仍保留 |
| 位置与角度 | 位置为米；轨迹 `joints_deg` 为度，ROS `JointState.position` 为弧度 |
| 四元数 | 轨迹与 ROS 接口使用 `xyzw`；读取其他 SDK 时显式转换顺序 |
| 雷达点 | XYZ 位于各自原生雷达 frame；转到 world 必须使用同组 TF，转完不能继续保留原 frame_id |
| 相机 | optical 为 X 右、Y 下、Z 前；配套读取实际 CameraInfo，不能直接用 USD 相机轴代替 |
| 传感器外参 | MCAP 给出其相对业务根的逐组变换；实际安装部件和 revision 另有记录，不能把动臂上传感器外参误当恒定值 |
| 时间 | 区分轨迹源时间、采集原生时钟和墙钟；按 frame_index 的组号与映射对齐，不能直接比较不同会话的绝对 stamp |

新轨迹采用 `native_simulation_seconds`；兼容旧完整轨迹保留其 `prescribed_control_simulation_seconds` 含义，不能再按 GUI 倍率缩放。完整轨迹按等间隔网格采样；26.5 秒、10 Hz 为 266 组，非网格尾端不额外加帧。10 Hz 是仿真时间采样率，墙钟采集速度独立报告。

### USD mesh 与 RViz STL

同一部件至少有三种不同坐标：原始 corrected mesh 空间、资产定义的部件刚体空间、world。RViz STL 必须导出到对应刚体局部空间，将 mesh 到刚体的完整变换烘焙一次。

统一采用列向量解释跨程序接口：`T_A_B` 将 B 中的点转换到 A。

```text
原始 mesh：p_W = T_W_P(t) × T_P_G × p_G
RViz STL：p_W = T_W_P(t) × p_STL，且 p_STL = T_P_G × p_G
```

USD/Gf 使用行向量矩阵，转换到上述列向量库时要转置，乘法顺序随之调整。资产重建包中的 `C × V_i × B_i(q) × W` 不能原样传给 NumPy 列向量接口。

当前 USD 的 2.4 倍缩放已位于 Visuals 变换中，corrected 到 raw 的固定配准位于 MeshAlignment；STL 导出后这些变换已经烘焙，RViz Marker 的 scale 应为 1。不能再应用公共 RPY 或 2.4 倍缩放，不能按包围盒重新设原点或凭截图微调。

现有 RViz 工具会核验场景及 STL 哈希，且可从 `/excavator/root_pose` 读取业务根，并用 manifest 中的 `base_in_reference_col`、关节锚点和原生弧度角重建五部件。接入 single0602 时需要实际验证其数据与 manifest 配对。现有 `capture_observer.py` 的导出和注入入口仍导入旧 `sensor_visualizer_v06`，不能直接当作已支持本版的导出器；应移植必要导出逻辑或制作独立导出工具。

### 3DGS 扩展的适配

历史 [3DGS TF 规范](../../../source_docs/3dgs_tf_simulation_contract.md) 使用 `base_link → swing_link → boom_link → arm_link → bucket_link`，履带是 `base_link → track_link` 独立支路，并采用 `capture_startup`。这与本版业务采集树及 USD 机械关节拓扑承担不同职责，不能直接改名互换。

扩展包应提供显式适配：由实际 USD 刚体状态和已核验的业务参考偏移计算各部件世界位姿，再按目标树计算 `T_parent_child = inverse(T_W_parent) × T_W_child`。适配器独立保留原始数据；同一 ROS domain 内每个 child 只由一个节点发布。

若整机 roll/pitch 已由全局根姿态承担，不能又在平台支路叠加同一倾斜。启动渲染器前稳定在与素材匹配的已验证绑定姿态，再捕获绑定，最后运动。历史 `bag_2` 的绝对零角和轴向符号只适用于当时资产，不得直接套入 scene18 mesh contract。

原始五份 PLY 共用重建坐标，其公共显示变换由 3DGS 渲染器应用一次；不能复用于已经烘焙的 STL。五份 PLY 的版本、哈希、绑定矩阵和逐关节符号都随扩展交付。mesh 铲斗带完整斗齿、历史 3DGS 为 `bucket_without_teeth`，要在资源表中明确几何内容差异。

## 5 同事使用流程

### 第一步 校验与回放

解压到指定位置后核对归档与逐文件清单，查看环境记录和示例说明。先在已准备好的 ROS/RViz 环境运行显式回放命令：

```bash
source /opt/ros/jazzy/setup.bash
cd /实际安装目录/Rviz2Viewer
/usr/bin/python3 run_viewer.py --capture /实际示例会话目录 --assets /配套viewer_assets目录 --rviz
```

浏览器打开 `http://127.0.0.1:8767`。RViz 使用 `world`、`use_sim_time=true`，默认独立 domain 43。先只勾一路雷达，在零位、单关节动作和倾斜组暂停，检查 mesh、TF 与点云；然后启用其余雷达。严格贴合判断以暂停后的同组状态为准。模型 ±1 组偏移仅作错帧诊断，正式验收设为 0。

该工具目前显示 mesh、TF 和点云；四路鱼眼图像需要另用配套解码检查或新增图像回放入口，不能把“MCAP 内有图像”写成“RViz 网页已播放图像”。

### 第二步 操作仿真并录制

在远端图形桌面终端分别执行：

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless
/usr/bin/python3 run_web.py
```

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless
/usr/bin/python3 run_capture.py --interactive --job config/interactive.json
```

浏览器打开 `http://127.0.0.1:17877`，等待 `interactive_ready`。按 Start Trajectory、Play Simulation，录制水平移动、转向和单关节动作。启用键控并取得回执后，点击 Isaac 视口取得焦点；WASD 为当前 H 系水平运动，Z/X 为升降，Q/E 为整机航向，U/J、I/K、O/L 为三工作关节。

End Trajectory 后等待 `recording_complete=true`。Hold 和关闭键控保持姿态，仿真继续；Pause 暂停时间；原生 Stop 或网页 Stop 会结束当前轨迹。完整键位与模式切换规则见项目 [README](../README.md)。

### 第三步 短程采集与检查

先选已完成轨迹，使用“指定最多组数”采 3～5 组，验证写入、退出与释放资源。通过后再按“完整轨迹”执行计划。外来轨迹通过网页 Import 导入本版输出目录，CLI 不直接接受任意外部轨迹路径。

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless
/usr/bin/python3 run_capture.py --trajectory /root/gpufree-data/semantic/output/sensor_visualizer/single0602Headless/trajectories/已导入轨迹目录 --groups 5 --sample-hz 10
```

完整采集时用 `--all-trajectory` 替代 `--groups 5`，两者互斥。CLI 返回任务 ID 后进程退出，子进程继续工作；要检查任务卡与 `tasks/<task_id>/` 状态。完成条件同时包含计划执行、数据排空、进程退出和资源锁释放。提前 Stop + Drain 的数据只能标记为部分结果。

```bash
source /opt/ros/jazzy/setup.bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless
/usr/bin/python3 tools/validate_capture_data.py /实际采集会话目录
```

当前回读脚本会读取 `job_spec.json` 指向的轨迹和 `asset_manifest.json` 的源 USD 路径，所以演示发行包需按第 3 节保存对应目录及文件。面向只回放的同事，可提供独立数据结构检查；若要实现任意位置完整回读，应另行增加路径映射支持并保持原始身份可追溯。

## 6 接收端验收

下表是综合发行的建议门槛，包含模型重建和跨程序对齐。除已有代码内检查外，数值阈值为本方案拟定，应固化进相应发行验收配置。主程序当前自动检查的阈值及实际接收结果见 [交付对接说明](handoff/DeliveryHandoff.md)，不能把下表的建议值全部称为已经实现的检查。发送端历史通过记录不能替代接收端结果。

| 层次 | 方法与通过条件 |
| --- | --- |
| 文件一致性 | 归档、解压后文件大小与 SHA256 全部匹配；无缺卷、缺模型或缺材质 |
| 环境与资产 | 实际 Isaac build、ROS/Python 依赖有记录；profile 匹配；脱离源目录与缓存可解析并运行完整场景 |
| 主程序逻辑 | 在项目目录执行 `/usr/bin/python3 -m unittest discover -s tests -v`；平台适用项通过 |
| 交互生命周期 | 可录制、暂停、继续、结束排空；新录制建新文件；GUI 退出后仍可独立采集 |
| 采集完整性 | 3～5 组短采成功；正式默认配置为 13 雷达、4 路 1920×1080 相机、32 topic、19 条 TF 边；按实际 registry 逐组核对 |
| 数据与时间 | MCAP/CDR/PNG 可回读；源时间网格、组数、标定和载荷摘要一致；原生时间量化误差符合现有 `0.5 / physics_hz + 1e-6 s` 检查 |
| 根姿态与关节 | 相对源轨迹位置误差不超过 `1e-4 m`、旋转测地角和关节误差不超过 `1e-4 rad`；swing 使用 profile 的 `1e-5 rad` 零位容差 |
| 模型空间对齐 | 在零位、非零工作关节、整机平移/航向/倾斜下，对应局部顶点转 world 后最大差不超过 `1e-3 m`；检查行列矩阵及缩放只应用一次 |
| 传感器对齐 | 同组 TF 还原的传感器 world 矩阵与记录矩阵的最大元素差不超过 `1e-8`；雷达 frame_id、光学轴、安装 revision 一致 |
| 几何时序 | 在运动样例单步对照同组及前后组，保存图像/点云与实际 mesh 的数值或标注证据；测距噪声、可见性等单独计入，不把上述模型变换容差当作雷达测量精度 |
| 退出与资源 | 写入数等于采集数；完整结果等于计划数；排空、退出码和锁释放都有结论 |
| 资产重建 | `verify_package.py` 通过；用冻结 SDK 重建后与金标准比较，记录六文件字节一致结果 |

几何时序检查的测量阈值，应先在发送端用固定姿态和重复采集建立基准，并随 release 保存。相同消息时间戳和 TF 数值一致只能证明时间与变换记录相符，不能单独证明所有传感器的几何内容已更新。

现有 [Testing.md](Testing.md) 记录了本版短程功能、连续交互及生命周期验证；003 验证未执行 26.5 秒轨迹的 266 组全量重采。其他对象的运动尚未记录和重放；演示复现应采用静态环境，仅覆盖挖机和其传感器。性能说明分别给出 GUI 倍率、采集墙钟耗时、启动开销与数据体积。

## 7 实施顺序与交付完成条件

| 阶段 | 具体工作 | 产物与退出条件 |
| --- | --- | --- |
| 1 冻结版本 | 选择当前代码提交，冻结最终配置，记录环境与运行资产；为工作树差异制作明确快照 | release ID、源码及资产基线可核验 |
| 2 闭合资源 | 在原环境解析完整依赖，封存非 USD 资源，统计体积与外部环境先决条件 | 接收端不依赖源机器目录或未声明缓存 |
| 3 制作同源示例 | 本版生成短采与运动样例；补齐本版 STL 导出并核验根参考偏移、关节锚点和五部件姿态 | MCAP、轨迹、viewer_assets 与报告一一对应 |
| 4 编写操作材料 | 按首次回放、录制、短采、全量和排错顺序整理；资源逐项解释用途、原点和使用入口 | 同事不依赖口头补充即可执行 |
| 5 独立机器验收 | 用空部署目录完成校验、回放、新录制和短采；记录差异及修正 | 第 6 节适用门槛通过 |
| 6 正式交接 | 提供相同 release ID 的分卷、校验清单、结果与问题入口；由同事独立完成一次操作 | 接收人确认可回放、可录制、可采集、可解释对齐 |

主程序的完整资产目录清单、scene18 依赖检查、接收环境记录和跨机器短采已完成。综合发行还需补齐正式套件组包、single0602 配套 STL 导出及真实 RViz 回放验证、连同任务快照和配套资产封存的演示数据，以及同事独立操作签收。若同事不具备原路径条件，再把可迁移路径及独立回读作为前置实现。3DGS 扩展根据实际使用目的另开验收。

交接材料同时保留常见症状的定位顺序：profile 报错先查路径和哈希；缺画面先查材质与相机；模型尺寸错误先查重复缩放；关节错位先查锚点、零位和度/弧度；点云错位先查同组 frame 与 TF；时间错位先查源时间映射；任务停止后先查排空、进程与租约状态。

发行更新必须给出变更说明。修改模型原点、零位、TF 拓扑或时间含义时升级相应契约并重新生成示例；接收端保留前一个发行目录，输出写入独立目录。回退以停止本次所属进程、恢复对应源码与资产版本并重新校验为准，不混用前后两个版本的轨迹、STL 和数据。

## 8 现有材料索引

| 材料 | 作用 |
| --- | --- |
| [主项目 README](../README.md) | 现有启动、操作、键位和兼容要求 |
| [交付对接说明](handoff/DeliveryHandoff.md) | 当前主程序交付边界、数据契约与接收结果 |
| [操作指南](handoff/OperationGuide.md) | 按首次启动、录轨迹、短采、完整采集和回读顺序执行 |
| [换场景核验与操作](handoff/SceneSwitchGuide.md) | 初始 USD 核验项、统一挖机结构和新组合操作 |
| [坐标与运动契约](CoordinateFrames.md) | 本版业务原点、水平系和 cab–track 假设 |
| [实现状态](ImplementationStatus.md) | 当前模块、资产原点和采集范围行为 |
| [验证记录](Testing.md) | 已完成验证、性能测量及适用范围 |
| [资产 profile](../config/asset_profiles.json) | 当前场景、独立挖机哈希与 swing 零位声明 |
| [mesh 重建交接包](../../../mesh_scene18/handoff/README.md) | 五部件输入、重建和已有金标准 |
| [mesh 完整重建说明](../../../mesh_scene18/handoff/MeshRawToExcavator_Reconstruction_Handoff.md) | corrected/raw/body/world 变换与装配定义 |
| [RViz 独立工具](../../../../261013Rviz2Viewer/README.md) | 回放行为、资源及现有验证边界 |
| [3DGS TF 规范](../../../source_docs/3dgs_tf_simulation_contract.md) | 扩展环视的目标接口，需显式适配 |
| [3DGS 部件素材定义](../../../source_docs/3dgs_part_local_frames.md) | PLY 指纹、公共显示变换和绑定含义 |
