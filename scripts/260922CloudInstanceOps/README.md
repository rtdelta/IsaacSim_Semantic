# 云实例操作与审计工具

面向 AI/人工操作新云实例的本地工具。提供凭据引用、固定主机身份校验、SSH Python 脚本执行、HTTPS 下载核验、外部访问登记和脱敏操作日志。它不是防病毒工具、网络防火墙或操作系统沙箱。

## 运行

仓库提供 `config.example.json`。实际 `config.json` 保存于本机原路径，由 Git 忽略；已有配置不需要改名。首次获取代码时，复制模板为 `config.json` 并填写已核验的主机指纹、实例身份和本机凭据引用，随后再运行工具或安装器。模板占位值不能通过目标策略校验，不会自动连接任何实例。

单元测试使用临时合成配置，不依赖本机实例配置。`install_skill.py` 不会在缺少本地配置时进行部分安装；本轮只更新项目源码，没有执行安装器或修改已安装 Skill。

源码目录：`D:/learning/IntelligentDepartment/CodesSet/Self/260707IsaacSIm/scripts/260922CloudInstanceOps`。

本地已有 Python 3.9.18、Paramiko 2.8.1；本次没有安装或升级依赖。HTTPS 下载、日志、脱敏和 Windows 凭据管理使用标准库；SSH 使用现有 Paramiko。其版本较旧，是否升级应另做兼容性评估。

从此目录运行：

```powershell
& 'D:\Anaconda3\python.exe' -X utf8 ops.py status
& 'D:\Anaconda3\python.exe' -X utf8 ops.py probe --target isaac-new --task example --purpose 'Verify target identity'
& 'D:\Anaconda3\python.exe' -X utf8 ops.py exec --target isaac-new --task example --purpose 'Read project directory state' --script examples\inspect_project.py --intent read --timeout 30
& 'D:\Anaconda3\python.exe' -X utf8 ops.py verify
```

SSH 密码没有放在源代码、配置或本次工具日志中；从此前用户已提供的连接信息一次性迁入当前用户的 Windows 凭据管理器。引用名为 `CloudInstanceOps/isaac-new/ssh`。这是本地保存方式变更，没有修改远端密码、authorized_keys 或 sshd。已有明文历史记录未删除，凭据尚未轮换。

后续更换凭据，在交互式本地终端执行：

```powershell
& 'D:\Anaconda3\python.exe' -X utf8 ops.py credential-set --target isaac-new --task maintenance --purpose 'Enroll updated SSH credential'
```

命令会隐藏输入，不接受密码参数。当前实例未接受现有公钥，因此仍使用凭据管理器中的密码认证。密钥方式可在配置中选择 `auth: key` 和 `identity_file`；本次没有安装远端公钥。

## 下载和外部访问

```powershell
# 期望哈希来自已审阅的锁定清单或可信发行资料。
& 'D:\Anaconda3\python.exe' -X utf8 ops.py download --task example --purpose 'Obtain reviewed artifact' --url https://allowed-host/path/file.whl --filename file.whl --sha256 EXPECTED_SHA256

# 首次留存公开资料，仅计算观察值，不声称内容可信。
& 'D:\Anaconda3\python.exe' -X utf8 ops.py download --task example --purpose 'Keep official documentation' --url https://pip.pypa.io/en/stable/topics/secure-installs/ --filename pip-secure-installs.html --observe-hash

# 登记浏览工具中的已发生访问；此命令本身不联网。
& 'D:\Anaconda3\python.exe' -X utf8 ops.py access-note --task example --purpose 'Consult official documentation' --surface browser_tool --activity documentation --url https://pip.pypa.io/en/stable/topics/secure-installs/ --reference ACTUAL_TOOL_CALL_REFERENCE
```

只允许配置中精确域名、HTTPS/443；每次重定向重新校验，TLS 证书正常验证。第一版不接受 URL query/fragment、内嵌账号密码或私有地址解析结果，不继承环境 HTTP 代理。默认下载上限 200 MiB、120 秒；文件名限定为普通文件名，落点由工具生成，不覆盖已有文件、不解包、不执行内容。私有认证下载和自动包安装不在第一版功能内。

允许域名不是可信仓库认证；发布者本身可能受入侵，wheel 也可能含恶意代码。首次下载现算哈希只证明该文件的内容指纹，不证明安全。SSH 脚本内部的 pip/curl 或库自动下载不经过本下载器，必须另外记录来源，不能算作已经被拦截或全面审计。

## 数据组织与权限

默认状态根目录为 `%LOCALAPPDATA%/CloudInstanceOps`。Codex 的 Windows 打包环境可能将其重定向到包的 `LocalCache/Local/CloudInstanceOps`；`status`、每次命令的 `audit_log` 字段显示解析后的真实目录。

```text
CloudInstanceOps/
  .cloud-instance-ops-state     本工具目录标记
  audit/YYYYMMDD/
    OPERATION_ID.jsonl          操作起止、连接、执行、下载等事件
    OPERATION_ID.script.txt     已审阅脚本的脱敏快照
  staging/                     本次下载的临时文件；失败时只清理自己的文件
  downloads/                   UUID 前缀的下载产物
```

工具仅为自身状态根目录设置当前 Windows 用户和 SYSTEM 的访问权限，不修改工程目录或远端目录权限。日志不自动同步到云实例或第三方。需要独立不可改写留存时，另外配置可信日志接收端；目前本地哈希链只能校验现存记录，不能抵抗同用户完整重写、删除。

每条事件包括操作 ID、UTC 时间、顺序号、事件类型和脱敏数据。开始记录先落盘并 flush/fsync，然后执行；结果包含退出码。超时/断线标记 unknown，不自动重试，不断言远端进程停止。单流输出超过 1 MiB 会完全省略，防止截断泄露秘密值前缀。

## 模块

- `cloud_ops/security.py`：Windows 凭据、目标策略、脱敏、状态目录权限。
- `cloud_ops/ssh.py`：认证前校验主机指纹、认证后校验实例身份、执行与超时语义。
- `cloud_ops/download.py`：来源与重定向校验、TLS、流量限制、SHA256 和下载落盘。
- `cloud_ops/audit.py`：每次操作的 JSONL、脚本快照及一致性验证。
- `cloud_ops/cli.py`：统一入口与结果格式。
- `skill/cloud-instance-ops/`：更新后的 Skill 源码；`install_skill.py` 安装 Skill 和工具副本并保存变更清单。

## 使用边界

`--intent read/write/diagnostic` 是操作意图声明，不会把 Python 变成只读沙箱。当前以 root 连接，也没有安装出口控制、全局审计或杀毒。AI 拥有任意 shell 或同用户文件权限时仍能绕过包装器。凭据管理器也不是对同用户恶意程序的隔离。

脱敏覆盖已加载凭据原文及 URL/JSON 转义、常见秘密字段、认证头、私钥、常见 token；不能识别所有编码、无标签或业务自定义秘密。因此先限制读取范围，敏感数据处理尽量在本地完成，只返回必要摘要。带业务敏感信息的脚本本身也不应作为日志快照输入。

本工具不自动记录其他人的 SSH、客服操作、外部浏览器、后台进程或所有网络连接。`access-note` 明确标注为人工/AI 登记，不伪装成独立流量证据。状态字段 succeeded 仅指指定操作返回成功，不表示实例无病毒。

## 验证、维护与回退

```powershell
& 'D:\Anaconda3\python.exe' -X utf8 -m unittest discover -s tests -v
& 'D:\Anaconda3\python.exe' -X utf8 install_skill.py
```

每次修改工具源码后重新运行适当测试和安装器；安装器只同步本项目管理的文件，不清理整个 Skill。原 Skill 完整备份在 `backups/cloud-instance-ops-before/`，每次安装覆盖的文件还单独保存。安装清单在 `reports/skill_install_*.json`。

需要回退时，按安装清单恢复备份中的对应文件，并移除清单里本次新建、确认没有用户修改的工具文件；不要递归删除整个 Skill。取消使用工具不等于删除历史凭据，凭据记录可由用户在 Windows 凭据管理器单独移除。

参考依据：
- https://pip.pypa.io/en/stable/topics/secure-installs/
- https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html

## 报告与验收证据

正式报告、精选验收摘要和必要配图见 [报告索引](docs/reports/README.md)。原始采集、逐帧状态和性能追踪保留在原运行目录，由仓库忽略规则排除。
