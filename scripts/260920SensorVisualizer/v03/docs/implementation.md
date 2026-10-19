# v03 实现与验收说明

## 1. 本次边界

2026-10-08 本地新建并随后部署远端、运行原生验收。旧版本逻辑被复制为本项目内的源码后调整；运行时只使用 `sensor_visualizer_v03`、本目录配置和外部已安装环境，不引用旧项目。旧文件哈希比较结果保存在 `reports/isolation_check.json`，远端验收见 `deployment_and_native_test.md`。本次未安装库、未修改磁盘 USD 资产或系统配置。

方案 002 的第 1、2、4 点与日志方案是本次范围；方案 001 的替代渲染器、CUDA 零拷贝、GPU PNG、多实例分片不在此版本中。画质/预热子帧未为追求性能而降低。

## 2. 调度和完成条件

| 阶段 | 相机更新 | LiDAR 更新 | 原生时间 | 完成条件 |
|---|---|---|---|---|
| Panel Idle / Initialize 后 Idle | 关闭 | 关闭 | 暂停 | 等待用户 |
| Pacing / Pause / WaitSlot | 关闭 | 关闭 | 暂停 | 节拍/控制/槽可用 |
| Advance | 关闭 | 关闭 | 以原生 Kit 更新推进 | 达到下一采样点 |
| Camera Warmup | 开启 | 关闭 | 冻结 | 16 子帧及完成屏障 |
| 初始化或安装位姿变更预热 | 开启 | 开启 | 冻结采集前稳定 | 原配置预热及屏障 |
| Capture / WaitData / Read | 开启 | 开启 | 冻结 | 全传感器数据拥有化且校验通过 |
| Pack / Drain / Finished | 关闭 | 关闭 | 暂停 | IPC/编码/写包完成 |

初始化逐个创建产品，立即关闭更新，产品之间让出 Kit 更新机会。产品仅在关闭/重新初始化时销毁。缓存开关状态用于避免重复 API 调用；事件明确写明“API 已返回”，不会据此宣称 GPU 无任务。

`SceneStepper.capture()` 冻结原生仿真时间、Timeline、传感器和机器人相关矩阵以及安装位姿 revision。预热、正式渲染、等待回调、读回和重试后均核验。时间不变容差 `1e-9 s`；来源时间差最大 `2 ns`；场景矩阵最大差采用 `atol=2e-6, rtol=0`；渲染矩阵最大元素差 `2e-3`。矩阵差不是统一的毫米单位。

`CaptureTicket` 保存 run/capture/group/request/attempt/stage_generation 标识、目标时间、位姿版本、预期/收到/验证的传感器集合和超时。原生产品没有明确帧号时写 `source_frame_id=null`，不把请求号当渲染帧号。

## 3. 回调来源与重试

相机 Writer 使用手动触发：预热不调度 Writer；正式采集为每个 Writer 绑定不可变请求，然后 `schedule_write()`，再零时间步渲染。`step_async` 返回后仍保留窗口，晚到回调可以进入当前请求。收到全部相机后，经过 `wait_until_complete_async()` 停止并排空 Replicator，再按真实来源时间/渲染位姿验证。回调数据在主线程及时转换、复制为自有 CPU 数组。

远端 Replicator 1.13.27 源码和原生测试确认：此接口会停止 generation、恢复设置与 Timeline auto-update，并非低成本单帧 fence。仅以相机回调替代它，或额外做 8 次 Kit 更新，均未得到正确 LiDAR 渲染变换，校验阻止了这些样本入包。因此当前保留该兼容流程，单独记录 `replicator_stop_drain` 耗时；不声称已经消除所有重复渲染。未来需要改造或替换这一原生适配路径时，应以位姿变化和数据一致性再次验收。

LiDAR 仍在完成渲染之后读取 Annotator，不假设它具有同样的 Writer 回调接口。其新鲜度证据是完成的串行渲染、来源时钟及 RTX 变换。未提供原生帧号的情况下，不能仅凭时间戳数学证明“同一冻结姿态下绝非同内容缓存”；真实环境必须用姿态变化和后端事件验收这一兼容路径。

只对已交付请求的 `source_time_mismatch`、`render_pose_mismatch`、`source_frame_stale` 做同一冻结姿态下的整组重试，最多 3 次。缺失回调或就绪超时直接结束当前采集并要求重新初始化，避免把仍在途中返回的旧请求绑定到新组。没有未经验证的“只重试一台相机”。

等待数据时最多执行配置的额外 Kit 更新；每一次标记 `may_render=true` 并计时。它可能产生实际渲染，不被称作零成本等待。Python 超时无法中断已阻塞的原生渲染调用；此时只能记录返回后的耗时、保留资源所有权。取消协程会先等待已提交原生任务完成，不能强拆 CUDA/RTX 句柄。

## 4. 并行与背压

缓冲槽状态：`FREE → RESERVED → CAPTURE_OWNED → PACKED → SENT → RELEASE_ACK → FREE`。每次复用增加 generation；录制进程释放必须匹配 capture/group/slot/generation。空点云也是有效载荷。

取得自有 CPU 数组后设为只读，再 `asyncio.to_thread` 执行 mmap 打包和 IPC 发送，减少 Kit 主线程复制/等待。没有把引擎指针交给线程。IPC 发送超时关闭本项目自己的连接，等待发送线程结束后再清理缓冲。接收连接不因用户长时间暂停而超时。

后端保持一个独立 ROS Python 进程，最多配置数量的 PNG 编码线程，单一有序 MCAP 写入者。前后端队列及 mmap 数量有界；无槽时不运动、不渲染。停止请求记录到达时间，在安全边界应用；已经交付的组继续 drain。失败时保留此前成功组并记录失败状态。

## 5. 日志精度与使用

- run 从面板/CLI 启动即开始；初始化、空闲、采集、关闭都可观察。一个面板 run 可以关联多个 capture。加载另一个 Job 会结束启动诊断并按新配置开启新 run。
- 事件包含同主机 `monotonic_ns`、UTC、pid/tid、角色、顺序号、阶段、group/request、仿真来源时间、sensor、span ID。显式 span ID 可跨 await，禁止把异步等待伪装为线程内嵌套 CPU 调用区间。
- `host_materialize` 包含可能的 GPU 等待；`cpu_owned_copy` 是随后的 CPU 副本；两者不能被直接解释为纯 DMA 带宽。MCAP API 写入、摘要、分段、关闭、索引 fsync 分别计时；`write()` 返回不等于数据已物理持久化。
- `basic` 保留主要区间/计数及默认 1 Hz 资源采样；`diagnostic` 加入按 group 范围选择的明细；`deep` 同时保留明细，配合可选 `native_profiler=markers` 和外部已安装 profiler 使用。此版本不自动安装/启动 Nsight，也不自动打开全 Python 函数追踪。
- 原生 profiler 使用成对的短 begin/end 标记定位日志 span 边界；跨 await 的真实时长以 JSONL 为准，未生成引擎内部 CUDA/Vulkan 内核测量。
- Kit warning 从 `omni.log` 消费回调收集，保留原始日志路径，不修改原有日志级别。回调仅入项目队列，不回调原生日志系统。不可用时 manifest 明确记录原因，不能把“未采集到”当“没有警告”。
- 警告记录首末时间、累计数，按 1/2/4/8… 次输出样例；关联标注 `direct` 或 `time_inferred`。缓存最多 1024 类警告，再按溢出类聚合；完整原始 Kit 日志仍保留。
- 文件写入由每进程独立线程完成。主队列和关键队列均有容量；溢出和 I/O 错误写入 summary。异常前历史使用有界 ring buffer，最多每 5 秒触发一次，循环 32 份，不保存图像/点云原文。
- 日志每两秒写检查点；进程崩溃时通常留下 `state=incomplete` 和不闭合 span。磁盘满不递归记录错误、不无限缓存，不让诊断队列反向阻塞渲染。
- 资源采样使用 `/proc`、cgroup 和已存在的 `nvidia-smi`；GPU 数字为整卡统计，不是某个传感器占用或 SM occupancy。未采集的字段保持缺失，不补零。

`tools/analyze_trace.py` 输出冷启动/稳定组阶段分布、每传感器耗时、重试原因、队列峰值、Kit 长更新间隔、警告数量、丢事件及不闭合 span。`--trace` 输出以本次记录起点为零的微秒时间线，避免 JavaScript 大整数丢精度；只保存本地文件，不上传。`--compare` 对照 manifest，不同任务配置会提示不可直接比较。

## 6. 原生验收清单

1. 关闭其他控制器，在独立 Isaac 会话加载既有场景，运行 v03；保存 Kit 日志路径。
2. 测量仅开面板、Initialize、初始化后 Idle、Pause、Close 后的更新间隔和 CPU/GPU，核对两类产品开关事件。单凭平均 GPU 利用率不能通过验收。
3. `smoke.json` 验证手动 Writer 触发/晚到窗口及 ROS 写包兼容性，再用 `diagnostic.json` 全选传感器采集 10 组。
4. 分别覆盖静止、关节运动、整机 XYZ/Yaw/Pitch/Roll、安装位姿更改后恢复、Pause/Resume、Stop、关闭、重开面板；场景替换应明确失败而不使用旧句柄。
5. 用 `validate_capture.py` 检查每组完整、共同时间、时间冻结、PNG 解码尺寸、点云字段、TF 与渲染位姿、CDR 哈希及分段。
6. 对比图像和点云，确认未降低预热、分辨率、视野或遮挡质量；读取 warnings，特别检查 Hydra 释放警告是否仍出现。
7. 使用相同场景、传感器选择、预热、PNG、预览、组数做旧版/新版独立会话 A/B；分别报告初始化、稳态 s/组、交互响应、重试频率和日志开销。不能将先前减少预热所得收益记入本轮。

已执行的子集与结果见部署测试报告；上面是完整回归清单，不能将短时小样本结果扩大为长期稳定性或旧版/新版性能提升比例。本地假对象测试只覆盖项目逻辑与资源交接合同。

## 7. API 依据

- [NVIDIA Replicator Python API](https://docs.omniverse.nvidia.com/kit/docs/omni_replicator/1.13.30/source/extensions/omni.replicator.core/docs/API.html)：手动 Writer、schedule_write、零时间步和完成等待接口；具体安装构建仍需验收。
- [NVIDIA Carbonite Python bindings](https://docs.omniverse.nvidia.com/kit/docs/carbonite/210.1.12/docs/python/bindings.html)：`omni.log` consumer 签名及禁止回调中重新进入日志接口的约束。
- [NVIDIA Kit profiling](https://docs.omniverse.nvidia.com/kit/docs/kit-manual/110.0.0/guide/profiling.html)：可选 profiler 标记。

上述页面仅用于核对公开 API，本次没有下载执行外部源码或依赖。
