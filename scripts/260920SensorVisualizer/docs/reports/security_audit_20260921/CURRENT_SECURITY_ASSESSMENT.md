# 新实例与本地 Windows 安全状态复核

检查时间：2026-09-21 19:47–19:55（北京时间）。

结论：两端本轮检查均未发现能够确认感染的直接证据，但不能据此证明不存在恶意软件、历史入侵或信息泄露。本轮为有限范围的在线只读检查，没有运行完整杀毒扫描或离线取证。

## 新云实例

- 目标：120.209.70.195:30729。连接前核对既存 SSH 主机指纹，连接后核对 machine-id 的 SHA-256，与此前新实例记录一致。未连接已经释放的旧实例。
- 19:53 复查旧实例的 12 个已知路径指标，包括 `.libproc.so`、`.dpkg-triggers-2890`、`polkitdl`、`nvidian-smi`、`/tmp/sh.0` 等，普通访问和直接系统调用均未发现这些路径。
- 检查的进程映射未出现上述恶意组件特征；/proc 及另外五个目录的普通枚举与直接 getdents64 枚举未出现隐藏差异。在线系统调用比较仅针对此前用户态隐藏机制，不能排除其他未知或内核层威胁。
- /etc/ld.so.preload 仍为此前新实例基线中的 libblock_nvidia.so 和 libnvenc_fix.so，普通读取与直接系统调用结果一致。与基线一致不等于对这些库完成独立安全审计。
- **确认的访问控制问题**：Jupyter 启动参数将 token 和 password 设为空；使用正确 base_url 从实例本机不带认证请求目录元数据，得到 HTTP 200。仅请求元数据，未创建终端、内核或执行 notebook。平台公网网关和跨租户网络是否阻止未授权访问，本轮未验证；不能直接宣称公网裸露，也不能认定已被利用。若应用不做认证，需要其他层提供可靠的认证或访问限制。
- auth.log、secure、wtmp、btmp 和 /var/log/journal 均不存在，无法凭这些文件追溯历史登录。容器环境下日志缺失本身不证明被恶意删除，需要平台侧日志补充。
- 未对全部迁移资产、代码、依赖与磁盘内容做恶意软件扫描。

证据：new_instance_refresh.json；此前同日的 baseline.json、access_and_startup.json、targeted_integrity_and_services.json。

## 本地 Windows

- 安全中心注册卡巴斯基；AVP21.26 服务 Running / Auto，avp.exe 和 avpui.exe 进程存在。
- 磁盘上的卡巴斯基 avp.exe、wmiav.exe、upgrade.exe 数字签名有效。签名验证不能证明所有运行组件和配置都安全。
- Windows Defender 未运行。安装其他防病毒软件时 Defender 可以进入停用或其他兼容模式；当前状态本身不是病毒证据，也不能据其空检测列表推断没有病毒。
- 最近 30 天 Defender 1116/1117 检测、处置事件查询无匹配项；Kaspersky Event Log 记录数为零。卡巴斯基自己的 Report 目录存在，但本轮只查看文件元数据，未解析其完整扫描、检测与隔离记录，也未核实各实时保护模块或数据库是否已是最新。
- 查看了常见 Run / RunOnce 注册表启动项、两个 Startup 目录，以及非 Microsoft 任务目录中的计划任务。未在这些输出中识别出明确恶意命令，但未逐一验证全部程序、脚本和 COM 任务内容，因此这不是完整的持久化审计。
- 此前重启调查确认 0x18 蓝屏；尚未读取受保护的转储并归因，蓝屏本身不能证明感染，也不能证明无感染。

证据：windows_protection.json、windows_av_runtime.json、windows_startup.json、windows_av_reports_metadata.json。

## 提高确认程度的后续工作（未执行）

1. 新实例：请平台核实 Jupyter 入口认证、跨租户网络隔离以及平台保存的登录/访问日志；按核实结果另行制定认证和访问限制变更。
2. 本地：在卡巴斯基中确认保护状态、病毒库与更新结果，运行完整扫描并保存扫描及检测报告。若发现可疑项，再依据证据安排离线检查；扫描可能执行处置，因此本轮未擅自启动。
3. 源自旧实例的可执行代码和依赖优先对照可信本地版本及可信发行源，不能把文件传输校验等同于恶意软件检查。

本轮没有安装软件、修改远端或 Windows 配置、停止进程、隔离或删除文件；只在本地项目内保存检查结果。在线查看可能产生连接或访问日志。

参考：
- https://jupyter-server.readthedocs.io/en/latest/operators/security.html
- https://learn.microsoft.com/en-us/defender-endpoint/microsoft-defender-antivirus-compatibility
