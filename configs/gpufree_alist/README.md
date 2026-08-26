# GPUFree AList 自动挂载配置

## 目标

本配置将远端 GPUFree 实例中的 AList 数据自动挂载到本地 Windows，并在登录后自动启动和断线重连。

数据链路：

```text
远端 /root/gpufree-data
  → AList WebDAV 127.0.0.1:5244
  → SSH 隧道 127.0.0.1:15244
  → rclone WebDAV
  → 本地 Y:（GPUFree_AList）
  → 本配置目录中的 GPUFree AList.url
```

## 为什么使用 Y: 而不是直接挂到 Z: 子目录

`Z:` 当前是映射到 `\\192.168.71.34\Public` 的 SMB 网络盘。WinFsp/rclone 不适合在一个网络共享的子目录中再次嵌套挂载文件系统，因此使用独立盘符 `Y:`。此外，服务器拒绝在 `Z:\SimluationData` 创建快捷入口，因此快捷入口保存在本配置目录中，日常直接打开 `Y:` 即可。

## 文件说明

| 文件 | 用途 |
|---|---|
| `gpufree_alist.json` | SSH、端口、挂载点、缓存和重试参数 |
| `rclone.conf` | AList WebDAV 连接配置 |
| `Start-GPUFreeAListMount.ps1` | 自动启动、监控和断线重连管理器 |
| `Stop-GPUFreeAListMount.ps1` | 停止自动管理器、SSH 隧道和 rclone 挂载 |
| `Install-GPUFreeAListTask.ps1` | 注册 Windows 登录自动启动并立即运行 |
| `Uninstall-GPUFreeAListTask.ps1` | 移除自动启动，不删除配置或日志 |
| `installation_status.json` | 安装脚本运行后生成的注册结果 |

## 当前配置

```text
远端主机：183.147.142.40
SSH端口：30549
SSH用户：root
SSH密钥：%USERPROFILE%\.ssh\id_ed25519_isaacsim_gpufree
远端AList目录：/root/gpufree-data/alistgo
远端AList端口：5244
本地隧道端口：15244
rclone远端：alist:/gpufree-data
本地挂载点：Y:
快捷入口：本配置目录中的 `GPUFree AList.url`
```

## 安装

在普通 PowerShell 中执行：

```powershell
Set-Location "D:\learning\IntelligentDepartment\CodesSet\Self\260707IsaacSIm\configs\gpufree_alist"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Install-GPUFreeAListTask.ps1"
```

安装脚本优先注册任务计划 `GPUFree AList Auto Mount`。如果当前账户没有任务计划注册权限，则自动回退到当前用户的 `HKCU Run` 登录启动项。

## 日常使用

Windows 登录后，等待约 10～30 秒，然后打开：

```text
Y:\
```

或者打开：

```text
D:\learning\IntelligentDepartment\CodesSet\Self\260707IsaacSIm\configs\gpufree_alist\GPUFree AList.url
```

不再需要手动保留 SSH 或 rclone PowerShell 窗口。

## 手动启动（前台观察日志）

先停止后台实例：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Stop-GPUFreeAListMount.ps1"
```

然后以前台模式启动：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Start-GPUFreeAListMount.ps1" -Foreground
```

前台运行时按 `Ctrl+C` 退出管理器。需要彻底卸载 Y: 时，再运行停止脚本。

## 停止挂载

```powershell
Set-Location "D:\learning\IntelligentDepartment\CodesSet\Self\260707IsaacSIm\configs\gpufree_alist"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Stop-GPUFreeAListMount.ps1"
```

## 移除登录自动启动

```powershell
Set-Location "D:\learning\IntelligentDepartment\CodesSet\Self\260707IsaacSIm\configs\gpufree_alist"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Uninstall-GPUFreeAListTask.ps1"
```

卸载脚本不会删除本目录配置，也不会删除 `%LOCALAPPDATA%\GPUFreeAList` 中的日志和缓存。

## 日志与状态

运行日志和缓存位于：

```text
%LOCALAPPDATA%\GPUFreeAList\
├── state.json
├── logs\mount-manager.log
├── logs\ssh.log
├── logs\rclone.log
└── cache\
```

查看管理器日志：

```powershell
Get-Content "$env:LOCALAPPDATA\GPUFreeAList\logs\mount-manager.log" -Tail 100
```

查看 rclone 日志：

```powershell
Get-Content "$env:LOCALAPPDATA\GPUFreeAList\logs\rclone.log" -Tail 100
```

检查挂载：

```powershell
Test-Path "Y:\"
Get-ChildItem "Y:\" | Select-Object -First 10 Name
```

检查 SSH 隧道和 AList：

```powershell
Test-NetConnection 127.0.0.1 -Port 15244
Invoke-WebRequest "http://127.0.0.1:15244" -UseBasicParsing
```

## 远端实例关机或断网

管理器每 10 秒检查一次连接。远端恢复后，它会：

1. 通过 SSH 检查并启动 AList；
2. 重新建立本地 15244 端口隧道；
3. 重新启动 rclone 挂载。

远端完全关机期间 `Y:` 不可访问，这是正常现象。

## GPUFree SSH端口变化

如果 GPUFree 将 SSH 端口从 `30549` 调整为其他值，修改 `gpufree_alist.json`：

```json
"remote_ssh_port": 新端口
```

还需要先在命令行用新端口连接一次并接受新的主机密钥，然后运行停止脚本；管理器会按新配置自动重建连接。

## 凭据说明

- SSH 自动登录使用本地 Ed25519 密钥，配置文件不保存 SSH 密码。
- AList WebDAV 密码由 rclone 以混淆形式保存在 `rclone.conf` 中。
- 若 AList 管理员密码改变，需要重新生成或更新 `rclone.conf`。
