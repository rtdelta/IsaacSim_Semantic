# v04 调度、数据所有权与原生诊断

## 函数与接口

| 阶段 | 项目函数 | 外部接口/执行线程 |
|---|---|---|
| 背压与调度 | CaptureRunner.run、RecordPipeline.reserve | asyncio、有界槽；Isaac 主线程 |
| 运动 | SceneStepper.advance | Timeline play/pause/commit、Kit next_update_async、Articulation tensor；主线程，正式流程唯一推进时间的阶段 |
| 冻结 | SceneStepper.capture 的 frozen 检查 | SimulationManager、Timeline、UsdGeom.XformCache；主线程 |
| 预热 | SensorDrivers.warm_cameras、_step | Replicator step_async(delta_time=0)；主线程调用、GPU执行 |
| 请求 | SensorDrivers.acquire | 每路 Writer.schedule_write、step_async(wait_for_render=True) |
| 完成回读 | _receive、_copy_host、read | CUDA Annotator、Warp.numpy/NumPy、CameraParams、IsaacReadSimulationTime、RTX transform |
| 打包 | RecordPipeline.submit | asyncio.to_thread、mmap、socket；后台线程只使用独立CPU数据 |
| 编码/录制 | record_worker | Pillow、线程池PNG、rclpy CDR、rosbag2_py MCAP；独立进程 |
| 安全停启 | finish_generation、_drain_generation | wait_until_complete_async；暂停/结束边界 |

所有正式请求均在冻结姿态和时间下完成。回调立即复制 GPU payload 为独立 CPU 数组，全部相机和雷达收到并验证后才推进下一组。后台第N组编码/保存可与第N+1组采集重叠；线程不并发调用USD、Kit、Annotator或原生指针。

## 正确性

来源时间容差保留2ns，渲染矩阵误差阈值保留2e-3。group/request/sensor只关联请求；source_frame_id未暴露，保持null，不伪造。冻结验证同时检查原生时钟、Timeline、机器人部件矩阵和安装revision。

缺回调、晚回调和来源异常不重新贴时间戳。缺回调直接失败，遗留pending不能转交新组。重试只允许已完成请求且场景仍冻结的来源时间/矩阵异常。失败即停用产品，包含keepalive策略。

compatibility保留v03相机回调、LiDAR排空后轮询路径。persistent_gated使用所有传感器手动回调；每组不停止生成会话，暂停、结束、关闭时才全局排空。native渲染返回与独立回调所有权构成组完成屏障。

## 资源策略与灯光

gated默认在空闲、运动、背压、暂停和成功取得数据后关闭全部产品。预热时全部开启，以同姿态初始化RTX位姿；只预热相机的实验产生错误LiDAR矩阵，已拒绝。

keepalive仅允许offline持续后端。活动组间保持真实更新，减少CUDA/Vulkan再建；中间运动渲染没有正式请求，不保存。暂停、结束、失败、背压关闭产品。它增加中间渲染以减少CPU初始化，是否划算以有效组/秒实测判断，不能按GPU利用率升高判断。

select_dome在运行层明确选择一个可见DomeLight，停用其他DomeLight。原生实验中两盏光源同时有效导致持续会话天空黑色，图像PSNR仅4–7dB；临时停用近黑色地形光后恢复31–33dB。原始文件不修改，公平基线使用同样选择。null保留作者配置；持续后端在多盏可见光源且未选择时拒绝初始化。

## 日志与原生追踪口径

RunDiagnostics.begin/end记录monotonic_ns、UTC、PID/TID、group/request/sensor及span ID。thread_cpu_duration_ns是同一OS线程跨await的累计CPU，包含引擎与其他回调，不是函数自身CPU；跨线程结束为null。

可选native_profiler=nvtx使用已安装libnvToolsExt，以RangeStart/RangeEnd关联原生时间线，不使用跨await线程push/pop假设独占线程。默认off；短追踪与性能验收分开。

Nsight包含Vulkan、CUDA、OSRT、NVTX、原生栈和线程调度。实验仅在自己的进程中包装SDK，finally恢复，不改安装目录。direct Kit在profiler注入前整理环境，不修改全局LD_PRELOAD。

Nsight2025.1与CUDA13存在兼容警告，闭源符号不全。individual Vulkan溢出时记录并集只代表工作下界；batch覆盖区间可能包含内部空档，不能当成GPU持续100%。整卡nvidia-smi和进程采样也不是函数的资源消耗。等待、回读、后台编码与原生GPU工作重叠，不能简单相加。

## 保护范围

只部署v04，旧源码逐文件哈希检查，双端ZIP备份。USD变更仅Session层，关闭恢复。无外部下载、依赖安装、驱动/系统/桌面变更。诊断是项目性能排查，不是主机安全认证。
