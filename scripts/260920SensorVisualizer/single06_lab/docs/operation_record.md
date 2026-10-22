# single06_lab 操作、备份与复现记录

日期：2026-10-11。实例目标为已登记的单卡 `isaac-new`，NVIDIA L40 / 驱动 580.126.09；本轮未操作双卡实例。

## 范围和依赖

新增本地：`D:\learning\IntelligentDepartment\CodesSet\Self\260707IsaacSIm\scripts\260920SensorVisualizer\single06_lab`。

新增云端：`/root/gpufree-data/semantic/scripts/260920SensorVisualizer/single06_lab`。测试结果：`/root/gpufree-data/semantic/output/single06_lab`。

只使用已有 Isaac、ROS、Warp、Pillow/NumPy、NVML、Nsight Systems 2025.1.1、nm、Python/SQLite 标准库。没有 apt、pip、驱动、系统、桌面组件变更，没有外部依赖下载。Isaac 启动沿用关闭注册表拉取、遥测、网络服务的项目参数。

远端操作通过 `cloud-instance-ops`，验证主机指纹和实例身份，凭据采用现有引用。工具调用没有写入密码值。SFTP 复用已有 Paramiko，同样核对身份与指纹，逐文件 SHA256 校验并记录审计；这是项目证据回传，不是从外部网站下载工具。当前 CLI 无项目文件传输命令，单独记录了这一能力缺口。

## 备份和源码隔离

本地正式版备份：`../../backups/single06_before_lab_20261011_175330.zip`，143 个源码/配置/文档文件。

每次远端部署前保存正式 v06 快照；至少包括：

```
/root/gpufree-data/semantic/scripts/260920SensorVisualizer/backups/single06_before_lab_20261011_101200.zip
/root/gpufree-data/semantic/scripts/260920SensorVisualizer/backups/single06_before_lab_20261011_104510.zip
```

实验项目自身被替换的文件保存到 `single06_lab/deploy_history/<UTC时间>/`。正式 v06 的 61 个运行相关源码与冻结副本逐文件一致；本地正式版另以基线清单核对全部 143 文件。`frozen_runtime` 不导入相邻正式 v06。

部署 ZIP 限定项目路径，拒绝不安全成员或非预期符号链接，校验全部传输哈希。工具脚本单次不超过 256 KiB；最终代码和文档可分别用 `build_deploy.py --kind code`、`--kind docs` 生成审计部署批次。

## 执行批次

| 云端目录 | 内容 |
|---|---|
| `smoke_20261011_100023` | 2 组首次完整采集及全话题校验 |
| `trace_steady_20261011_100332` | 首次原生窗口未触发，保留失败证据 |
| `trace_steady_20261011_100829` | 修正 NVTX 注册字符串筛选后取得原生窗口与设备指标 |
| `investigation_20261011_101239` | 交错 AB/BA、静态对照、CPU 池、同进程 3 轮、初始化/清理追踪 |
| `followup_20261011_104521` | RGB 立即消费、失败的预热路由、完整组堆栈、停止、keepalive 并发控制 |
| `confirmation_20261011_110041` | 两种策略各 16 组、图形指标窗口、仅交互/gated 并发控制 |

普通性能对照期间不插入原生追踪；大文件证据回传放在批次结束后，原生追踪数据用于机制分析，不用于计算普通速度收益。

## 实验中出现和处理的问题

- 首两次实验启动器配置/返回值适配错误：诊断级别应为 `deep`，原 `launch_spec` 返回三项。只修正实验启动器，原 v06 未改。
- 第一次 NVTX 捕获未输出 native 文件：设置 `NSYS_NVTX_PROFILER_REGISTER_ONLY=0` 后触发成功。后续要求实际闭合窗口和设备指标行存在，不能以退出码 0 代替追踪成功。
- 首轮并发控制端 `AF_UNIX path too long`：嵌套输出路径超过 Linux 限制，实验端改用输出根目录下随机短 socket；已正常启动并完成 keepalive 并发验证。
- 相机单独预热候选触发 LiDAR `render_pose_mismatch`：保留失败、正常清理，停止采用该候选，没有取消源位姿/时间戳校验。
- 请求 CUDA API 栈但实际没有导出：明确标注缺口，保留 CPU 采样与 API 时间证据，没有假装取得完整调用栈。
- 本地顺序 CSV 的路径拼接错误修正后已生成；分析脚本的 P95/P99 使用 nearest-rank，标注小样本限制。

## 警告记录和归因边界

完整 `engine.log` 保留；诊断队列另聚合 warning/error。常见项包括空 SdfPath、Fabric 接口版本提示、3DGS `channels` 属性类型、hydratexture/传感器接口频繁获取、清理时 interface already released、GUI 动画节点注册和音频设备提示。

这些日志不能逐项自动当作性能根因。对性能根因的论证使用原生调用栈、模块生命周期、时间包含关系和单变量对照。没有为了“消除警告”更新环境或修改正式资产。失败的预热路由和 socket 错误有明确功能影响，分别保留了原始日志及处理/否决结果。

## 进程和退出

只启动并管理本项目自己的子进程，保留 PID、开始时间及进程归属。隔离测试遇到已有 Isaac 会拒绝运行；并发测试由实验运行器显式创建 GUI owner 和独立 capture。

正常结束先完成冻结组、排空 writer、结束 generation，再释放资源。超时先请求 stop，等待后只处理创建的进程/进程组，不使用宽泛 pkill。最终退出及源码不变核验会保存到本地 reports 中。

最终只读核验已通过：本地正式版 143 文件、远端初始快照 141 文件没有变化，冻结运行副本一致，未残留本项目进程。派生报告和关键图表随最终文档同步，完整原生文件仍留在实验输出及本地 reports。
