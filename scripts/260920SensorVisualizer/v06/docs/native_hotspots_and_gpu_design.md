# 原生热点与 GPU 技术取舍

## 本轮真实追踪

使用实例已安装的 Nsight Systems 2025.1.1，采集 Vulkan、CUDA、NVTX、OS runtime 和 CPU 调度。完整配置、冻结姿态、单张 L40；只追踪第二组的一次窗口，避免把完整追踪开销混入普通性能对照。

证据：reports/native_trace_analysis.json。原生文件保存在远端 output/sensor_visualizer/v06/native_trace/1791605377202176681/。

| 范围 | 墙钟 | 主线程被调度运行 | 记录的 CUDA/图形 GPU 区间并集 |
|---|---:|---:|---:|
| 整个追踪组 | 9.039 s | 8.755 s | 5.670 s |
| 冻结预热 | 8.051 s | 7.908 s | 5.382 s |
| 正式渲染及回调 | 0.655 s | 0.640 s | 0.274 s |

Vulkan batch 区间不等于 SM 占用率；表内时间互相重叠，不能相加。CPU 调度运行也可能包含驱动轮询。单组带 profiler 的结果用于定位，不能作为普通吞吐验收。

整个窗口 cudaFreeHost 2561 次，包含墙钟 1.850 s；cudaHostAlloc 3666 次，0.555 s。预热还出现 vkAllocateMemory 1248 次、vkGetMemoryFdKHR 1149 次。正式渲染内两种主机分配/释放各 52 次，cudaFreeHost 包含墙钟约 0.394 s。API 时间可能包括驱动等待和隐式同步，不能全部归为纯分配成本，计数也不能直接证明每个内部对象的归属。

项目自己的 17 路 host_materialize 合计约 4.0 ms，cpu_owned_copy 合计约 11.6 ms。相机回调是 warp CUDA:0 数组；十三路点云回调是 warp CPU 数组。Articulation 根姿态返回值也是 CPU 数组。不能把所有 .numpy() 都当成 GPU→CPU DMA。

## 内存与传输链路

交互诊断还捕获到一次 507 ms 的主线程更新，其中 PhysX `update_transformations(False, True, False, False)` 写回 USD 占约 500.594 ms 墙钟、500.479 ms 线程 CPU。它发生于另一个采集进程初始化期间。这里有实际 CPU 执行，不能把这次停顿全部解释成等待 GPU。精确缓存可避免未改变的姿态重复进入它，但移动中的必要同步仍保留。

另一个最长更新间隔约 744 ms 出现在采集任务结束附近，轻量发布版本自己的更新函数最大仅约 11 ms。这证明间隔大部分发生在我们的更新回调之外；GPU/引擎清理和上下文竞争是待验证的解释，尚未定位到具体驱动函数。不同实验的长尾没有确定改善。

图形侧持有 Vulkan/RTX 资源，CUDA 通过外部内存与信号量进行部分互操作。SDK 已执行大量内部复制和缓冲管理。相机 CUDA 数组经 numpy() 得到 CPU 数据，再独立复制，随后后台打包到 mmap。点云在回调边界已经在 CPU，仍独立复制以脱离 SDK 的复用生命周期。

保留独立复制是当前正确性边界。擅自把 SDK 指针送到后台线程，或在回调结束后继续异步访问，可读到被复用的数据。现有三槽缓冲和代数编号只能保护我们自己的 mmap，不能自动保护 SDK 的 GPU 数组。

## Stream/Event 的适用边界

若要把我们控制的 D2H 复制异步化，必须同时具备：生产流完成信号、可保持有效的源指针、锁页主机槽、独立复制流、完成 Event、消费方等待，以及取消/异常时的生命周期保护。只调用 cudaMemcpyAsync 或创建高优先级 Stream 并不能满足这些条件。

CUDA Stream 的优先级不能直接控制另一个 Isaac 进程的 Vulkan/RTX 队列。当前没有得到 RTX Producer 的明确可转移生产 Event 和跨回调生命周期承诺，不能把我们创建的 Event 当作渲染完成证据。

官方技术依据：[CUDA 异步执行](https://docs.nvidia.com/cuda/cuda-programming-guide/02-basics/asynchronous-execution.html)、[Nsight Systems 用户指南](https://docs.nvidia.com/nsight-systems/UserGuide/index.html)。公开文档访问是自报记录；本轮没有据此下载外部文件。

## C++/CUDA 候选与决定

可控制的候选包括 RGBA→RGB、点云坐标处理、复制到锁页槽和编码前布局整理。但当前这些工作占整组很小比例；向 GPU 再上传 CPU 点云会增加传输，且当前接口只输出 XYZ，没有需要大型并行计算的点云算法。

因此本轮先交付有实测依据的主线程和所有权优化，没有添加用于展示的 CUDA 内核，也没有拦截引擎 cudaFreeHost、修改全局 LD_PRELOAD 或闭源 RTX 插件。

后续最小验证方向：在独立实验入口中，核实相机 CUDA 数组的持有和生产同步契约；用现有 Warp/CUDA 能力创建三槽锁页池与复制流/Event，逐帧与当前 CPU 输出逐字节对比，并检查 Stop/失败排空。只有端到端收益超过维护成本才进入正式管线。引擎内部主机分配热点还需 SDK 生命周期或上游插件层面的支持，不能由我们的 mmap 池直接消除。

## 学习入口

先看 performance_evidence.md 的对照数据，再看 motion_update.py 的脏状态、control_ipc.py 的不可变状态代、hot_path_metrics.py 的墙钟/线程 CPU 时间，最后沿 sensors.py → pipeline.py → buffers.py → record_worker.py 追踪所有权。把测量范围、等待、复制和复用分清，比先写一个 CUDA kernel 更接近这次真实问题。
