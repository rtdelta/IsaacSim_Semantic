# 实现与方案对照

更新：2026-10-22，北京时间。版本 0.5.0。初始设计依据为本目录 `CoordinateFrames.md` 和 `ImpPlan/001_single0602Headless_实现方案.md`，当前交互规则以 002 修订为准，采集范围规则以 003 修订为准。

当前设计依据：[002 连续交互改进方案](ImpPlan/002_连续交互改进方案.md)。已实现原生 Timeline 连续交互、逐仿真步位置设置及物理速度清零、Stop 结束文件和重新绑定；其他对象记录保留在 TODO。1× 为交互目标，实际倍率和验收范围见 [验证记录](Testing.md)。

[003 完整轨迹采集改进方案](ImpPlan/003_完整轨迹采集改进方案.md) 已实现“完整轨迹／指定最多组数”、自动采集计划、只读预览、快照计划核验及完成范围展示。网页默认完整轨迹；旧 API 和 CLI 未提供新范围选项时保持最多 100 组的历史默认。具体测试及真实数据回读范围见 [验证记录](Testing.md)。

[005 单参数场景加载与全场景传感器发现](ImpPlan/005_单参数场景加载与自动绑定_实现方案.md) 实现于
`launch_config.py`、`sensor_catalog.py`、`scene.py` 及重放、消息和网页模块。
新增运行配置快照、全 Stage 设备候选与选择、普通/原生 OpenCV 相机标定、车外固定设备 world TF、根附属设备跟随。
新版 `scene_interface=2`、`sensor_registry=3` 保留旧轨迹读取；跨环境可显式使用目标传感器配置，旧默认仍恢复来源设备。
`imu_interface.py` 仅提供原生物理域探针与导出映射预留，不参与正式冻结采集。实际证据以 Testing 为准。

| 要求 | 实现位置 | 行为 |
| --- | --- | --- |
| 独立包、端口、输出和 IPC | `single0602_headless/`、`run_web.py`、`config/` | 包内导入自包含，网页 17877；使用独立输出，源码移植来源及哈希另存 |
| 完整坐标契约 | `frame_contract.py`、`robot/articulation_motion.py` | 写入版本、原点、固定偏移、工程假设、零位映射和启动读回；snapshot 验证每次 swing |
| 已声明零位 | `config/asset_profiles.json`、`scene.py` | 按 scene18 mesh contract 的原生重建 bind 零位设置 swing=0；核验声明及组合机械接口，文件哈希仅记录身份 |
| 当前 H 系键控 | `keyboard_control.py`、`robot/reference_frames.py` | 每步先按起始姿态计算水平投影和平移，再转向；保留退化迟滞和四元数连续性 |
| 原生焦点及重复事件 | `native_keyboard.py`、`interactive_runtime.py` | 应用、视口焦点和输入阻塞一起检查；KEY_PRESS 才能新增按键，失焦后 KEY_REPEAT 无法恢复 |
| 混合控制交接 | `interactive_runtime.py`、`keyboard_control.py` | 模式配置完整校验后提交，清键、epoch、实际读回建立基准；网页显式运动使旧输入失效 |
| 网页实际回执 | `web/static/app.js`、`control_ipc.py` | 开关以引擎已应用状态显示；携带 epoch/序号；刷新读状态而不重建会话 |
| 连续录轨迹 | `trajectory.py` | 完整状态、控制事件分流到同一个有界后台写队列；close 排空并写哈希和完整标记 |
| 原生连续交互 | `interactive_runtime.py`、`scene.py`、`interaction_clock.py` | 原生和网页 Play/Pause 控制同一个 Timeline；键控开关和 Hold 不暂停场景；单个 POST_STEP 入口计算位置并读回，重复步不重复推进 |
| 1× 目标与实时统计 | `contracts.py`、`scene.py`、`run_capture.py`、网页 | 默认目标 1×，移除旧 0.1× 上限；设置实际活动循环的正常时间推进，GUI 异步渲染与正式同步采集分离；实际倍率由原生时间/墙钟测量 |
| Stop 与重新绑定 | `interactive_runtime.py`、`robot/articulation_motion.py` | Stop 清键及取消目标，使用末次有效状态结束并排空文件；不读取已释放物理句柄；重新 Play 从实际状态绑定并 Hold，下一次录制创建新文件 |
| 离线任务快照 | `offline_job.py`、`capture_supervisor.py` | 只接收完整轨迹；任务私有副本、任务配置和来源哈希独立保存 |
| 完整轨迹采集计划 | `capture_plan.py`、`capture_supervisor.py`、`contracts.py` | 统一网格容差、完整/指定范围及合法频率校验；从任务快照生成确定组数，计划存入 job/task，可恢复并核验 |
| 计划预览与范围选择 | `web_service.py`、网页、`run_capture.py` | 只读 `/api/capture_plan`，完整模式隐藏组数，防抖及过期响应隔离；CLI 增加互斥的 `--all-trajectory` |
| 范围完成与部分结果 | `replay_capture.py`、网页任务卡 | 核对采集/写入数，区分 completed_plan / stopped_by_user / failed，源提前耗尽不能冒充完整完成；排空和资源释放独立展示 |
| 独立 Headless | `run_capture.py`、`kit_replay_entry.py`、`replay_capture.py` | 固定 offline、persistent_gated、keepalive；无交互 owner/socket 查询、无组间协作心跳 |
| 数据与保存 | `scene.py`、`sensors.py`、`pipeline.py`、`record_worker.py` | 保留冻结、源时钟、传感器回执、重试和独立 CPU 缓冲所有权；异步编码写 MCAP |
| 生命周期 | `capture_supervisor.py`、`replay_capture.py` | Pause/Resume/Stop 在完整组边界执行；保存排空、进程退出、资源租约释放分别记录 |
| 独立回读 | `tools/validate_capture_data.py` | 读取真实 MCAP/CDR/PNG，与轨迹、TF、标定、关节和逐组零位相对照 |

scene18 的资产原点采用 `scene18_contract_base_link_raw_reconstruction_v1`。它不能冒充 origin03，也不代表实测接地点或重心。swing 原生正轴为其关节父侧坐标系的 Z；cab 安装固定高度 0.6 m 保留，业务参考点等效不意味着部件原点重合。

GUI 运行器采用原生仿真步及 `native_simulation_seconds`（时间语义版本 2）；墙钟用于性能测量，不再积分第二套运动。物理速度清零，轨迹不新增速度、角速度、加速度估计。旧完整轨迹的规定控制秒保持原始含义，正式离线采样的原生时间映射单独记录。按键事件只用于解释操作，离线重建只使用完整状态。

未提供未知资产和无零位证据的旧轨迹自动迁移。新增资产需声明零位、原点和关节映射并验证其 profile；现有默认链路不会静默选择任意启动角。
