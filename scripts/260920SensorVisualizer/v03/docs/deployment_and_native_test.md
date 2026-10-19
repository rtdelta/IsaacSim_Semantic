# v03 远端部署与原生测试记录

日期：2026-10-08，北京时间。目标：`isaac-new`。远端目录：

```text
/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v03
```

## 已完成的 GUI 验收

使用已有 Isaac / Replicator 1.13.27、ROS 2 Jazzy 和 NVIDIA L40，在独立测试进程中打开既有 `combine_scene_16_terrain_fisheye.usda`。没有降低图像分辨率、相机 16 子帧预热或正式 2 子帧设置；自动发现 4 路鱼眼和 13 路 Instant LiDAR。

最终 GUI 测试目录：

```text
/root/gpufree-data/semantic/output/sensor_visualizer/v03/tests/20261008_153745_631520
```

| 测试 | 完整组 | 图像 | 点数 | 结果 |
|---|---:|---:|---:|---|
| 静止离线采集 | 3 | 12 | 1,711,667 | 通过 |
| 关节/Pitch 目标运动、暂停、恢复、提前停止 | 2 | 8 | 1,142,534 | 通过，原计划 10 组，按 Stop 提前结束 |
| 雷达安装位置 Z 改动 1 cm 后再次采集 | 2 | 8 | 1,141,472 | 通过 |

合计 7 组、28 张图像、3,995,673 点。每组包含 30 个数据话题，另有每段运行/相机元数据。三份 MCAP 均逐条解码，通过 CDR 摘要、组完整性、共同来源时间、原生时钟冻结、PNG 尺寸与像素解码、PointCloud2 字段和 TF 与渲染位姿组合校验。成功组未发生新鲜度重试。

暂停时所有传感器更新请求均关闭；最终严格回归在第一组完成后暂停，再恢复并实际采到第二组，随后 Stop，来源时间继续相差 0.1 s。Stop 等待已提交组写完；关闭恢复 Session 改动。测试进程退出码 0、没有遗留本测试子进程；已加载磁盘 USD 哈希未变化。远端 v02 的 79 个源码/配置/文档文件哈希未变化，本地 622 个旧文件哈希未变化。

可移植测试 25 项通过。这里的 GUI 验收通过代码调用同一 CapturePanel 操作方法，不等于人工逐个点击所有控件。未执行 RViz 窗口验收、长时间压力测试、场景热替换全回归或相同条件下的 v02/v03 A/B。交互测试启用了 ROS preview；MCAP 校验与原生相机回调成功不能代替外部 ROS 订阅端验收。

## 实测性能与限制

| 阶段 | 实测结果 |
|---|---:|
| 面板对象创建 | 23 ms |
| 仅场景的 Kit 更新间隔中位数 | 8.40 ms |
| 打开面板、未 Initialize | 8.41 ms |
| 初始化 | 35.02 s |
| 初始化后空闲 | 13.27 ms，中位数；p95 17.30 ms |
| 关闭面板后空闲 | 10.93 ms，中位数 |
| 全传感器静止采集 | 12.34 s/组，含写包收尾 |
| 其中渲染/预热/读回 | 11.81 s/组 |
| 其中相机预热 | 2.76 s/组，已包含在上一项 |
| mmap 打包与提交 | 约 67 ms/组 |

Kit 更新间隔不是远程桌面实际显示 FPS。采集期间仍出现约 3.33 s 的单次更新间隔，不能承诺按钮即时响应。空闲阶段传感器更新已关闭，但正式采集仍受原生渲染和同步边界限制，尚未实现“全程流畅”或“极致吞吐”。这些数据来自短时样本，不能外推为固定性能指标。

首轮完整 GUI 基线（15:18 开始，保存在 `reports/native_evidence_baseline.json`）中，`capture` 阶段整卡利用率平均约 26.5%、Isaac 进程平均约 1.83 个 CPU 核；`warmup` 阶段整卡平均约 68.9%。空闲阶段视口继续渲染，整卡仍可能很忙，不能将“传感器更新关闭”理解为“整卡空闲”。17 次原生 render wait 累计约 97.67 s，stop/drain 累计约 11.28 s；二者包括初始化与预热，不能全部除以采集组数。说明下一步优先研究 RTX/SDG 调度与同步，而不是继续增加 PNG 线程。

## 本轮查明的兼容性问题

安装的 Replicator `wait_until_complete_async()` 会停止 generation、排空 Writer 并恢复设置，包括 Timeline auto-update；不是轻量的单帧完成 fence。尝试只等待相机回调时，LiDAR 的来源时钟正确，但渲染变换与 USD 不一致；另一次保留同一冻结请求并额外推进最多 8 次 Kit 更新仍未刷新变换。两次试验都被校验拦截，成功组数为 0，没有将错误组作为有效数据发布/保存。

最终部署保留已经原生验证的停止/排空流程，并用 `replicator_stop_drain` 单独计时；相机接收窗口、请求身份和位姿检查仍保留。移除该流程需要进一步研究 RTX/SDG 后端的完成条件，不能简单删掉等待。

命令行首次打开场景还暴露了 `captureOnPlay` 生命周期问题：在打开 USD 前设置为 false，会被场景加载过程重置，随后 Replicator 的停止操作连带停止 Timeline，使 Articulation tensor 无效。已在场景加载与 STOP 回调完成之后再次关闭该选项，修复后无窗口测试完成。

关闭顺序调整为：禁用更新、等待/分离数据资源、销毁本项目产品、停止 Timeline 后再恢复运动与移除 Session 层。这避免了先移除运行层、PhysX 仍持有旧状态的顺序问题。最终 GUI Kit 日志中不再出现先前的停止时编辑目标变更告警。

## Warning 与诊断

`omni.hydratexture.plugin was already released` 仍反复出现。它没有使本轮 7 组数据校验失败，但根因未消除，也不能因此判为长期无害。本轮没有改动 Isaac SDK 或压低日志级别。Motion BVH 关闭提示属于沿用的启动配置；这里只验证冻结 Instant 数据路径，不推断运动扫描补偿正确。

第一轮完整 GUI 验收的具体记录：Hydra 已释放接口提示 185 次；LiDAR 材质接口重复获取性能提示 11 次；另有空 SdfPath、USDRT channels 属性、RobotMotionSchema 路径及 animation graph 注册等启动/资产告警。这些告警不能仅凭此次出包成功就一概忽略；本项目当前直接使用 Articulation 状态控制，没有使用 motion planning / animation graph 功能。没有为消除这些环境告警而修改 SDK、系统库或安装额外组件。该轮无 `[Error]` 级别日志，项目与录制端诊断均正常关闭，丢事件计数为空且无日志 I/O 错误。

完整 Kit 日志位于各测试根目录 `kit.log`；项目日志位于 `captures/runs/<run_id>/diagnostics/`，包含原生 Warning、分阶段主机耗时、来源时间、请求/组身份、队列与资源采样。主机耗时包含 GPU 等待，不代表精确 GPU kernel 时间。GPU 利用率是整卡统计，不能当作单个传感器或 SM occupancy。

## 使用

远端桌面终端：

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v03
/usr/bin/python3 run_capture.py --gui
```

打开默认 combine scene，在 Script Editor 执行：

```python
from pathlib import Path
p = Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v03/run_in_isaac.py')
exec(compile(p.read_text(encoding='utf-8'), str(p), 'exec'))
```

按 `Initialize Current Stage → Start Capture → Stop + Drain → Close / Restore` 使用。不要手动按 Timeline Play。测试过的详细操作与命令见项目 README。

命令行小样本入口：`/usr/bin/python3 run_capture.py --job config/smoke.json`；无窗口补充测试结果另记于本报告后续段落及 `reports/native_evidence.json`。

## 无窗口 CLI 验收

修复后的测试目录为：

```text
/root/gpufree-data/semantic/output/sensor_visualizer/v03/tests/20261008_153437_404068_headless
```

实际通过 `run_capture.py --job <测试 job.json>` 运行，没有使用 GUI 验收替代这个入口。选择前相机 + 13 路 LiDAR；加入 Roll 目标和缓慢前进/Yaw 速度，3 组写成 2 段 MCAP。退出码 0；3 张 PNG、1,712,968 点、每组 21 个数据话题全部读回校验通过。采集阶段耗时 28.83 s。此负载只有一台相机，不能与上面的四相机结果直接计算加速比。

四路相机解码样图已保存本地 `reports/native_camera_preview.jpg`，能够看到前方挖掘机结构、四周围栏、地面与天空；这只是人工检查样例，不是全部帧的视觉质量评估。

## 操作记录与恢复

- 授权：部署并测试新建 v03，保留旧项目与资产。执行渠道为本地审阅 Python + cloud-instance-ops 包装器，使用凭据引用和主机指纹/实例身份验证。
- 操作前：v03 尚不存在，已有 Isaac/ROS 环境与默认场景，无既有 Kit/录制进程。没有安装或升级依赖、驱动、系统或桌面组件，没有下载第三方文件。
- 写入范围：远端 v03 项目目录、v03 测试输出及应用自身正常生成的缓存/日志。场景改动只在可撤销 Session 层；源 USD 未保存。
- 所有远端试验由专用 supervisor 启动并限定自己的进程树。一次 SSH 部署握手失败后误启动了冗余 GUI 测试，核对测试目录、PID 与启动 tick 后仅停止该测试进程组，未处理桌面或其他用户进程；该轮不计入验收。
- SSH 后续有数次认证前握手断开；不能据此推断实例损坏或安全事件。失败均有记录，已知未发出远端命令的操作才重新尝试。
- 本地原始审计目录为 `%LOCALAPPDATA%/CloudInstanceOps/audit/20261008`（桌面应用可能重定向，准确位置见 `reports/operations.json`）。它只覆盖包装器操作，不是主机全量网络/安全审计。
- 被替换的 v03 文件保存在远端 `v03/deploy_history/<UTC时间>/`，包括 `20261008T071830491806Z` 和 `20261008T072602116606Z`。旧版本未覆盖，可继续使用原入口。按清单恢复 v03 时应先结束 v03 自己的采集进程；本轮未进行回退演练。
- 本地 `reports/gui_acceptance_status.json` 与 `reports/gui_validation_results.json` 是已留存审计结果的提取副本；完整 MCAP 保留远端，本轮未把大包下载到本地 output。
