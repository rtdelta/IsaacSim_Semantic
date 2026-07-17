# Isaac Sim 远程免密连接与执行 Prompt

## 使用说明

将本文档中“可直接使用的 Prompt”部分提供给后续 Codex 或其他自动化助手，使其在不读取、不询问和不暴露密码的情况下，连接 Isaac Sim 远程计算机、上传项目文件并运行采集脚本。

## 已配置环境

本地系统：Windows。

远程主机：

```text
HostName: 183.147.142.40
Port: 30745
User: root
SSH alias: isaacsim-gpufree
```

本地专用密钥：

```text
Private key: C:\Users\15452\.ssh\id_ed25519_isaacsim_gpufree
Public key:  C:\Users\15452\.ssh\id_ed25519_isaacsim_gpufree.pub
SSH config:  C:\Users\15452\.ssh\config
```

远端公钥授权文件（数据盘）：

```text
/root/gpufree-data/wyb/RemoteConnection/authorized_keys
```

远端 SSH 服务配置文件：

```text
/etc/ssh/sshd_config.d/00-gpufree-data-authorized-keys.conf
```

配置内容及当前生效值：

```sshconfig
AuthorizedKeysFile /root/gpufree-data/wyb/RemoteConnection/authorized_keys
```

默认授权文件 `/root/.ssh/authorized_keys` 已删除，且不再由 SSH 服务读取。数据盘在实例关机时保留，但释放实例时不保存。

本地 SSH 配置已经包含：

```sshconfig
Host isaacsim-gpufree 183.147.142.40
  HostName 183.147.142.40
  User root
  Port 30745
  IdentityFile ~/.ssh/id_ed25519_isaacsim_gpufree
  IdentitiesOnly yes
```

远端项目目录：

```text
/root/gpufree-data/test_semantic_CustomWriter_260713_01
```

远端项目兼容软链接：

```text
/root/gpufree-data/wyb/test_semantic_CustomWriter_260713_01
```

远端 Isaac Sim 启动入口：

```text
/root/isaacsim/python.sh
```

项目封装启动脚本：

```text
/root/gpufree-data/test_semantic_CustomWriter_260713_01/run_capture_remote.sh
```

## 可直接使用的 Prompt

```text
你正在 Windows 本地工作区操作一台已经配置 SSH 公钥认证的 Isaac Sim 远程计算机。

必须遵守以下连接与执行规则：

1. 始终优先使用 SSH 别名 isaacsim-gpufree，不要在命令中写入密码。
2. 连接时增加 -o BatchMode=yes。公钥认证失败时应直接报告错误，不允许自动等待密码输入。
3. 普通连接验证命令为：
   ssh -o BatchMode=yes isaacsim-gpufree "printf 'key-auth-ok user='; id -un; printf 'host='; hostname"
4. 预期验证结果应包含：
   key-auth-ok user=root
   host=gpufree-container
   如需确认远端实际使用的授权文件，执行：
   ssh -o BatchMode=yes isaacsim-gpufree "/usr/sbin/sshd -T | grep '^authorizedkeysfile '"
   预期结果为：
   authorizedkeysfile /root/gpufree-data/wyb/RemoteConnection/authorized_keys
5. 上传文件时使用：
   scp -o BatchMode=yes <本地文件> isaacsim-gpufree:<远端绝对路径>
6. 下载文件时也必须使用 BatchMode，但只有用户明确要求下载时才允许执行：
   scp -o BatchMode=yes isaacsim-gpufree:<远端文件> <本地路径>

运行 Isaac Sim 时需要特别处理远端登录环境：

7. 不要使用下面这种非交互方式直接启动 Isaac Sim：
   ssh isaacsim-gpufree "<Isaac Sim 启动命令>"
8. 该服务器上直接通过非交互 SSH 启动 Kit 曾在扩展初始化阶段发生 exit code 139。原因是非交互 shell 没有加载完整登录环境。
9. 必须先建立带 PTY 的完整交互式连接：
   ssh -tt -o BatchMode=yes isaacsim-gpufree
10. 成功连接后应确认提示符包含：
    (venv) root@gpufree-container
11. 再通过该交互会话的标准输入发送 Isaac Sim 命令，并持续读取同一个会话的输出。
12. 不要在 Isaac Sim 仍运行时关闭 SSH 会话。
13. 等待日志出现业务完成标志和应用关闭标志，例如：
    [semantic-capture] Complete: <输出目录>
    Simulation App Shutting Down
14. 任务完成并回到 shell 提示符后，发送 exit，正常关闭 SSH 连接。

语义相机项目的通用采集命令模板如下：

/root/gpufree-data/test_semantic_CustomWriter_260713_01/run_capture_remote.sh \
  --usd <USD或语义overlay绝对路径> \
  --mapping <semantic mapping JSON绝对路径> \
  --camera <USD Camera prim路径> \
  --output <新的输出目录> \
  --frames <采集帧数> \
  --delta-time <每帧推进的Timeline秒数> \
  --width 1280 \
  --height 720 \
  --warmup 10 \
  --rt-subframes 4

当前 usd_ply_combined_01 场景可使用：

USD基础文件：
/root/gpufree-data/wyb/StageMaterial/usd_ply_combined_01.usd

语义overlay：
/root/gpufree-data/test_semantic_CustomWriter_260713_01/usd_ply_combined_01_semantic_overlay.usda

mapping：
/root/gpufree-data/test_semantic_CustomWriter_260713_01/semantic_mapping_usd_ply_combined.json

Camera prim：
/root/Xform/track_mesh/Camera_01

运行前必须：

15. 检查目标输出目录是否已经存在，默认不要覆盖已有数据。
16. 检查没有其他 Isaac Sim 或 semantic_capture_custom.py 进程正在占用 GPU。
17. 使用新的、能体现 delta_time 和帧数的输出目录及日志文件名。
18. 用户没有要求时，不下载输出数据，不进行帧间差异统计，不修改 USD 原文件。
19. 如果只是调整采集参数，应复用现有 overlay、mapping、Camera prim 和 Writer，不重新生成无关文件。
20. 最终只报告公钥认证是否成功、实际运行参数、任务是否完成、输出目录和日志路径。

安全约束：

21. 永远不要输出、复制、上传或展示私钥内容。
22. 永远不要把远程密码写入命令、脚本、日志、文档或聊天回复。
23. 远端只使用 /root/gpufree-data/wyb/RemoteConnection/authorized_keys，不要向 /root/.ssh/authorized_keys 写入公钥，也不要把后者重新加入 AuthorizedKeysFile。
24. 增加新公钥时只能向数据盘中的 authorized_keys 追加，并避免重复条目；不要覆盖已有有效公钥。
25. 远端 /root/gpufree-data/wyb/RemoteConnection 权限应为 700，数据盘 authorized_keys 的属主应为 root:root、权限应为 600。
26. SSH 配置文件 /etc/ssh/sshd_config.d/00-gpufree-data-authorized-keys.conf 应只指定数据盘授权文件。修改后必须先执行 /usr/sbin/sshd -t，再 reload SSH，并在保留现有会话的情况下从本地新建 BatchMode 连接验证，避免锁死远端。
27. 如果 BatchMode 连接失败，应先检查本地 SSH 配置、密钥路径、数据盘授权文件、父目录权限和 sshd 生效配置，再向用户报告；不要自动退回密码认证。
28. 数据盘在实例关机时保留，但释放实例时不保存。释放实例前如需迁移密钥，必须先获得用户明确授权。
```

## 常用命令

### 验证免密 SSH

```powershell
ssh -o BatchMode=yes isaacsim-gpufree "printf 'key-auth-ok user='; id -un; printf 'host='; hostname"
```

### 进入 Isaac Sim 运行环境

```powershell
ssh -tt -o BatchMode=yes isaacsim-gpufree
```

预期提示符：

```text
(venv) root@gpufree-container:~#
```

### 免密上传文件

```powershell
scp -o BatchMode=yes "D:\path\to\local_file.py" isaacsim-gpufree:/root/gpufree-data/test_semantic_CustomWriter_260713_01/
```

### 查看公钥指纹

```powershell
ssh-keygen -lf "$HOME\.ssh\id_ed25519_isaacsim_gpufree.pub"
```

当前专用密钥指纹：

```text
SHA256:kuwPP/Az4fk4tCwNM0WaOPjl7I3HZqzMGFRPRQ8UYRE
```

## 故障处理

### 仍然出现密码提示

必须停止当前命令，不要输入密码。使用以下命令进行详细诊断：

```powershell
ssh -vv -o BatchMode=yes isaacsim-gpufree
```

重点确认日志中是否加载：

```text
C:\Users\15452\.ssh\id_ed25519_isaacsim_gpufree
```

### 公钥被远端拒绝

在获得用户授权并通过其他可信登录方式进入远端后，检查：

```bash
namei -l /root/gpufree-data/wyb/RemoteConnection/authorized_keys
stat -Lc '%n owner=%U:%G mode=%a size=%s' /root/gpufree-data/wyb/RemoteConnection/authorized_keys
ssh-keygen -lf /root/gpufree-data/wyb/RemoteConnection/authorized_keys
/usr/sbin/sshd -t
/usr/sbin/sshd -T | grep '^authorizedkeysfile '
```

预期生效路径必须为：

```text
/root/gpufree-data/wyb/RemoteConnection/authorized_keys
```

同时确认目标公钥指纹为 `SHA256:kuwPP/Az4fk4tCwNM0WaOPjl7I3HZqzMGFRPRQ8UYRE`，目录权限为 `700`，文件属主为 `root:root`、权限为 `600`。默认 `/root/.ssh/authorized_keys` 不参与认证，不要把公钥恢复到该位置。不要复制或查看私钥。

### Isaac Sim 在约 1 至 2 秒内退出 139

首先确认是否通过非交互 SSH 命令直接启动。该服务器应先执行：

```powershell
ssh -tt -o BatchMode=yes isaacsim-gpufree
```

进入带 `(venv)` 的远端提示符后，再运行 `run_capture_remote.sh`。不要把 Isaac Sim 启动命令直接作为 `ssh host "command"` 的参数。
