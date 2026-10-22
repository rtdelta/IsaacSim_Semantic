# 迁移完成报告

完成日期：2026-09-20。旧实例：120.209.70.195:30162；新实例：120.209.70.195:30729。

**已迁移 4,529 个文件，共 8,903,002,518 字节（约 8.29 GiB）。**
数据传输与逐文件校验用时约 8 分 8 秒，最终状态为 `complete`，校验错误为 0。
每个文件均通过源端 SHA-256、接收流 SHA-256、目标磁盘重新读取 SHA-256 三方比对，最终文件数量和尺寸与迁移清单一致。

## 新实例上的主要位置

| 内容 | 目录 |
|---|---|
| 全部场景、挖掘机、环境和传感器资产 | `/root/gpufree-data/IsaacSim_Asset/` |
| LiDAR Visualizer | `/root/gpufree-data/semantic/scripts/260907LidarVisualizer/` |
| MyAiry 制作项目 | `/root/gpufree-data/semantic/scripts/260919MyAiryLidar/` |
| 最新 3DGS 挖掘机装配项目 | `/root/gpufree-data/semantic/scripts/260920SensorVisualizer/` |
| 最新 3DGS 挖掘机发布资产 | `/root/gpufree-data/IsaacSim_Asset/excavator_module_set/Excavator_3DGS_Contract/` |
| Semantic World、关节控制、后处理等各版本代码 | `/root/gpufree-data/semantic/scripts/` |
| Blender 工程与原始模型素材 | `/root/gpufree-data/blender/`、`/root/gpufree-data/Test0/`、`/root/gpufree-data/Test1/` |
| NZ3 标定和建模素材 | `/root/gpufree-data/260910NV3Lidar/` |

保持原有目录层次与文件内容。保留源码相关文档、配置、轨迹输入、资产预览和 Git/LFS 数据。
历史 `semantic/output`、MCAP/DB3、运行日志、缓存、旧虚拟环境与系统二进制未迁移。
新实例的 `semantic/output` 仅创建空目录，便于后续应用写入。

## 引用与环境检查

- 使用新实例原装 USD 库检查了 54 个相关 USD 层；没有 USD 层打开失败。
- 最新组合场景、MyAiry、MyOS0、NZ3 与新的 3DGS 挖掘机没有发现缺失的本地组合引用。
- 旧场景 `Combine_Scene_02.usda` 仍有两个原本缺失的引用：`./Environment/environment.usdz` 和 `./Fangshan_Excavator_01.usda`。已在旧实例单独确认这两个文件不存在，属于迁移前的问题；未擅自修改该场景。
- NVIDIA 云端默认环境与 Ouster 资产链接保持不变；这次只检查本地组合引用，没有下载或离线化这些云端依赖。
- 新实例已有 Isaac Sim 6.0.1-rc.7 与 ROS 2 Jazzy。此次没有安装、升级或克隆系统库与旧运行环境，也没有逐一启动项目进行 GUI/仿真验收。
- 新实例的 gpufree、Xorg、XFCE、selkies 进程在迁移后仍保持运行，PID 与迁移前一致。`/etc/ld.so.preload` 保持新实例初始内容，检查进程没有加载旧实例的 `.libproc.so`。

## 传输与记录

公网实例间回连被拒绝后，使用新实例到旧实例的内网 SSH 连接完成迁移；全程核对原有 SSH 主机公钥。
旧实例存在读取过滤，已通过原始读取系统调用与 Base64 传输绕过，并以逐文件哈希确认一致性。
旧实例未收到新实例密码或私钥。迁移期间不执行旧项目代码，不修改旧资产，不修改新实例桌面、SSH 或系统启动项。

- 作业与完整清单：`/root/migration_jobs/assets_code_20260920_to_30729/`
- 项目内报告与工具副本：`/root/gpufree-data/semantic/scripts/260920SensorVisualizer/migration/20260920_to_30729/`
- 本地报告与工具：本报告所在目录。
- `verified.jsonl`：全部文件的 SHA-256 与落盘复核记录。
- `completion.json`：最终数量、容量、目录统计及环境检查结果。
- `selection.json` / `excluded.json`：迁移范围与排除理由。
- `asset_dependencies.json`：USD 组合引用检查细节。

文件哈希一致性不等同于完整安全审计；此报告不声称旧项目源码已经过全面安全审查。
