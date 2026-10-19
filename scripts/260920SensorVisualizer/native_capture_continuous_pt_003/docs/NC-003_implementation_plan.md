# NC-003：原生连续调度下逐张高采样Path Tracing测试

2026-10-12。用户要求：原生链路采用连续采集调度，Path Tracing，每张指定高采样画质并测试。

本轮采用上一轮预算上限1024SPP，每迭代32SPP，8反弹，关闭自适应采样、时间降噪和运动模糊，开启OptiX空间降噪。四路1920×1080鱼眼及13路Instant LiDAR保留同一场景。

## 调度及逐张质量约束

- 一次启动官方 `rep.orchestrator.run_async(num_frames=4)` 连续场景，调用普通引擎更新驱动原生调度。取消上一轮每组6物理更新及两次step_async，原生引擎不导入任何旧项目运行时代码。
- 连续指原生场景持续调度；不是让场景在一张图像累积时不停运动。已安装SDK on_update会在每张PT的32个子帧期间关闭时间轴自动推进，完成后恢复，再开始下一张。
- 使用 `/rtx/resetPtAccumOnAnimTimeChange=true`，并在官方逻辑帧trigger事件处调用 `UsdContext.reset_renderer_accumulation()`。每张独立重置；不能把首张1024累积沿用到后续图像。
- 只读记录原生trigger/capture事件、原生子帧完成计数及实际生效设置。私有SDK计数器用于版本相关的诊断，不控制调度。要求每张capture时计数32、配置1024/32且关闭adaptive，不把这些证据冒称逐像素硬件射线数。
- 基准的0/15/-15/0度大臂目标在逻辑帧开始处通过原生Articulation设置，用于验证姿态改变后每张重新累积；未开启重力与接触动力学。

## 数据与校验

官方ROS Helper生成图不改接；标准ros2 bag record写MCAP。NVIDIA BasicWriter另外保存每张最终RGB和CameraParams作为诊断参考；原生RGB/XYZ观察记录哈希及渲染位姿，不替换发布载荷或header。

要求四路图像/标定、13路点云、18条TF及关节在当前组时间戳齐全；MCAP/current/native BasicWriter图像字节一致，MCAP/current XYZ字节一致；组间时间戳不同，TF/关节/渲染位姿匹配；每张预算和重置记录通过。不满足就记录失败，不把低采样图像当成成功数据。

## 保存与范围

独立项目 `native_capture_continuous_pt_003`；NC-002及旧版本保存执行前源码快照，每次部署检查其哈希。USD只改本进程Session层。用现有Isaac/ROS/MCAP/NumPy/Pillow/Nsight工具，不下载或更新依赖、不改系统。

保存逐更新时间、逻辑帧耗时、质量配置、事件、1Hz GPU/CPU/RSS采样、原始warning、标准MCAP与BasicWriter参考图。先完成4组有效数据，再解释每张耗时及GPU利用率。启动/录包收尾与正式采集分别计时。

首轮测试失败时保留日志及MCAP，依据已安装SDK修正本新项目并重试；不为速度改预算或删除质量校验。最终报告注明调度计数与实际硬件SPP的证据边界。
