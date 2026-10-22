# v07 实施与回退记录

日期：2026-10-10；时区：Asia/Shanghai。操作者：当前任务 agent，执行渠道为本地 PowerShell/Python、Skill 审计 SSH 和项目 SFTP 工具。

## 1 目标和范围

用户授权依照 `docs/20261010_dual_gpu_v07_optimization_plan.md` 开始实现，尽可能完整记录日志。仅使用已经迁移的双卡实例 `isaac-dual`，不连接已关闭的单卡源实例。

- 本地新项目：`D:/learning/IntelligentDepartment/CodesSet/Self/260707IsaacSIm/scripts/260920SensorVisualizer/v07`。
- 远端新项目：`/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v07`。
- 正常输出：`/root/gpufree-data/semantic/output/sensor_visualizer/v07`。
- 本次测试：`/root/gpufree-data/semantic/output/sensor_visualizer/v07_validation`。

SSH 通过既有凭据引用认证，认证前校验主机指纹，认证后核对 hostname 与 machine-id 哈希。未重新从聊天提取密码，文档不记录凭据值。

没有下载或安装新的库/工具，没有修改系统 Python、驱动、桌面、SSH、服务、预加载、系统 cgroup 或旧场景 USD。运行 Isaac 产生其正常项目/SDK 缓存；不能因此宣称整个系统所有文件完全未变化。网页继续用现有标准库后端。

## 2 备份和改动

开始前本地保存 `../backups/20261010_162014_v07_baseline/v06_source.zip` 与 manifest；本项目 `baseline_manifest.json` 固定 140 个 v06 源码/配置/文档/工具文件。每次部署重新核对远端这些文件，并创建远端 `../backups/v07_<operation_id>/v06_source.zip`。部署差异保存在 `../deploy_history/v07/<operation_id>/previous_v07.zip`；已有用户差异不会无条件覆盖。

| 顺序 | 动作 | 结果与证据 |
| --- | --- | --- |
| 1 | 复制可复用 v06 逻辑，独立包名、入口、配置和输出 | v07 运行代码独立；保留 v06 可信哈希和备份 |
| 2 | 物理设备解析、CPU 配额/工作池、交互/正式配置分离 | 启动 manifest、CUDA/PCI 映射、原生 Kit 表与 producer 数组设备记录 |
| 3 | 常驻 worker、持久提交、单例/任务锁、复用与显式关闭 | 每轮新会话，兼容场景不重复加载，完成后回到 idle |
| 4 | 扩展诊断、资源监控、控制序号、原生日志和 GC 观察 | bounded 非阻塞落盘；完整性与丢失显式报告 |
| 5 | 同实例基线、headless 功能和 100 组测试 | 数据包独立校验；失败原因和日志保留 |
| 6 | 修复测试暴露的深路径 socket、关节越界、僵尸 PID 问题 | 新版测试覆盖；不修改旧源代码或资产文件 |
| 7 | GUI + HTTP 两轮采集与退出/重建测试 | `20261010_173141` 通过；日志完整 |
| 8 | 增加 GC 明细后的最终短轮 GUI 复核 | `20261010_174511` 通过；2/2 组包及日志校验通过 |
| 9 | 下载日志证据、整理文档、最终源码与进程核验 | `reports/native_runs`、部署清单与最终核验报告；具体 ID 见报告 |

## 3 可追溯操作

每次 SSH 执行保存请求、脚本哈希、脱敏脚本快照、结果和退出码。SFTP 工具保存传输落点、观察哈希、部署/证据清单。本地受限日志位于 `%LOCALAPPDATA%/CloudInstanceOps/audit/20261010/`；桌面应用可能重定向 LOCALAPPDATA，实际位置由工具返回的 `audit_log` 为准。

主要操作 ID（UTC 前缀与正文北京时间不同）：

- `20261010T093141Z_9ab3131a41ea`：已完成包的独立结构/内容校验。
- `20261010T093924Z_2a7ad1d952ae`：headless 长测日志下载。
- `20261010T093924Z_40efe852d97c`：GUI 8/3 组日志下载。
- `20261010T094504Z_28d4e1ffca39`：GC 日志加入后的源码部署，105 文件，当时 v06 哈希未改变。
- `20261010T094905Z_c3c6e09e5060`：所有结束验证的日志和资源汇总。
- `20261010T094918Z_022ba80ad477`：最终 GUI 2/2 组日志下载，122 文件约 28.3 MB，校验一致。

最终部署 ID、文件数与审计日志位置以本地 `reports/deployment/latest.json` 为准。每次更新均保留原操作目录，而非覆盖所有历史证据。

工具记录覆盖本任务通过这些渠道执行的操作；它不是整台实例的网络抓包、不可篡改审计或安全认证。原生 Kit 文本作为内部故障证据保留，外发之前需要按实际内容复查。

## 4 验证边界和回退

完整证据与剩余问题见 [performance_evidence.md](performance_evidence.md)。数据正确性、日志完整性、命令响应和最终屏幕体感分别验收，不能互相替代。

测试结束按已记录 PID、start_ticks 和项目命令行关闭本任务创建的引擎与服务；没有按宽泛名称批量终止 Python/Isaac/桌面进程。最终检查结果见 `reports/final_verification.json`。

回退时先在网页停止并排空 v07 当前任务，Close Idle Capture Service、关闭 v07 交互窗口及网页服务，再按 v06 原启动方式运行。正常回退不需要覆盖 v06；若要恢复特定 v07 改动，可从对应部署的 `previous_v07.zip` 取回匹配文件。不要在运行中的 native 引擎上热覆盖代码。
