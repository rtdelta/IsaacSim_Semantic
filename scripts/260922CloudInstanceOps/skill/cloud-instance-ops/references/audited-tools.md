# 审计工具使用

本 Skill 附带 `scripts/ops.py`、`scripts/cloud_ops/` 和不含秘密值的 `scripts/config.json`。当前开发源码位于：

`D:/learning/IntelligentDepartment/CodesSet/Self/260707IsaacSIm/scripts/260922CloudInstanceOps`

可用解释器：`D:/Anaconda3/python.exe`，已安装 Paramiko。只在需要 SSH 功能时导入它。不要为使用本工具顺便升级全局 Python 或 Paramiko。

## 当前配置

- 实例别名 `isaac-new`，只包含用户已授权的新实例。旧实例已经释放，工具配置不包含旧目标。
- SSH 主机指纹在认证前验证，认证后比对已记录的 hostname 与 machine-id SHA256，再执行项目命令。它们不是平台独立证明，克隆/平台复用仍需结合实例生命周期确认目标。
- 密码存放在当前 Windows 用户的凭据管理器中，工具只使用引用 `CloudInstanceOps/isaac-new/ssh`。密钥认证也支持：配置 `auth: key`、`identity_file`，可选 `passphrase_ref`；没有 agent forwarding，也不自动尝试任意密钥。
- 状态默认在当前进程的 `%LOCALAPPDATA%/CloudInstanceOps`，Windows 打包应用可能重定向目录。运行 `status` 或使用结果中的 `audit_log` 获取真实位置。

## 命令

以下把 `<ops.py>` 替换为此 Skill 的 `scripts/ops.py` 完整路径；全局 `--config`、`--state` 参数须放在子命令之前。

```powershell
& 'D:\Anaconda3\python.exe' -X utf8 '<ops.py>' status
& 'D:\Anaconda3\python.exe' -X utf8 '<ops.py>' probe --target isaac-new --task TASK_ID --purpose 'Verify instance identity'
& 'D:\Anaconda3\python.exe' -X utf8 '<ops.py>' exec --target isaac-new --task TASK_ID --purpose 'Read relevant project state' --script 'D:\path\reviewed_probe.py' --intent read --timeout 30
& 'D:\Anaconda3\python.exe' -X utf8 '<ops.py>' download --task TASK_ID --purpose 'Obtain pinned dependency' --url 'https://allowed-host/path/file.whl' --filename file.whl --sha256 EXPECTED_SHA256
& 'D:\Anaconda3\python.exe' -X utf8 '<ops.py>' verify
```

- `exec` 接受审阅过的 UTF-8 Python 脚本，使用 SSH stdin 运行 `python3 -I -S -B -`，默认工作目录是实例配置中的 workspace。脚本必须自行限定副作用；`--intent read` 是记录声明，不是只读沙箱。不要把无关环境或完整敏感文件打印出来。运行 Isaac 解释器等任务需在脚本中显式选择已确认的程序和项目路径。
- 不提供命令行密码参数。凭据需要更新时，在用户可控制的交互式本地终端运行 `credential-set --target isaac-new --task TASK_ID --purpose 'Enroll SSH credential'`，按隐藏提示输入；本命令不改变远端密码。
- `download` 默认必须提供期望 SHA256。只为留存资料或首次检查，可显式用 `--observe-hash`，结果会标记未验证，文件不会执行。第一版不接收带 query/fragment 的 URL，避免签名链接和 token 进入 CLI；需要认证下载时扩展凭据引用流程，不能把秘密放在 URL。
- 下载仅允许 HTTPS/443 与配置中的精确域名；每次重定向也检查。允许 GitHub 域名不代表认可其中所有仓库。未配置来源需要核实并更新来源配置，不自动跟随未知 CDN。HTTP 环境代理默认不继承，不关闭 TLS 验证。
- `access-note --surface browser_tool|local_windows|remote_linux --activity documentation|search|download|upload|other --url URL --reference EVIDENCE_ID --task TASK_ID --purpose REASON` 只登记已发生且有依据的外部访问，不执行网络请求。对搜索只保存去敏后的目的及必要地址，避免把私有查询复制到日志。

## 审计与失败处理

- 每次操作一个 JSONL：开始、连接/认证/身份、执行或下载、结果。保留操作 ID、UTC 时间、用途、目标、策略哈希、脚本哈希及脱敏输出。脚本快照另存脱敏文本；验证器同时检查它的哈希。
- stdout/stderr 先在内存收集和脱敏再记录/返回。单个输出流超过 1 MiB 时整段不输出，防止截断到秘密值中间；其字节数和省略标志仍记录。
- 下载时只创建本次 UUID 的 `.part`；失败只清理该临时文件，不删除现有下载，也不覆盖同名用户文件。下载不会解包、导入或运行。
- SSH 超时或请求后的断线标记 unknown；工具关闭连接，不声称远端进程已结束，也不自动重试、不按进程名批量停止。
- `verify` 检查现有日志和脚本快照的一致性，未结束的操作返回非零。它不能发现被整个删除的日志，不能抵抗拥有同用户写权限者重算哈希链。需要强审计时另行部署独立日志收集端。

## 边界

外部下载清单的用户确认由执行此 Skill 的 agent 在调用工具前落实，并在用途或关联记录中标明对应批次。当前 CLI 不提供确认弹窗，也不验证聊天中的批准状态；域名允许清单和哈希校验不能替代用户对具体下载批次的确认。

工具没有接管系统网络、所有 shell 或后台进程；没有改变 SSH 服务、桌面、Jupyter、防火墙或系统包。非包装器操作要准确注明覆盖缺口。DNS 检查和域名清单不能替代进程级出口隔离，不能声称防住 DNS 重绑定。当前仍以实例配置中的 root 登录，凭据管理器减少秘密传播但不降低远端执行权限；同一 Windows 用户下的恶意程序也可能访问凭据。

脱敏不能识别任意无标签、编码或业务专用的秘密。秘密已进入模型或旧记录后，后续脱敏无法撤回；轮换和历史记录处置应另按授权开展。
