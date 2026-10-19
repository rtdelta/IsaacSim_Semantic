# 本地 Windows 重启排查

采集时间：2026-09-21 19:35—19:38，北京时间。对象为本地 Windows 11，用户明确排除了云实例。本轮未连接云端，未修改系统设置、驱动或软件，未安装工具；仅在项目目录保存检查结果。

## 已确认

- WMI LastBootUpTime：2026-09-21 19:12:56.500。
- EventLog 6008：上次意外关机时间为 2026-09-21 19:10:57。
- System / WER-SystemErrorReporting 1001（RecordId 428500）：系统发生检测错误后重新启动，BugCheck 0x00000018。
- 参数：0x0、0xffffb508f7294080、0x2、0xfffffffffffffffe。
- 系统记录的转储路径：C:\WINDOWS\Minidump\092126-14875-01.dmp。
- 报告 ID：33d1ae3f-d64e-4623-b85f-ce1aa12b49ad。
- Application WER 1001 也明确记为 BlueScreen。
- Kernel-Power 41 的 BugcheckCode=24，即十六进制 0x18。PowerButtonTimestamp=0、LongPowerButtonPressDetected=false；这些字段不能替代完整硬件诊断。
- 受查近两天相关事件中未见 USER32 1074 主动重启记录。因此已知直接机制是系统崩溃后重新启动，尚未识别具体责任应用或驱动。

## 错误含义与界限

微软将 0x18 定义为 REFERENCE_BY_POINTER：对象引用计数与当前状态不一致，典型原因是驱动错误地减少引用计数。需要转储调用栈、相关模块和对象状态才能进一步归因。

官方说明：https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/bug-check-0x18--reference-by-pointer

崩溃前一小时可见 Schannel TLS 错误和 DCOM 权限警告；尚无证据把它们与本次 0x18 建立因果关系。重启后出现 TsQBDrv、服务超时、应用初始化等警告，发生在新系统启动后，不能仅凭时间邻近把其中的软件认定为肇因。

没有证据将本次本地蓝屏与旧云实例的 Linux 恶意脚本建立联系，也不能据此认定本地无任何恶意软件。

## 当前阻碍

Windows 拒绝当前进程读取 Minidump 文件及对应 WER ReportQueue 内容。错误同时附带 Cannot find path，但首要错误为 Access denied，不能据此声称转储丢失。未改变 ACL、接管所有权、绕过权限或启动提权程序。

继续分析需要用户以管理员身份复制该转储到当前用户可读的项目目录。只需副本，不删除或修改原文件；转储保留本地，不需上传外部服务。

## 证据文件

- system_restart_events.json：系统启动、意外关机、BugCheck 等。
- crash_window_events.json：启动前后系统与应用事件。
- pre_crash_events.json：重启前一小时警告/错误。
- kernel_power_event.xml：Kernel-Power 原始事件字段。
