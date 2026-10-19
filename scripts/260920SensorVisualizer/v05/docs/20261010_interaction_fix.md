# v05 键盘与重复运行修复记录

日期：2026-10-10（北京时间）。本轮修改 v05，保留旧版本和原场景。

## 修改

- 原回调无条件读取 `event.input.name`，遇到 input 为字符串的 CHAR 事件连续报错。本版先筛选 KEY_PRESS/KEY_REPEAT/KEY_RELEASE，再解析 enum/string 键名；字符输入不驱动运动。
- 初始化默认开启键控，运动仍需网页 Play。明确显示运行、暂停、停止复位、退出和错误状态。Isaac 原生 Timeline 保持暂停是独立控制时钟的既有设计，以网页运动状态为准。
- Stop / Restore 保留控制连接，可再次 Play。Exit Controller 释放场景控制并保留管理端点，之后先 Reinitialize Controller，再 Play；完整 close 留给入口/应用退出。
- 复位和退出前检查采集、轨迹及排空，防止丢失数据；区分“已接收”与“已实际应用”回执。
- 记录原生按键、焦点阻塞、键控切换、姿态应用延迟、主帧间隔和控制回执。有界后台 JSONL 写入，输入回调不直接写盘；丢日志与写盘错误可见。

## 验证

| 项目 | 结果 |
|---|---|
| 单元回归 | Windows 51 项（1 项 Unix Socket 跳过）；Linux 51 项全部通过；JS 语法通过 |
| 真实原生输入 | Carb IInputProvider → 真实订阅回调 → Articulation；6 个平移键、3 个旋转键、3 个关节键及 CHAR 通过 |
| 状态与重用 | F8、暂停不移动、5 次 Stop/Play、2 次 Exit/Reinitialize/Play/Stop 通过 |
| HTTP 控制 | 实际网页服务到 IPC/Isaac 回执通过；退出时 Play 被拒绝，Socket 保留 |
| HTTP 响应 | 同机 120 次状态请求 P50 5.09 ms，P95 5.82 ms，最大 7.91 ms |
| 轨迹和安装位姿 | 整机、关节、雷达和相机安装位姿通过；轨迹 138 行、0.487 仿真秒 |
| 指令应用 | 短轨迹测试 P50 32.13 ms，P95 44.48 ms，最大 45.59 ms |
| MCAP | 3 组，13 路雷达、4 路 1920×1080 PNG；32 话题、92 消息、53,234,873 字节；19 条 TF 边，时间戳/源姿态检查通过 |
| 原文件 | 远端 v04 90 个文件未变；部署哈希一致；本轮根场景磁盘文件未变 |

本地证据：`reports/interaction_fix_20261010.json`。远端详细报告在 `v05/reports/native_owner/`。

正式数据：`/root/gpufree-data/semantic/output/sensor_visualizer/v05/20261010_104938_471400_3685709b/`。

合成网页 fixture 只用于按钮状态/布局验证，不作为真实运动证据。SDK 注入经过真实回调和焦点检查，仍不等同于人工远程桌面端到端手感验收。

## 剩余问题

本轮有 1 次约 414.66 ms 的 owner 慢更新，附近记录为 Play，具体内部耗时尚未拆解。正式采集每组仍约十余秒，本次不承诺完全无卡顿或渲染吞吐提升。原有 NVIDIA hydratexture 等 warning 仍存在；本轮采集没有 Error，不能据此认为 warning 无影响。没有重复 100 组/30 分钟测试，双 GPU 未验证；页面延迟为最近一次测量。

## 备份与操作范围

- 本地：`../backups/20261010_v05_interaction_before_fix_103015/v05_source.zip`，含清单。
- 远端：`../backups/20261010_v05_interaction_before_fix_103046/v05_source.zip`，含清单。每次覆盖另存 `v05/deploy_history/<UTC修订>/`。
- SSH 短暂握手中断期间没有执行部署；恢复后核对实例身份。远端动作通过 cloud-instance-ops 审计包装器，使用实例别名。
- 直接提交 HTTP 测试源码曾被包装器 secret-like 检查拒绝，未执行；随后按部署清单保存并校验测试工具，用最小入口运行。控制令牌留在实例进程中，没有传回日志。
- 没有下载/安装依赖，没有修改系统、桌面、驱动、SSH 或防火墙。专属测试进程、临时 HTTP 服务、本地 fixture 和测试浏览器标签已关闭，数据和日志保留。

## 使用

云端 v05 目录下，两个终端分别运行 `python3 run_web.py` 和 `python3 run_capture.py --interactive`。浏览器打开 `http://127.0.0.1:17865`，等就绪后点击网页 Play，原生键控前先点击 Isaac 视口。

结束顺序：Stop + Drain 并等待采集退出 → End Trajectory 并等待回执 → Stop / Restore。之后可以直接 Play。需要释放控制器时，用 Exit Controller → Reinitialize Controller → Play。

详细说明见 `startup_and_usage.md`，不要同时运行两个交互入口。
