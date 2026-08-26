# 05｜并发、并行、线程池、队列与背压

对应源码：

- [npy_reader.py](../../semantic_pixel_ratio/io/npy_reader.py)
- [numpy_backend.py](../../semantic_pixel_ratio/backends/numpy_backend.py)
- [pipeline.py](../../semantic_pixel_ratio/pipeline.py)

## 1. 先把常混淆的词分清

### 串行

同一时刻只推进一项工作：

```text
读 batch 0 → 算 batch 0 → 读 batch 1 → 算 batch 1
```

总时间近似：

```text
T ≈ Σ(T_read + T_compute)
```

### 并发 concurrency

多项工作在时间上交错推进，不保证物理上同时执行。单核 CPU 也能通过任务切换实现并发。

### 并行 parallelism

多项工作在同一时刻由不同执行单元真正执行，例如：

- 多个 CPU core；
- CPU 与 GPU；
- GPU 的多个 SM；
- 磁盘读取与 CPU 计数。

### 异步 asynchronous

发起操作后，调用者不必原地等到全部完成，可以做其他事或稍后等待结果。异步描述控制流，不自动等于并行或更快。

### 流水线 pipeline

把任务拆成阶段，让不同数据批次同时处于不同阶段：

```text
时刻 1：读 batch 0
时刻 2：算 batch 0 || 读 batch 1
时刻 3：算 batch 1 || 读 batch 2
```

稳定阶段理想吞吐接近：

```text
max(T_read_per_batch, T_compute_per_batch)
```

而不是两者之和。

## 2. 本项目的线程拓扑

NumPy 后端运行时，至少有三层角色：

```text
主线程
├── 消费 LoadedBatch
├── 调用后端
├── 校验和提交账本
└── 写最终报告

semantic-batch-producer 线程
├── 把 pairs 切成 batch
├── 管理 reader 线程池
└── 把 LoadedBatch 放入有界 Queue

semantic-npy-reader-* 线程池
└── 每个任务加载一对 whole/reference 文件

semantic-numpy-counter-* 线程池
└── 每个任务统计一帧的两个来源
```

GPU 后端没有 NumPy counter pool，但主线程会发起 GPU 操作；reader 线程仍可为下一批读盘。

## 3. 生产者—消费者模式

`PrefetchingNpyReader` 是生产者，pipeline 主循环是消费者。

核心容器：

```python
queue.Queue(maxsize=ring_slots)
```

生产者：

```text
pairs → chunks → _load_batch → queue.put
```

消费者：

```text
queue.get → yield LoadedBatch → backend.count_batch
```

队列既传数据，也传控制消息：

| 消息 | 含义 |
|---|---|
| `LoadedBatch` | 正常数据 |
| `_ReaderEnd` | 所有 batch 生产完成 |
| `_ReaderFailure(error)` | 后台发生异常 |

这避免后台异常只打印在线程中却不让主任务失败。

## 4. 一批文件怎样并行读取

`_load_batch` 对一个 batch 的每个 `FramePair` 提交任务：

```python
pool.submit(load_pair_arrays, pair, contract)
```

每个任务内部顺序读取：

```text
whole .npy
reference .npy
```

不同 frame pair 可以由不同线程同时读取。

随后 producer 按 batch 内原顺序调用：

```python
future.result()
```

即使后面的 future 先完成，也会按 index 复制进连续数组，因此输出顺序始终与 pairs 顺序一致。并行完成顺序不会改变 ordinal。

## 5. 为什么线程能帮助 I/O

机械或固态存储、操作系统 page cache、文件打开和读取都有等待时间。一个线程等待 I/O 时，其他线程可以推进别的请求。

但线程不是越多越快：

- 单块盘的顺序带宽有上限；
- 数万个小文件可能受 IOPS 和 metadata 限制；
- 太多并发请求会使访问更随机；
- 每个线程有调度和内存开销；
- 网络文件系统可能有自己的并发限制。

因此 `reader_threads=4/8/16/32` 是需要基准测试的候选，不是“32 必定比 8 快”。

## 6. Python GIL 到底影响什么

CPython 的 Global Interpreter Lock 使同一进程内通常只有一个线程在执行 Python bytecode。

这不代表 Python 线程永远不能并行：

- 阻塞文件 I/O 时会释放 GIL；
- NumPy 的许多重型循环在 C/C++ 中执行，并可能释放 GIL；
- GPU kernel 在设备上执行，不占用 Python GIL。

项目线程的主要工作是 `np.load`、`np.copyto`、`np.bincount`，大量实际工作发生在原生实现或 I/O 中，所以线程池有机会产生重叠。

但“某个 NumPy 版本中的某个操作是否释放 GIL、是否内部还会开线程”是实现细节，最终要靠基准和 profiler，而不是凭口号判断。

## 7. NumPy 后端为何再开一个线程池

一个 batch 有 B 帧，`NumpyBackend.count_batch` 为每帧提交 `_count_frame`：

```text
frame 0 → worker 0
frame 1 → worker 1
...
```

每个 worker 负责该帧的两个来源和五个目标，返回 `[2,5]`。主线程按 future 列表顺序 `stack` 成 `[B,2,5]`。

这样避免多个线程写同一个共享输出区域，也不需要锁或 atomic。每个 worker 返回私有小数组，最后由主线程合并。

## 8. 背压为何重要

假设 producer 每秒能读 20 个 batch，后端每秒只能算 5 个。如果队列无界：

```text
积压速度 = 15 batch/s
```

450 MiB/batch 时，十秒就可能积压约 67.5 GiB，最终耗尽内存。

有界队列满后，`put(timeout=0.1)` 暂停并反复检查 stop event。下游速度自然限制上游。

背压解决的是**资源上界**和**系统稳定性**，不保证更快。队列太小可能无法掩盖抖动，太大则占内存且可能污染 page cache。

## 9. `ring_slots` 的准确含义

当前：

```text
ring_slots = Queue 中最多等待消费的 LoadedBatch 数
```

它不是：

- 固定预分配的 NumPy buffer 池；
- pinned memory 槽；
- CUDA stream 数；
- 同时在 GPU 上运行的 batch 数；
- 规划文档里的完整 slot 状态机。

每次 `_load_batch` 都调用 `np.empty` 创建新数组；GPU 后端每批还可能调用 `.pin_memory()` 创建 pinned 副本。

## 10. 内存上界怎样估算

单 batch payload：

```text
M_batch = B × 2 × H × W × bytes_per_element
```

仅队列 payload：

```text
M_queue ≤ ring_slots × M_batch
```

实际峰值还要加：

```text
主线程当前 batch
+ producer 正在构造的 batch
+ producer futures 已加载的单帧 arrays
+ GPU pinned host 副本
+ GPU device_data
+ Torch bool 临时量或 Triton partial
+ Python/线程/文件系统缓存开销
```

以 720p、uint16、B=128：

```text
M_batch = 450 MiB
ring_slots=3 的队列本身最多 1.35 GiB
```

考虑 producer、consumer 和临时副本后，host 峰值达到数 GiB是正常可能性。规划时不能只算队列。

## 11. reader 的停止协议

迭代器 `finally` 中：

```text
设置 stop event
清空 queue
join producer，最多等 10 秒
```

producer 的 `_put` 使用 0.1 秒超时，而不是永久阻塞，因此能定期看到 stop event。

如果消费者因后端异常退出：

- stop event 通知 producer 不再继续；
- 清空 queue 释放 batch 引用；
- join 尝试回收 producer。

已经在 `np.load` 中阻塞的线程无法被 Python 强行安全取消，只能等待底层操作返回，所以 join 设有超时。

## 12. 并行完成顺序与确定性

项目没有采用“谁先完成就先提交谁”的 unordered 模式：

- batch 顺序由 `_chunks` 固定；
- batch 内 futures 按原 index 收集；
- backend futures 按帧顺序 stack；
- ledger 要求 ordinal 恰好等于下一连续范围。

这牺牲了少量“绕过慢帧”的灵活性，换来简单可靠的恢复语义和确定顺序。

## 13. 线程数相互影响

NumPy 模式同时有：

```text
reader_threads + cpu_workers + 主线程 + producer
```

若 `reader_threads=32, cpu_workers=64`，并不表示可以稳定利用 96 核：

- I/O worker 和 counter worker 可能同时争 CPU；
- `np.bincount` 受内存带宽限制；
- 操作系统 page cache 和复制也消耗内存带宽；
- NumPy 自身依赖库有时还会开内部线程；
- 过量线程增加 context switch。

合理策略：

1. 单独测读取吞吐；
2. 单独测 CPU 计数吞吐；
3. 再测端到端；
4. 观察 CPU 利用率、磁盘吞吐、队列空/满比例；
5. 每次只改一组参数。

## 14. 为什么当前没用多进程

多进程能绕过 GIL，但代价包括：

- 大型 batch 在进程间传输可能复制或需要 shared memory；
- 进程启动和序列化开销；
- 生命周期与异常恢复更复杂；
- 多进程共同写账本需要额外协调；
- NumPy 核心循环本来就在原生代码中。

这不意味着多进程永远不合适，而是要证明收益能覆盖数据搬运和复杂性。

## 15. 用时间线判断瓶颈

三种典型情况：

```text
情况 A：Queue 经常为空
解释：reader 供不上，I/O 或加载/复制是瓶颈

情况 B：Queue 经常满
解释：后端慢，producer 被背压

情况 C：Queue 有时空有时满
解释：两段速度接近或存在 I/O 抖动
```

当前代码没有记录 queue occupancy 指标。进阶优化可加入低开销统计，但不能在每个像素或每次短轮询上打印日志，否则测量本身会干扰性能。

## 16. 本章自检

1. 并发、并行、异步、流水线分别是什么？
2. 当前 reader 的 producer 和消费者是谁？
3. `future.result()` 按顺序等待为何仍可能有读取并行？
4. GIL 为什么没有让本项目线程池必然失效？
5. Queue 有界为什么限制不了全部内存恰好为 `ring_slots × M_batch`？
6. Queue 经常为空和经常满分别说明什么？

