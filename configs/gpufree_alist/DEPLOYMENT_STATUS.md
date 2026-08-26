# 部署状态

验证时间：2026-08-14 16:04（Asia/Shanghai）

## 已完成

- AList v3.63.0 正在远端 `127.0.0.1:5244` 运行。
- 本地 Ed25519 公钥已追加到远端 `/root/.ssh/authorized_keys`。
- `BatchMode=yes` 免密 SSH 登录验证通过。
- Windows 任务计划 `GPUFree AList Auto Mount` 已注册并处于运行状态。
- 自动管理器已建立隐藏 SSH 隧道 `127.0.0.1:15244`。
- rclone 已将 `alist:/gpufree-data` 挂载到本地 `Y:`。
- `Y:\semantic` 和其他远端目录可正常读取。
- AList 本地隧道 HTTP 检查返回 200。
- 主动终止 SSH 隧道后，管理器成功自动创建新隧道并恢复访问。

## 当前入口

主要入口：

```text
Y:\
```

配置目录快捷入口：

```text
D:\learning\IntelligentDepartment\CodesSet\Self\260707IsaacSIm\configs\gpufree_alist\GPUFree AList.url
```

## Z盘限制

`Z:` 是 `\\192.168.71.34\Public` 的 SMB 网络盘，而且当前账户无法在 `Z:\SimluationData` 创建文件。由于网络文件系统不能稳定嵌套挂载，最终使用独立盘符 `Y:`，没有修改 `Z:` 中的现有数据。

## 自动恢复范围

- 关闭原来的手动 SSH PowerShell 窗口不会影响现在的自动挂载。
- SSH 隧道中断后，管理器会自动重建。
- rclone 退出后，管理器会自动重新挂载。
- 远端 AList 未运行时，管理器会通过 SSH 尝试启动它。
- Windows 下次登录时，任务计划会自动启动管理器。
- 远端主机完全关机时 `Y:` 暂时不可用；远端恢复后管理器会继续重试。
