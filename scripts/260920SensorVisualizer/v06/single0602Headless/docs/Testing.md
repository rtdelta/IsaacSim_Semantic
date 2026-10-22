# single0602 验证记录

## 005 单参数加载、全场景设备与 IMU 预留（0.5.0）

2026-10-22 仅在 test 单卡执行本轮远端验证；capture 未部署本轮变更。结果见
[验收摘要](reports/acceptance_20261022/scene_binding_summary.json)，接入流程见 [换场景指南](handoff/SceneSwitchGuide.md)。

- Windows 80 项：75 通过、5 跳过；Linux 80 项：79 通过、1 项可选依赖跳过。JavaScript 语法及设备选择、录制锁定、目标设备策略 DOM 夹具通过，未重复真实浏览器视觉或实体键盘验收。
- 六种原生场景完成轨迹录制：当前 scene18 副本、零设备、仅相机、仅雷达、混合车载/环境设备和新机器人根路径。
- 七项正式短采共 31 组，全部独立回读 MCAP；另有零设备正式采集按预期在 writer 创建前拒绝。当前用户场景新增设备被扫描到，基线实际为 7 相机、13 雷达，其中保留原 4 鱼眼 ID。
- 两项摆放/目标设备策略通过；世界固定设备误差为 0，根附属设备最大矩阵误差约 `1.2e-8`，来源轨迹完整。原有位置、零位、TF、标定和 writer 摘要检查保留。
- 关节轴错误、负焦距、多台挖机、没有挖机四类初始资产负例均在创建采集产品前拒绝。
- 真实 CLI 使用含空格的新场景路径、独立输出和不含 job 的入口，生成独立配置及 ready 绑定报告后正常结束；最终 Linux 检查包含设备 ID 与生成 frame 名交叉冲突的修复。
- 官方 `isaacsim.sensors.experimental.physics.IMU.create` 资产取得连续 5 s、301 个有效样本；静止含/不含重力、旋转 90°、受控运动、重复采样和 Stop/重新初始化均通过。独立 60 个样本保留原生时间写入并回读 MCAP，正式 IMU 同步仍未启用。
- 旧接口版本归一化有单元覆盖；test 可用历史轨迹缺少匹配的已核验身份基线，被提前拒绝，不能将此项写成原生旧轨迹兼容通过。未放宽历史轨迹检查，也未为取回其他证据连接 capture。

正例夹具使用保留完整根层设置的独立副本，并明确保留单个 DomeLight；源 USD 含多个 DomeLight 的诊断规则没有取消。源资产 SHA-256 始终为 `a5c834fa948f3dc41339138e42f311491355bb8f349bb003887095b3adf15258`。

## 004 场景编辑与跨环境采集（0.4.0）

设计与操作见 [004 方案](ImpPlan/004_场景编辑与跨环境轨迹采集_实现方案.md)，
本轮独立结果见 [验收摘要](reports/acceptance_20261019/scene_replay_summary.json)。
历史 0.3.0 及更早的 GUI/性能证据仍按其原版本解释。

- Windows：62 项，57 通过、5 项跳过；Linux：62 项，61 通过、1 项可选 FastAPI 跳过。
- JavaScript 语法和 DOM 夹具检查新增目标场景、数值摆放及隐藏覆盖清除；未宣称真实浏览器视觉检查。
- 原生接口与轨迹录制通过。原场景、同路径环境修改、不同路径且源环境缺失并进行摆放，均完成 4 组真实传感器采集及 MCAP 回读。
- 原场景身份变化被拒绝；关节轴向、相机标定不兼容在正式 bag 创建前被拒绝。
- 旧轨迹使用与迁移清单中 18 个 USD 层完全一致的已核验基线，最终采集结果见摘要。

初次薄包装场景触发既有渲染位姿检查，原始场景对照通过；最终使用保留根层设置的完整副本。
测试夹具的 socket 路径和 USDA 换行问题已修正，保留失败记录，不计入通过用例。
本次没有运行中换场景、自动地形贴合或其他动态对象记录。

## capture 新单卡接收验收（2026-10-19，版本 0.3.0）

原 test 实例的整个 `IsaacSim_Asset` 目录和冻结的本地项目部署到独立 capture 实例。精选结果见 [capture_migration_summary.json](reports/acceptance_20261019/capture_migration_summary.json)；其中保留来源摘要的哈希，不包含连接凭据。

| 检查 | 接收端结果 |
| --- | --- |
| 全量资产传输与保护 | 600 个文件、4,339,056,580 字节，包含隐藏文件；源端复核、接收校验和运行后复核哈希不一致均为 0 |
| 代码快照 | 当次 142 个项目文件，manifest 登记 141 个成员；后续文档变动另更新 manifest |
| 原生环境 | 单卡 L40，Ubuntu 24.04.4，Isaac `6.0.1-rc.7+release.42383.32955d8d.gl`，ROS Jazzy 和 MCAP 插件；复用已有环境 |
| scene18 依赖 | 实际打开 Stage，26 个 USD 层和 9 个非 USD 资源；普通 USD 检查提示的 `OmniPBR.mdl` 由现有 SDK 内置材料提供 |
| Linux 逻辑与 IPC | 54 项全部通过 |
| Headless owner 连续交互 | 20 轮键控切换、四航向、Pause/Play、Stop 结束和再次录制通过；稳态约 `0.999914×` |
| GUI 连续交互 | 首次启动超时后保留尝试记录；最终真实 GUI 通过同套生命周期检查，稳态约 `1.000157×` |
| 位置与速度 | GUI 和 Headless owner 的物理速度读回最大值均为 0；根位置误差最大约 `4.52e-8 m` |
| 全传感器短采 | 新录制轨迹完成 5 组，13 路雷达、4 路 1920×1080 相机；32 topic、152 条消息、19 条 TF 边，MCAP 70,028,919 字节 |
| 独立回读 | 源时间 0、0.1、0.2、0.3、0.4 s；源位姿、标定、各组 swing 零位、TF 和 writer 消息摘要一致 |
| 实际网页 | HTTP 服务和采集范围选项正常；新录 5.833333 s 轨迹的完整计划为 59 组，未把这个计划称为 59 组已采集 |
| 结束状态 | 网页验证进程、GUI 和 Headless 进程退出，交互 socket 关闭，采集锁释放；原 test 实例资产保留 |

GUI 与 Headless owner 通过项目控制 API 发起操作；实体键盘未在新接收端自动注入。1× 数据来自短测，不能直接外推为任意场景或长时性能。当前接收验收覆盖 scene18 和这套挖机，其他初始资产按 [换场景清单](handoff/SceneSwitchGuide.md) 重新放行。

## 003 完整轨迹采集（2026-10-19，版本 0.3.0）

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| Windows 逻辑及兼容 | 最终套件共 54 项，51 通过、3 项 Linux socket/租约检查跳过；JavaScript 语法通过 | `docs/reports/acceptance_20261019/full_trajectory_local_tests.txt` |
| Linux 同套逻辑 | 54 项全部通过，包含快照重新计划、无 status 时恢复计划和启动失败释放租约 | 最终 `docs/reports/acceptance_20261019/linux_tests.json`、`docs/reports/acceptance_20261019/linux_tests.txt` |
| 实际网页 | 默认完整、隐藏组数、指定 2 组、非法 7 Hz 禁用启动、20 Hz 自动 531 组及 10 Hz 自动 266 组通过；控制台无 error/warn | `docs/reports/acceptance_20261019/full_trajectory_ui.png`、`docs/reports/acceptance_20261019/full_trajectory_ui.json`；本地派生测试轨迹页面，owner 未连接 |
| 完整网格 0.2 s | 自动 3 组；MCAP 源时间为 0、0.1、0.2 s | `docs/reports/acceptance_20261019/full_trajectory_remote_evidence.json` 的 full_grid |
| 非网格尾端 0.25 s | 自动 3 组，最后 0.2 s，不追加 0.25 s 尾帧 | 同上 full_tail |
| 指定最多 2 组 | 保存 2 组，源时间 0、0.1 s | 同上 group_limit |
| 完整模式 Pause/Resume/Stop | 计划 21 组，暂停期间组数稳定，恢复后 Stop，实际排空保存 4 组，completion_reason=stopped_by_user，capture_complete=false | 同上 pause_stop |
| 既有用户轨迹 | 26.5 s、1592 状态的轨迹完整加载通过，10 Hz 自动计划 266 组 | 同上 original_preview；没有执行此轨迹的 266 组全量重采 |

四项真实采集均使用原有 13 路雷达、4 路 1920×1080 相机、32 topic 和 19 条 TF 边，MCAP/CDR/PNG、源状态、标定、各组零位、载荷摘要及源时间独立回读通过；全部任务正常退出并释放资源锁。测试轨迹来自用户已有完整轨迹的明确派生副本，位于输出目录 `test_trajectories/`，未改写用户原轨迹。

本轮只验证本次新增采集范围与生命周期；没有重新执行 GUI 键控/运动长测，也没有以 10 Hz 采样频率声称墙钟实时采集能力。下面保留 002 和 001 历史验证。

交付更新：2026-10-16，北京时间。实例：`isaac-new`，单卡 NVIDIA L40，现有 Isaac/ROS2 Jazzy。下述验证报告保留实际运行时的时间戳，主要验证于 2026-10-15 完成；最终回读结果于 2026-10-16 核实。

## 002 连续交互改进

以下为当前实现的新增验证；后文保留 001 历史结果，旧的 0.1× 条件下性能不代表当前交互性能。

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| Windows 逻辑、HTTP 和生命周期 | 43 项中 42 通过，1 项 Linux socket 平台跳过；Python 编译、JavaScript 语法检查通过 | `docs/reports/acceptance_20261019/continuous_local_tests.txt` |
| 远端 Linux 同套测试 | 43 项全部通过，包含真实 Unix socket 和录制写入失败检查 | `docs/reports/acceptance_20261019/linux_tests.json`、`docs/reports/acceptance_20261019/linux_tests.txt` |
| 实际 GUI 连续交互 | 原生和网页 Play/Pause、20 次模式切换、静止区间原生时间及独立运动标记持续推进、四航向带倾斜平移通过 | `docs/reports/acceptance_20261019/continuous_gui.json` |
| 逐仿真步位置与零速度 | 372 个受控物理步；根线速度、角速度及关节速度读回最大值 0；位置最大误差约 `4.52e-8 m`，关节角约 `5.97e-8 deg` | `docs/reports/acceptance_20261019/continuous_gui.json` |
| Stop、排空和重新绑定 | 原生 Stop 正常完成第一文件；再次 Play 后 Hold，无旧按键及目标恢复；第二次录制新建文件，网页 Stop 正常完成；重复 Stop 幂等 | `docs/reports/acceptance_20261019/continuous_gui.json` |
| 进程退出 | 最终 GUI 测试进程退出码 0，关闭其独立 IPC | `docs/reports/acceptance_20261019/continuous_gui_process.json` |
| 新旧时间语义离线兼容 | 两种完整轨迹分别完成 13 雷达、4 路 1920×1080 相机的 3 组采集，MCAP 独立回读通过；每例 32 topic、92 消息、19 条 TF 边 | `docs/reports/acceptance_20261019/continuous_capture_regression.json` |
| 交付文件与实际网页链路 | 113 个源码/配置/文档文件哈希一致、固定源资产哈希一致；刷新后的实际 HTTP→IPC→Timeline 完成 Play、键控开关、Hold、Stop、重新绑定及 Pause；GUI 最终保持暂停、键控关闭、无录制 | `docs/reports/acceptance_20261019/delivery_v002.json`、`docs/reports/acceptance_20261019/ready_v002.json` |

当前真实 GUI 稳态测量为 `0.9264×`；整个播放区间平均约 `0.9101×`。报告的 `target_1x_met` 使用 0.9–1.1× 作为短测判断范围；1× 是正常交互目标，不保证在任意负载下严格等于 1。稳态测量窗口约 3 个仿真秒，不能作为长时性能置信结论；最长 app 更新间隔包含测试中的 Stop、重新绑定及命令开销，不等于稳定播放时的输入延迟。

定位并修复了两层时间行为：移除交互运行器的原生 Play 回压暂停，同时关闭交互进程中 throttling 扩展在 Play 时重新启用手动固定步进的行为。最终日志显示 app/timeline 使用变化的实际步长，物理时间每次按固定原生步推进，同一画面可包含多个物理步；播放期间手动模式确实关闭。正式 Headless 入口仍使用原有同步固定时钟和冻结采样。

002 的 GUI 检查在真实窗口中通过项目控制 API 注入命令，没有把它称作重新完成 OS 键盘/远程桌面端到端测试。原生焦点、文本阻塞、KEY_REPEAT 和 stale epoch 的逻辑测试通过；原生输入模块继续沿用已验证的键盘接口。加速度未增加估算或状态字段，不把相邻位置差分解释为零物理速度。

首次隔离测试的 socket 路径超过 Unix 限制，随后改用本项目 runtime 下的独立短路径；另一次仅测试用的 app dt 诊断误用 Carb payload.get 参数，已修正并在最终测试中要求收到有效样本。各次尝试保留在远端 `reports/test_attempts/`。最终运行没有这些诊断错误。

其他对象的运动状态尚未记录或重放。独立运动标记只用于证明键控和 Hold 不暂停仿真，未扩大轨迹覆盖范围；后续工作见 002 方案 TODO。

## 001 历史短程验收

| 层次 | 结果 | 本地证据 |
| --- | --- | --- |
| Windows 纯逻辑与 HTTP | 37 项中 36 通过，1 项 Unix socket 平台跳过；Python 编译、JavaScript 语法检查通过 | `docs/reports/acceptance_20261019/local_tests.txt` |
| 远端 Linux 同一套测试 | 37 项全部通过，包含真实 Unix-domain socket、所有权及回执 | `docs/reports/acceptance_20261019/linux_tests.txt`、`docs/reports/acceptance_20261019/linux_tests.json` |
| 原生 Isaac 交互运行器 | 启动 swing=0 核验、20 轮键控开关、同一文件连续录制、四航向倾斜平移通过 | `docs/reports/acceptance_20261019/isaac_acceptance.json` |
| 实际 GUI 原生输入 | OS W 键移动、模式切换后旧重复输入失效、文本编辑不移动、视口恢复后新按下生效 | `docs/reports/acceptance_20261019/gui_input.json` |
| GUI 退出回归 | 运行器关闭后，实际 Kit 进程退出码 0，IPC 已关闭 | `docs/reports/acceptance_20261019/gui_shutdown.json` |
| 完整传感器 Headless 短测 | 13 路雷达、4 路 1920×1080 相机，5 组；MCAP 独立读回通过 | `docs/reports/acceptance_20261019/mcap_validation.json` |
| GUI 退出后的重复任务 | 第 2 组后 Pause，0.6 秒保持组数不变，Resume 到第 3 组，Stop + Drain；退出码 0、锁释放 | `docs/reports/acceptance_20261019/capture_lifecycle.json` |
| 停止后保存内容 | 3 组 MCAP 独立回读通过，源时间为 0、0.1、0.2 s | `docs/reports/acceptance_20261019/lifecycle_mcap_validation.json` |
| 网页浏览器检查 | 实际页面加载无 console error/warning；键控默认关闭；无完整轨迹时禁用正式采集 | 本轮浏览器检查；实际引擎链路另见上述证据 |

## 坐标与零位

纯数学测试覆盖 heading=0°、90°、180°、−90°，非零 pitch/roll，W+A 归一化、相反键抵消、独立 Z/X、W+Q 的先平移后转向、全部关节键位/限位和水平系退化恢复。

实际 Isaac 在 20° pitch、−15° roll 下检查四个航向的 W+A。最大位置误差小于 `3.7e-8 m`；验收容差 `3e-5 m`。启动和录制 snapshot 的 swing 原生角均按已声明的零位核验。真实设备的 cab–track 角仍为 `assumed_zero`。

录制排空后交互进程关闭；正式采集读取任务私有轨迹副本。离线代码已移除 live owner 查询路径，任务快照没有交互 socket 字段。

## 完整采集回读

5 组包含 32 个 topic、152 条消息、19 条 TF 边，MCAP 大小为 70,669,545 bytes。四相机 PNG 解码尺寸均为 1920×1080。所有 topic 组数、写入摘要和逐组源时间一致，源轨迹时间为 `[0, 0.1, 0.2, 0.3, 0.4]` 秒。

- TF 与传感器矩阵最大绝对误差：约 `8.44e-15`。
- 根位置与源轨迹最大误差：约 `5.31e-8 m`。
- 四元数最大误差：约 `2.89e-16`；工作关节误差为 0。
- 每组 frame contract 和 MCAP `/joint_states` 的 swing 零位检查通过。
- 相机标定、光学 frame、雷达局部 XYZ 格式和有限值检查通过。
- 根 USD 哈希保持 `e44ff38c21caaaccf20aa44a9b834e33d7109407e737df27198a63ad95e9fb79`。

图像检查覆盖可解码、尺寸、RGB、非均匀画面和标定。没有将这些检查当作画质主观评审、噪声/曝光优化或长期稳定性验证。

## 性能范围

保留 16 相机预热子帧和 2 正式采集子帧，完整 17 个传感器的短测采集阶段为约 `0.1866 组/真实秒`，5 组及排空共约 `27.24 s`。该阶段计时不含 Kit 启动和场景/传感器初始化，不能据此称为实时 10 Hz。

GUI 测试最近一次引擎收到按键至姿态应用为 `11.658 ms`；153 次更新中主线程最长约 `7.875 ms`。最大更新间隔约 `223.239 ms`，其中包含焦点测试、测试面板创建和 OS 输入自动化开销。这不是浏览器、远程桌面或屏幕呈现的端到端延迟，也不是统计置信的性能基准。

## 排查和未扩大范围

首轮生命周期验证脚本在任务尚未写状态时直接访问 `groups` 导致测试脚本失败；已将起始状态的组数规范为 0 并修正检查。早期 GUI 输入测试通过后，其 Kit 退出过程停在 `os_acquire_rwlock_read`；只对本次创建、身份已核对的 GUI PID 发送 SIGTERM 并确认结束。启动器随后对 GUI 和 Headless 一致设置 fastShutdown 和忽略临时层未保存退出提示；新的 GUI 原生退出回归正常返回 0。记录见 `docs/reports/acceptance_20261019/gui_exit_cleanup.json`，失败的生命周期尝试保留在 `reports/history/`。

本轮没有重启实例、更新驱动、安装新依赖或改写源 USD。交付范围是短程功能及生命周期验收；没有以旧版本长测作为本版验收。
