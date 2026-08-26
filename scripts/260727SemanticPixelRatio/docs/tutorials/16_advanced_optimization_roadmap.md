# 16｜进阶优化路线：从 pinned ring 到 GDS

本章讲如何继续实现规划中的加速，并说明每项技术解决哪个瓶颈。顺序基于当前“读取远慢于 Triton 热态计数”的实测，不是按技术听起来有多高级排序。

## 1. 优化必须守住统一接口

任何新后端/reader 都应保持：

```text
FramePair 顺序
DatasetContract
LoadedBatch [B,2,H,W]
BatchCounts [B,2,5] integer
连续 ledger append
NumPy cross-check
```

若优化需要改变内存对象，可扩展模型，但最终提交账本前必须回到相同整数语义。

修改缓存有效性语义时，更新：

```text
PIPELINE_VERSION
manifest schema / fingerprint
tests
```

## 2. 第一优先：真正可复用的 pinned-memory ring

### 当前问题

每批：

```text
np.empty pageable batch
→ 单帧 arrays copy 进去
→ torch.pin_memory 再复制
```

重复分配与复制大量 host 内存。

### 目标

启动时分配固定 slots：

```text
slot[i].host_data [B,2,H,W] pinned
slot[i].frame_ids
slot[i].state
```

reader 直接把 payload 填入 pinned slot，GPU H2D 直接使用。

### 状态机

```text
FREE
→ FILLING
→ READY
→ COPYING
→ COMPUTING
→ RESULT_READY
→ FREE
```

每次状态转换必须有单一所有者或同步原语，防止 reader 在 GPU 尚未完成时覆写 buffer。

### 难点

- NumPy 怎样安全获得 pinned buffer view；
- 单帧 `np.load` 仍先创建数组，怎样直接读 payload；
- 最后一批不足 B 的有效长度；
- 异常时所有 slot 如何回收；
- buffer 不能在异步 H2D 完成前复用；
- pinned 总量不能过大。

### 验证

- 地址在多个 batch 间保持固定；
- RSS/pinned usage 有界；
- counts 与 NumPy相同；
- 提前异常不死锁；
- 长跑无 slot 泄漏。

## 3. 第二优先：多 stream 与 event

有固定 slots 后，可构建：

```text
slot 0: H2D batch n+1
slot 1: kernel batch n
slot 2: D2H counts batch n-1
slot 3: reader filling batch n+2
```

### 依赖

每 slot 记录 events：

```text
host_ready
copy_done
kernel_done
result_done
```

不要每批全局 synchronize。主线程只在准备提交对应 ordinal 时等待该 slot 的 result event。

### 顺序问题

GPU batches 可能完成顺序不同。ledger 只接受连续 ordinal，可以：

- 保持小型 reorder buffer；
- 或提交时按 next ordinal 等待；
- 绝不能按完成顺序乱写账本。

### 是否能重叠

取决于 GPU copy engines、kernel 资源、PCIe 和 pinned memory。若 kernel 已占满全部 SM/带宽，多 stream 不一定并行更快。

## 4. 第三优先：packed 连续缓存

小文件的成本：

```text
2N 次 open
2N 个 NPY header
metadata lookups
随机/碎片化 I/O
```

首次预处理生成：

```text
packed/
├── whole_scene.uint16.bin
├── excavator_only.uint16.bin
├── frame_index.json
└── cache_manifest.json
```

### 收益

- 两个大文件顺序读；
- 更容易大块 pread/io_uring；
- 更容易直接读到固定 buffer；
- 重复分析非常快；
- page cache/预读更有效。

### 代价

- 首次打包仍需读写全部数据；
- 占额外磁盘；
- 需要强 fingerprint；
- 中途中断的打包也需事务/恢复；
- frame index、endianness、dtype、shape 必须记录；
- packed cache 与原输入失效关系要清楚。

一次性分析可能不划算；反复改标签/报告则很有价值。

## 5. 第四优先：Linux `io_uring`

`io_uring` 允许批量提交异步 I/O 请求，减少每次 read 的系统调用和线程调度开销。

适用目标：

- Linux；
- 大量文件或大块读取；
- 注册文件/固定缓冲；
- reader 成为确定瓶颈。

实现工作：

- 解析 NPY header 得到 payload offset；
- 校验 dtype/shape/order；
- 批量提交 whole/reference reads；
- 直接读入预定 slot；
- 处理短读、错误、取消；
- 与 slot 状态机和 Python 生命周期连接；
- C++/Rust/pybind 原生扩展。

只把 Python ThreadPoolExecutor 改名为 io_uring 不算实现。需要真正在 Linux 原生接口上验证。

## 6. CUDA Graph

在固定 pinned/device addresses 和固定 batch shape 后捕获：

```text
H2D
kernel 1
kernel 2
D2H counts
```

### 难点

- 最后一批不足 B，可填充并用 valid_frames mask，或另有 graph；
- host/device 地址必须稳定；
- Triton/PyTorch 操作是否可安全 capture；
- graph 与多 stream/event 协调；
- target IDs/shape specialization。

### 价值判断

它减少 CPU launch 开销，不减少 NPY 读取字节数，也不减少 H2D payload。必须先测 timeline 中 launch gaps 的占比。

## 7. AVX-512/OpenMP CPU 后端

目标算法：

```text
每线程处理连续像素范围
→ vector load uint16
→ 与五个 broadcast ID 比较
→ 私有 counters
→ 线程结束后一次 reduce
```

### 为什么不用每像素 atomic

共享十个 counter 会产生 cache line contention。每线程私有 counter 几乎没有同步，最后合并十个数成本很小。

### 工程要求

- C++/OpenMP/pybind；
- 编译工具链；
- CPUID feature detection；
- AVX-512/AVX2/scalar 多版本分发；
- 处理 alignment/tail；
- NUMA/线程绑定；
- Windows/Linux 构建；
- 与 NumPy逐整数验证。

### 适用场景

- page cache 热；
- GPU 被占用；
- PCIe 成为瓶颈；
- 服务器 CPU 核数和内存带宽强；
- 磁盘供给足以让 CPU 工作。

## 8. 实测自动调优器

当前 `auto`：

```text
有 Triton 就选 Triton
```

真正 autotuner 应在少量代表性帧上测：

```text
reader_threads
batch_frames
ring_slots
backend
block_pixels/num_warps
streams
```

### 设计原则

- 预热 JIT；
- 区分 cold/warm I/O；
- 样本包含代表性 shape/dtype；
- 检查所有候选 counts 相等；
- 控制总调优时间；
- 把硬件/软件/数据契约作为调优缓存 key；
- 不让调优结果破坏总内存上限；
- 给用户可重现的选择报告。

“选择理论上更先进的后端”不是自动调优。

## 9. GDS / cuFile

GPUDirect Storage 目标是让存储数据更直接进入 GPU memory，减少 CPU staging。

需要整条链支持：

- NVIDIA 驱动与 `nvidia-fs`；
- cuFile；
- 兼容 GPU/NVMe/PCIe 拓扑；
- 文件系统和挂载支持；
- 对齐与 buffer 约束；
- 容器权限；
- 可验证的实际 direct path。

当前数据是数万个带 header 的小 NPY 文件，并不天然适合 GDS。更合理的前置步骤通常是 packed 连续文件。

不能只因为有 4090 和 NVMe 就假设 GDS 可用。先运行官方环境检查/样例，再设计 reader。

## 10. 异构 CPU/GPU work stealing

构想：

```text
GPU 处理主要 batch
CPU AVX 后端处理 GPU 队列溢出
调度器预测哪边更早完成
```

风险：

- CPU/GPU 同时争 host memory bandwidth；
- 两边都依赖同一磁盘；
- reordering 复杂；
- NUMA/PCIe 影响；
- 结果必须按 ordinal 合并；
- 调度开销与预测误差。

如果磁盘已经饱和，同时开 CPU/GPU 不会凭空增加输入吞吐。只在分阶段基准证明资源有余量后实现。

## 11. 报告层可优化项

相比读取通常很小，但超大 N 时可：

- 从 parts 流式生成 CSV，避免 `load_all` 全部 frame IDs；
- summary 用 uint64 streaming accumulators；
- 分位数用外存/近似算法（若允许）；
- cache 与 CSV 并行写不同设备；
- 为报告再生成提供独立 CLI。

任何近似 median 都是输出语义变化，必须显式标注，不能悄悄替代 exact median。

## 12. 输入内容 checksum

当前 fingerprint 用 size+mtime。强校验可在首次 payload 读取时：

```text
边读边 hash
→ part 记录输入 checksum
→ cache manifest 持久化
```

难点：

- 多线程完成顺序与 manifest 顺序；
- 不重复读数据；
- hash CPU 成本；
- 算法选择（SHA-256 强但成本高，快速 hash 风险不同）；
- partial crash 后哪些 hash 已可信。

## 13. 推荐实施顺序

基于远端 64 帧热态实测：

```text
reader 111.4 ms
pageable→pinned 10.3 ms
H2D 35.2 ms
Triton 两 kernel 0.327 ms
```

以及 1026 帧中 Torch/Triton 端到端接近的结果，推荐：

1. 加阶段 timing、queue occupancy、RSS/VRAM 指标；
2. 固定可复用 pinned ring；
3. 多 stream/event 跨批流水；
4. packed 连续缓存；
5. Linux io_uring reader；
6. 固定 buffer 后评估 CUDA Graph；
7. AVX-512 CPU 后端；
8. 实测 autotuner；
9. 检查环境后评估 GDS；
10. 最后评估 CPU/GPU 混合调度。

每一步都先做小规模正确性、失败注入、长跑内存和端到端基准。

这些数字的版本、cache 口径和完整实验见 [第 19 章](19_remote_gpu_validation.md)。若换存储、GPU 或数据规模，应重新测量后再排序。

## 14. 新优化的验收模板

### 正确性

- NumPy逐整数全样本一致；
- ID=0、缺失 target、尾 tile、尾 batch；
- 不同 batch/stream 顺序一致；
- resume 跨新旧后端一致。

### 性能

- 冷/热端到端；
- 分阶段时间；
- CPU/GPU/磁盘利用；
- 多次中位数；
- 对照未优化基线。

### 资源

- 最大 RSS；
- pinned memory；
- VRAM；
- 文件描述符；
- 随 N 增长是否泄漏。

### 恢复

- 在 fill/copy/kernel/D2H/append/report 各阶段注入失败；
- 无半提交 part；
- slot 不死锁；
- 相同配置可续跑。

## 15. 本章自检

1. 为什么 pinned ring 应排在 CUDA Graph 前？
2. packed cache 为什么可能比 GDS 更现实？
3. io_uring 解决什么，不解决什么？
4. AVX 后端为什么使用线程私有 counter？
5. 异构调度为什么可能让性能更差？
6. 新优化为什么可能要求提升 pipeline version？
