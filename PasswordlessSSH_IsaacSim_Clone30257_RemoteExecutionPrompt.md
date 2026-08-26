# Isaac Sim 克隆实例免密连接与远程执行 Prompt

## 使用说明

本文档适用于 2026-08-12 验证过的 Isaac Sim 克隆实例。把“可直接使用的 Prompt”部分交给后续 Codex 或自动化助手，即可使用本地专用 SSH 密钥连接该实例并执行任务。

本文档不保存远程登录密码。后续始终优先使用已验证的公钥认证；公钥认证失败时应停止并报告，不得自动退回密码认证。

## 已验证连接信息

```text
HostName: 183.147.142.40
Port: 30257
User: root
SSH alias: isaacsim-gpufree-clone30257
Remote hostname: gpufree-container
```

本地专用密钥：

```text
Private key: C:\Users\15452\.ssh\id_ed25519_isaacsim_gpufree
Public key:  C:\Users\15452\.ssh\id_ed25519_isaacsim_gpufree.pub
SSH config:  C:\Users\15452\.ssh\config
Public-key fingerprint: SHA256:kuwPP/Az4fk4tCwNM0WaOPjl7I3HZqzMGFRPRQ8UYRE
```

本地 SSH 配置：

```sshconfig
Host isaacsim-gpufree-clone30257
  HostName 183.147.142.40
  User root
  Port 30257
  IdentityFile ~/.ssh/id_ed25519_isaacsim_gpufree
  IdentitiesOnly yes
```

远端公钥授权文件位于数据盘：

```text
/root/gpufree-data/wyb/RemoteConnection/authorized_keys
```

远端 SSH 服务配置：

```text
/etc/ssh/sshd_config.d/00-gpufree-data-authorized-keys.conf
```

当前生效值：

```sshconfig
AuthorizedKeysFile /root/gpufree-data/wyb/RemoteConnection/authorized_keys
```

已验证权限：`RemoteConnection` 为 `root:root`、模式 `700`；`authorized_keys` 为 `root:root`、模式 `600`。不要把公钥写回 `/root/.ssh/authorized_keys`。

远端 ED25519 主机密钥指纹：

```text
SHA256:kIfeVQ2EQsdiXEPSocGzqmCzv3sOWkAQPMRY8owqnbU
```

## 当前远端工作负载

Isaac Sim 启动入口：

```text
/root/isaacsim/python.sh
```

当前建议使用的项目：

```text
/root/gpufree-data/repositories/260811_01semantic_worldModule_v02
```

项目封装启动脚本：

```text
/root/gpufree-data/repositories/260811_01semantic_worldModule_v02/run_capture_remote.sh
```

该脚本只接受 `--config <capture-config.json>`，并把 HOME、临时目录、Kit/Omniverse 缓存放到项目数据盘下的 `.runtime`，可避免继续挤占 30 GB 系统盘。

旧提示词中的以下项目入口在克隆实例上已经失效，不得继续使用：

```text
/root/gpufree-data/test_semantic_CustomWriter_260713_01
/root/gpufree-data/wyb/test_semantic_CustomWriter_260713_01
```

第二个路径仍是软链接，但其目标 `/root/gpufree-data/repositories/test_semantic_CustomWriter_260713_01` 不存在。

克隆实例上另有一个仍存在的旧版项目：

```text
/root/gpufree-data/repositories/260714_01semantic_worldModule
```

除非用户明确要求复现旧版任务，否则优先使用 `260811_01semantic_worldModule_v02`。运行前必须读取目标配置 JSON，确认 USD、mapping、Camera、输出目录、帧数和渲染参数，而不是沿用旧提示词里的参数。

## 可直接使用的 Prompt

```text
你正在 Windows 本地工作区操作一台已经配置 SSH 公钥认证的 Isaac Sim 克隆实例。

必须遵守以下连接规则：

1. 始终优先使用 SSH 别名 isaacsim-gpufree-clone30257，不要在命令、脚本、日志、文档或回复中写入密码。
2. 所有非交互式 SSH/SCP 命令都增加 -o BatchMode=yes。公钥认证失败时直接报告错误，不得等待密码输入或自动退回密码认证。
3. 普通连接验证命令：
   ssh -o BatchMode=yes isaacsim-gpufree-clone30257 "printf 'key-auth-ok user='; id -un; printf 'host='; hostname"
4. 预期结果包含：
   key-auth-ok user=root
   host=gpufree-container
5. 如需确认远端授权文件，执行：
   ssh -o BatchMode=yes isaacsim-gpufree-clone30257 "/usr/sbin/sshd -T | grep '^authorizedkeysfile '"
   预期结果：
   authorizedkeysfile /root/gpufree-data/wyb/RemoteConnection/authorized_keys
6. 上传文件：
   scp -o BatchMode=yes <本地文件> isaacsim-gpufree-clone30257:<远端绝对路径>
7. 只有用户明确要求下载时才执行：
   scp -o BatchMode=yes isaacsim-gpufree-clone30257:<远端文件> <本地路径>

运行 Isaac Sim 时必须遵守：

8. 运行前先执行 df -h /，并确认系统盘有足够空间；同时确认没有其他 Isaac Sim、Kit 或 semantic_capture 进程占用 GPU。
9. 默认先建立带 PTY 的完整交互式登录：
   ssh -tt -o BatchMode=yes isaacsim-gpufree-clone30257
10. 进入远端 shell 后，再在同一会话中启动 Isaac Sim，并持续读取该会话输出；Isaac Sim 运行期间不得关闭 SSH 会话。
11. 当前优先项目为：
    /root/gpufree-data/repositories/260811_01semantic_worldModule_v02
12. 当前启动脚本为：
    /root/gpufree-data/repositories/260811_01semantic_worldModule_v02/run_capture_remote.sh
13. 启动命令模板：
    /root/gpufree-data/repositories/260811_01semantic_worldModule_v02/run_capture_remote.sh \
      --config /root/gpufree-data/repositories/260811_01semantic_worldModule_v02/configs/<目标配置.json>
14. 启动脚本只接受 --config。先读取配置 JSON，并逐项报告实际 USD、mapping、Camera Prim、输出目录、frames、分辨率、physics_hz、capture_fps、renderer、warmup_render_frames 和 rt_subframes；不要使用旧项目的命令行参数模板。
15. 项目会把运行期 HOME、TMPDIR、XDG cache、CUDA cache 和 OptiX cache放到项目数据盘的 .runtime 目录。不要改回 /root/.cache、/root/isaacsim/kit/cache 或 /tmp，以免再次写满系统盘。
16. 运行前检查输出目录；默认不覆盖已有数据。只调整采集参数时复用现有项目、USD、mapping、Camera 和 Writer，不生成无关文件。
17. 等待业务完成标志与 Simulation App 关闭标志。任务结束并返回 shell 提示符后发送 exit，正常关闭 SSH 连接。
18. 用户未明确要求时，不下载输出数据，不进行额外统计，不修改源 USD。

克隆实例的路径约束：

19. 不得使用已失效的 /root/gpufree-data/test_semantic_CustomWriter_260713_01。
20. /root/gpufree-data/wyb/test_semantic_CustomWriter_260713_01 是断开的旧软链接，也不得使用。
21. 除非用户要求复现旧版，否则使用 /root/gpufree-data/repositories/260811_01semantic_worldModule_v02；若用户指定其他项目，以实际存在并经检查的路径为准。

安全约束：

22. 永远不要输出、复制、上传或展示私钥内容。
23. 永远不要把远程密码写入命令、脚本、日志、文档或聊天回复。
24. 远端只使用 /root/gpufree-data/wyb/RemoteConnection/authorized_keys；不要向 /root/.ssh/authorized_keys 写入公钥，也不要把后者加入 AuthorizedKeysFile。
25. 新增公钥时只能去重后追加到数据盘 authorized_keys，不得覆盖已有有效公钥。
26. 修改 SSH 服务配置后，先执行 /usr/sbin/sshd -t，再 reload SSH；保留当前会话，并从本地新建 BatchMode 连接验证，避免锁死远端。
27. 不得删除 /root/isaacsim、CUDA、Torch、NVIDIA 驱动库或系统软件。清理系统盘时只处理经确认的缓存、历史日志和临时测试残留，并在删除前获得用户明确授权。
```

## 常用命令

验证免密 SSH：

```powershell
ssh -o BatchMode=yes isaacsim-gpufree-clone30257 "printf 'key-auth-ok user='; id -un; printf 'host='; hostname"
```

进入交互式 Isaac Sim 运行环境：

```powershell
ssh -tt -o BatchMode=yes isaacsim-gpufree-clone30257
```

查看两个存储卷：

```powershell
ssh -o BatchMode=yes isaacsim-gpufree-clone30257 "df -hT / /root/gpufree-data"
```

查看公钥指纹和 SSH 生效配置：

```powershell
ssh -o BatchMode=yes isaacsim-gpufree-clone30257 "ssh-keygen -lf /root/gpufree-data/wyb/RemoteConnection/authorized_keys; /usr/sbin/sshd -T | grep '^authorizedkeysfile '"
```

## 故障处理

### 公钥认证失败

从本地执行：

```powershell
ssh -vv -o BatchMode=yes isaacsim-gpufree-clone30257
```

确认加载的是 `C:\Users\15452\.ssh\id_ed25519_isaacsim_gpufree`，然后通过用户明确授权的可信登录方式检查：

```bash
namei -l /root/gpufree-data/wyb/RemoteConnection/authorized_keys
stat -Lc '%n owner=%U:%G mode=%a size=%s' /root/gpufree-data/wyb/RemoteConnection/authorized_keys
ssh-keygen -lf /root/gpufree-data/wyb/RemoteConnection/authorized_keys
/usr/sbin/sshd -t
/usr/sbin/sshd -T | grep '^authorizedkeysfile '
```

不得自动退回密码认证，不得查看或复制私钥。

### 系统盘空间不足

先确认没有正在运行的 Isaac Sim/Kit 进程，再统计 `/root/.cache/ov`、`/root/.nvidia-omniverse/logs`、`/root/isaacsim/kit/cache`、`/root/isaacsim/kit/logs` 和 `/tmp`。删除属于破坏性操作，必须先向用户报告候选路径、占用、影响和预计可回收空间，并取得明确授权。

