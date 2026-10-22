# Warning 与剩余停顿

## 已保留的引擎 warning

本轮完整配置在 v05、v06 均出现以下类型。RunDiagnostics 按消息聚合次数、第一次/最后一次 monotonic 时间并保存来源样本；没有屏蔽或改写引擎日志。时间归属是推断，不证明消息对应代码导致了该次长帧。

| 类型 | 本轮判断与处理 |
|---|---|
| hydratexture 插件 interface already released | 一轮 8 组通常 160 次，和资源启停相关；SDK 内部生命周期热点，保留原文。新资源复用实验是否减少它，见性能证据。不能把 warning 清零等同于正确性证明。 |
| repeated acquired interface / getCachedInterface | hydratexture、rtxsensor、viewport 插件重复获取 Carb 接口；插件内部实现，本项目不能用替换 Python API 修复。没有随组数每组增长的全部类别。 |
| MotionBVH not enabled | 当前正式组冻结姿态、Instant LiDAR；不模拟扫描期间运动畸变。保持原要求，不能由这条 warning 单独断言冻结点云错误，也不能推导运动中扫描正确。 |
| Ill-formed SdfPath、channels VtArray<string> unhandled | 启动/资产插件类型处理 warning，通常每进程少量；根 USD 和传感器原始配置保留。当前解码/源姿态校验通过也不能证明所有材质和纹理没有问题。 |
| initial World0 UsdStage reference count 2 | 场景切换时旧默认 Stage 引用提示。记录 RSS/清理后进程显存，不直接解释为不断增长的泄漏。 |

## 未解决的长尾

轻量状态发布减少常态主线程成本，但完整任务启动/结束仍有约 0.7–0.9 秒的更新间隔。约 0.5 秒的一个回调已经细化到 PhysX→USD 同步且线程 CPU 接近墙钟；另一个最大间隔发生在我们的回调之外，靠近采集进程退出。

单张卡上的两个 Isaac 引擎各自持有 RTX 场景和显存。任务级协作让步发生在组边界，不能抢占正在执行的 Vulkan 队列或原生 CPU 调用。本轮不会把 CUDA Stream 优先级写成图形进程之间已经隔离，也不会用“GPU 没满”判定 GPU 路径无瓶颈。

后续可检验方向是持久采集进程减少反复上下文销毁，以及双卡显式分配后原生验证。它们涉及更长的资源生命周期和错误恢复，未作为本轮已验证的修复交付。保留完整画质与正确性优先。

定位时先对齐同实例 monotonic_ns 的 control_events、采集 diagnostics 和任务 status；再看慢帧的线程 CPU/墙钟及 NVTX/Vulkan trace。nvidia-smi 1 秒采样无法为一个 30 ms 函数提供精确 GPU 占用率。
