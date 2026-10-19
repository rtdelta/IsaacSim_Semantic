# 单卡 → 双卡实例迁移记录

日期：2026-10-10，北京时间。迁移已完成。

## 迁移范围与落点

从单卡实例（SSH 端口 30729）复制到双卡实例（SSH 端口 30716）。以下目录在新实例保持原名、原路径：

| 路径 | 内容 |
| --- | --- |
| `/root/gpufree-data/IsaacSim_Asset` | combine stage、挖掘机、LiDAR、鱼眼相机、地面、环境、纹理等资产 |
| `/root/gpufree-data/semantic/scripts/260920SensorVisualizer` | Sensor Visualizer 各保留版本，包括当前 v06、配置、文档、工具和必要 3DGS 素材 |
| `/root/gpufree-data/semantic/scripts/260907LidarVisualizer` | 原 LiDAR 工程及旧入口需要的项目代码 |
| `/root/gpufree-data/camera` | 已有相机相关素材 |

共 1663 个文件，2,532,507,983 字节，约 2.36 GiB。目标目录原先没有这些项目文件，因此没有覆盖已有项目内容。

未迁移历史点云、MCAP、采集输出、旧虚拟环境、日志、缓存和 Git 历史。没有克隆系统盘、修改平台桌面、驱动、SSH 服务、系统启动配置，未下载或安装外部依赖。

为保留版本交付证据，少量 v06 单卡验收 JSON 报告也已复制；它们仍然是**源单卡实例的历史报告**，不代表新双卡实例的性能。

## 核验结果

- 传输压缩包 SHA-256：`693288517fa655f7f1d136f560213734f01de2bcda7258d27092b6e030d2bdc3`。
- 接收、解包、落盘后 1663 个文件的 SHA-256 全部与迁移清单一致。压缩包已在核验后删除；清单与结果保留。
- v06 交付清单中的 140 个文件与本地交付源码一致；v05 基线 102 个文件与保留的基线一致。
- 新实例实际运行 v06 单元测试：60 项通过，耗时 3.806 秒。测试中的 `test capture failure` 是主动测试异常处理，不是迁移失败。
- 新实例已有 Isaac Sim `6.0.1-rc.7+release.42383.32955d8d.gl`、ROS Jazzy；NumPy、Pillow、rclpy、rosbag2_py 及所需 ROS 消息包可导入，`mcap` 存储插件可用。
- 用新实例已安装的 USD SDK 静态读取最新场景的 18 个本地 USD 层；检查范围内没有缺失资产、没有外部 URL。环境 USDZ 的三个直接引用成员存在。`OmniPBR.mdl` 在已安装的 Kit 材质库中。未展开 USDZ 内部嵌套层、未通过完整 Stage 渲染验收。
- 新实例识别两张 NVIDIA L40，每张显存约 45 GiB。尚未启动双卡实际渲染、采集或性能基准，不能据迁移成功宣称双卡已经加速。

文件一致性、代码与本地版本一致性、运行依赖检查及单元测试是不同核验层次；这些结果不构成整台实例的安全认证。

## 传输与清理记录

首次登录按用户本轮要求用隐藏输入的密码直连，后续凭据由本地 Windows 凭据管理器读取，不在脚本、命令行、报告中保存密码。

新实例第一次连接记录并固定 SSH 主机指纹；实例为同一镜像的克隆，主机指纹、hostname 和 machine-id 与源实例相同，因此另核对目标端口和两张 GPU 的 UUID。首次指纹没有独立的平台证明。

新实例到源实例公网端口连接被拒绝。先试本地加密中转，随后发现两实例内网可达，切换为目标端主动拉取。使用新建的一次性密钥，源端只允许执行读取本次指定压缩包的强制命令，禁止转发和交互登录；没有把新实例密码或原有密钥交给源端。

内网迁移成功后，仅终止本任务旧中转的接收进程，旧中转记录标为失败/已替代，最终成功以 `migration_result.json` 为准。结果中的 `elapsed_s` 来自解包与落盘核验阶段，不能直接当作纯传输耗时。

源实例临时 authorized_keys 条目已撤销，原文件逐字节恢复。新实例临时私钥、两端传输压缩包、旧中转半包及解包临时硬链接已清理，最终项目文件保留。迁移元数据保存在两端 `/root/gpufree-data/.migration_sensor_20261010_dual/`；本地工具审计在 CloudInstanceOps 的本地受限审计目录。

## 新实例启动方式

在云端桌面打开两个 Linux 终端。第一个启动网页：

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06
/usr/bin/python3 run_web.py
```

第二个启动交互窗口，显式选择 GPU 0：

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06
/usr/bin/python3 run_capture.py --interactive --job config/interactive.json --gpu 0
```

云端浏览器打开 `http://127.0.0.1:17875`。等待 `interactive_ready`，在网页点击 **Play Simulation**，再使用键盘或参数控制。

默认自动加载 `/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_16_terrain_fisheye.usda`。

如使用已经打开的 Isaac GUI，可在 Script Editor 运行 `/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/run_in_isaac.py`；它与独立交互入口二选一。

网页已有“采集 GPU”选项，可以输入 `1`，计划让独立采集进程使用第二张卡。两进程各自加载场景，并非一份渲染任务自动分到两卡；实际 GPU 绑定、显存需求、采集输出及性能仍待双卡运行验收。本次迁移未改旧源码或配置来默认启用双卡。

完整控制、采集、停止和回退说明见 v06 的 `docs/startup_and_usage.md`。后续新采集数据仍写入 `/root/gpufree-data/semantic/output/sensor_visualizer/v06`。

## 回退与证据

源实例资产、项目代码保留原样，可继续作为迁移来源。目标保留旧版本目录，可按各版本原入口回退；停止自己启动的项目进程后再切换版本，不批量停止桌面或所有 Python/Isaac 进程。

本目录保存 `migration_manifest.json`、`migration_result.json`、`code_provenance.json`、`unit_validation.json`、运行依赖、USD 层检查和清理报告。相同报告也存放在新实例 `/root/gpufree-data/semantic/scripts/260920SensorVisualizer/migrations/20261010_dual_gpu/`。

## 本地实例配置

实际 `targets.json` 保持原文件名并由 Git 排除。首次获取代码时，将 `targets.example.json` 复制为 `targets.json`，填写独立核验的主机指纹、machine-id 哈希、hostname 与本机凭据引用。不要覆盖已有本地配置，也不要使用占位值启动迁移。现行 remote_ops.py 和历史入口继续读取同一路径；本次没有执行迁移或连接云实例。
