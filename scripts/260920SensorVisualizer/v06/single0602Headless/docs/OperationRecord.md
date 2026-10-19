# 云端操作记录

## 003 完整轨迹采集实施

- 时间：2026-10-19，北京时间；工具审计使用 UTC。授权来自用户“现在开始执行实现”，依据已制定的 003 方案。
- 进入任务时通过已配置实例别名核验 SSH 指纹、hostname 和 machine-id；确认本项目无 GUI、网页、采集或验证进程运行，采集锁空闲。
- 本地实现升级为 0.3.0，新增统一有限采集计划、完整/指定范围、只读预览、CLI 互斥选项、快照核验和准确结果展示；保持原传感器、坐标/零位和采集保存链路。
- 远端操作渠道为 cloud-instance-ops 包装器，凭据仍仅用现有 Windows 凭据管理器引用。本次无第三方下载或安装、无系统/驱动/源 USD 改动。
- 首次尝试打包整个项目时脚本超过包装器 256 KiB 上限，执行前被工具策略拒绝；改为明确列举的 16 文件增量批次完成部署，没有修改工具策略。首次有效部署的可恢复覆盖备份为 `reports/deployment_backups/20261019T015628377946Z/`；后续收尾批次各有同类备份。
- Linux 逻辑测试与独立全传感器测试使用本任务进程。实际测试自动派生独立短轨迹，未覆盖用户轨迹；四项任务均通过 MCAP 独立回读、排空、进程退出和租约释放。完整结果保留在远端 `reports/full_trajectory_capture.json` 和本地 `docs/reports/acceptance_20261019/full_trajectory_remote_evidence.json`。
- 26.5 秒用户轨迹的完整模式自动计划为 266 组；本轮没有将短测冒充此轨迹的全量采集。其他对象运动记录仍为 002 TODO。
- 最终交付：Linux 54 项测试全部通过，117 个清单文件和固定源资产哈希核验一致，60 份原来源码仍与移植快照一致。已启动新版网页服务（PID 78621），真实 HTTP 预览返回完整范围 266 组，交互 owner 未连接、无活动采集任务，用户可直接选择已有轨迹采集。
- HTTP 冒烟脚本第一次因包装器敏感文本/URL 规则被执行前拒绝；随后采用结构化的 loopback HTTP 请求并只输出非凭据计划字段，检查通过，未改变工具策略。
- 回退：按审计结果中的覆盖备份恢复本轮修改文件；新增文件可保留为未使用文件。用户轨迹和采集输出不属于源码回退目标；未执行回退演练。

## 002 连续交互实施

- 时间：2026-10-15 18:20 起，北京时间；每次操作的实际起止 UTC 时间见 cloud-instance-ops 本地审计记录。
- 授权：用户确认四项改进决策后，明确要求“依照改进方案开始执行实现”。修改限制在本项目，本轮未更改源 USD、旧 v06、single0601、系统 Python、驱动或实例服务配置，也未下载或安装第三方内容。
- 实现：交互包升级为 0.2.0，采用单一原生 POST_STEP 位置结算及版本化原生时间；原生 Stop 使用末次有效快照结束并排空，重新 Play 绑定实际状态，下一次录制新文件。
- 时序排查：原生安装的 throttling 扩展会在 Play 时重新开启手动固定步进；本项目仅对交互进程禁用该自动切换，使用活动循环正常时间推进，并在关闭时恢复设置。独立正式采集保留同步固定步进、冻结与 keepalive 链路。
- 验证进程：原型、headless owner、真实 GUI、Headless 采集及 ROS 回读均使用本任务创建的独立进程和报告。交互验证输出放在项目输出下 `validation/`，测试 socket 使用本项目 runtime 下的唯一短路径；没有终止用户运行中的 Kit。
- 结果：43 项 Linux 测试全过，Windows 42 项通过及 1 项平台跳过；实际 GUI 20 次切换、Stop/排空/重新绑定、新文件、速度清零和退出通过。正常交互目标 1×，当前场景短程稳态约 0.9264×。新旧完整轨迹的全传感器回读见 `docs/reports/acceptance_20261019/continuous_capture_regression.json`。
- 证据：`docs/reports/acceptance_20261019/continuous_gui.json`、`continuous_gui_process.json`、`continuous_capture_regression.json` 及本地保存的远端证据；各次试验和错误诊断留在远端 `reports/test_attempts/`，不把试验性性能或旧版验收冒充最终结果。
- 回退：差异部署前逐文件保存到远端 `reports/deployment_backups/<UTC>/`。原控制器核心修改前备份为 `20261015T103138056804Z`，启动器修改前备份为 `20261015T103844783210Z`；其他文件按各批记录恢复。新辅助文件可保留为未使用文件，不需要改动系统或源资产。未执行回退演练。
- 2026-10-16 交付：核验 113 个交付文件和固定源资产哈希一致；仅替换已确认归属本项目、无交互引擎连接的旧网页服务，启动全新 0.2.0 GUI。实际网页 HTTP→IPC→原生 Timeline 检查通过，交付时为暂停、键控关闭、物理绑定有效、无录制及排空任务。网页服务已重载，浏览器需刷新以读取新页面状态。具体进程及会话见 `docs/reports/acceptance_20261019/ready_v002.json`。
- 审计脚本记录：首次 HTTP 检查因源文本中的认证字段赋值被包装器敏感字段规则拒绝，未执行远端命令；随后调整为在进程内读取、使用且不输出页面校验值，包装器接受并完成检查，没有改变审计策略或暴露凭据。

## 001 首次实现记录

- 时间与时区：2026-10-15，约 16:18–17:10，北京时间；工具详细记录使用 UTC。
- 任务：依据用户指定的坐标契约和方案实现独立 single0602 项目，并在已连接的单卡实例验证。
- 目标：`isaac-new`；项目 `/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless`。
- 身份依据：认证前核对已保存 SSH 指纹；认证后比对 hostname 和 machine-id SHA256。该核对不构成平台独立身份认证。
- 渠道：本地 Windows 上 cloud-instance-ops 包装器，凭据仅使用 Windows 凭据管理器引用。SSH 探测、部署、启动和回读均经包装器记录；被启动项目的后台进程及 X11 测试有各自报告，不宣称包装器覆盖全部网络或实例活动。
- 授权范围：实现用户指定项目，使用已安装 Isaac/ROS 环境完成必要验证。部署只传本项目生成文件；没有第三方下载批次，没有安装系统软件。
- 操作前：本地目录只有 README 与方案；远端目标目录不存在；scene18 和原生 Kit 已存在。

| 阶段 | 动作 | 结果及证据 |
| --- | --- | --- |
| 接入及基线 | 核验 scene18、mesh contract、swing 原生零位声明及已有依赖 | 根层和资产哈希固定在 `config/asset_profiles.json`；原生 joint `angleZero` 声明保留 |
| 独立移植 | 复制 v06 所需模块并重写包内导入、输出、IPC、网页端口；实现新控制及轨迹契约 | 来源及原始哈希见 `source_provenance.json` |
| 部署 | 对本项目文件逐项 SHA256 校验，更新前保留差异文件备份 | 各次包装器 JSONL；最终清单见 `project_manifest.json` |
| 原生交互 | 新建本项目 Isaac 进程，测试 20 轮混合控制与坐标；完成并排空轨迹 | `docs/reports/acceptance_20261019/isaac_acceptance.json` |
| 独立采集 | 交互进程退出后，运行 Headless keepalive 全传感器短测与系统 ROS 回读 | `docs/reports/acceptance_20261019/mcap_validation.json` |
| GUI 输入与退出 | 只向所建 Kit 窗口注入 OS 键；保留早期退出阻塞证据，正常终止该 PID；修复项目启动器并重新验证退出 | `docs/reports/acceptance_20261019/gui_input.json`、`gui_exit_cleanup.json`、`gui_shutdown.json` |
| 重复生命周期 | 对 GUI 完整轨迹执行 Pause/Resume/Stop/Drain，核验保存及退出/锁释放 | `docs/reports/acceptance_20261019/capture_lifecycle.json`、`lifecycle_mcap_validation.json` |
| 本地回收证据 | 只读传回本项目生成的小型 JSON/text 报告 | `reports/remote_evidence_envelope.json`；不传回秘密、环境变量或全盘业务日志 |

包装器的真实日志根目录为当前应用进程的 `%LOCALAPPDATA%/CloudInstanceOps` 重定向目录；本轮具体路径保存在 `reports/remote_evidence_envelope.json` 的 `audit_log` 字段。记录包含请求、脚本摘要、脱敏结果和退出码；它不是整台实例完整审计。

## 恢复依据

远端首次部署为新目录。后续覆盖前的实际差异备份保存于本项目 `reports/deployment_backups/<UTC 时间>/`，例如 `20261015T083809451612Z`、`20261015T090012685765Z`。没有创建旧 v06 或源资产的系统级备份，因为本轮没有覆盖它们。

回退时先结束本项目轨迹，停止并排空本项目采集，确认进程退出且资源锁释放。需要恢复某次本项目文件时，按备份清单逐项恢复；或直接回到原 v06 入口继续原流程。无需回退驱动、SSH 或系统 Python。本轮没有实际执行文件回退演练。

## 交付结论

本地实现、文件部署校验、原生功能、短程采集、MCAP 独立回读与重复生命周期已验证。旧来源文件是否仍与移植快照一致、最终远端文件是否匹配交付清单，分别记录在来源清单和最终部署核验报告中。传输一致不等于整台主机或任意外部内容可信；本轮验证范围以 Testing 文档所列为准。
