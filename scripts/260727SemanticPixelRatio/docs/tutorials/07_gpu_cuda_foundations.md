# 07｜从零理解 GPU、CUDA 与性能模型

这一章先建立 GPU 心智模型，下一章才逐行看代码。你不需要先会 CUDA C++。

## 1. CPU 和 GPU 的设计目标

### CPU

CPU 擅长：

- 少量复杂线程；
- 分支、操作系统、通用控制流；
- 大 cache；
- 低延迟；
- 单线程性能。

### GPU

GPU 擅长：

- 大量相似、独立的小任务；
- 高吞吐；
- 让成千上万个线程隐藏内存等待；
- 高显存带宽。

semantic 计数很适合 GPU 的部分是：每个像素执行相同的“五个 ID 比较”。它不适合 GPU 的部分是：数据最初位于磁盘和 CPU 内存，计算本身又很简单，数据搬运可能比计算更贵。

## 2. Host 与 Device

CUDA 语境中：

```text
host   = CPU 及系统内存
device = GPU 及显存
```

普通 NumPy 数组在 host memory。GPU kernel 不能直接把它当作本地显存高速读取，通常需要：

```text
磁盘 → host memory → device memory → kernel → 小结果回 host
```

传输方向：

```text
H2D = Host to Device
D2H = Device to Host
```

## 3. 为什么 GPU 不一定更快

端到端时间包括：

```text
文件打开与磁盘读取
+ CPU 整理 batch
+ pageable→pinned copy
+ H2D
+ kernel launch
+ kernel
+ D2H counts
+ 同步等待
+ 账本与报告
```

若 kernel 只用 19 ms，而读文件用 435 ms，即使把 kernel 优化到 0 ms，单纯按这两个阶段相加的上限提升也只有：

```text
(435+19)/435 ≈ 1.044
```

约 4.4%。这就是 Amdahl 定律的直觉：只优化小占比阶段，端到端收益有限。

## 4. CUDA 执行层次

常用概念：

```text
thread  → 单个逻辑执行实例
warp    → NVIDIA GPU 通常以 32 个线程为一组调度
block   → 一组协作线程
grid    → 一次 kernel launch 的全部 block
SM      → GPU 上执行 blocks 的流式多处理器
```

Triton 不要求你手写每个 CUDA thread 的索引，但仍然映射到 GPU 的并行执行模型。一个 Triton program instance 类似一个 tile 级工作单元。

## 5. SIMT：相同指令，大量数据

GPU 适合：

```text
pixel 0: 比较 id1...id5
pixel 1: 比较 id1...id5
...
```

这叫 Single Instruction, Multiple Threads 的风格。

若同一 warp 中线程走不同分支：

```text
一半执行 if
一半执行 else
```

GPU 可能需要分时执行两条路径，叫 branch divergence。当前计数逻辑几乎没有数据相关复杂分支，适合 GPU。

## 6. GPU 内存层次的直觉

从快且小到慢且大，可粗略理解：

```text
register
shared memory / L1
L2 cache
global device memory
PCIe/NVLink 后的 host memory
磁盘
```

项目的主要策略：

- 从 global memory 连续读取 semantic pixels；
- 在寄存器/程序局部做比较和局部归约；
- 只把小 partial 写回；
- 第二次小归约得到 `[B,2,5]`；
- 只 D2H 回传计数。

## 7. 合并访问 coalescing

GPU 相邻线程读取相邻地址时，硬件能高效合并内存事务。

项目 batch 是 C-contiguous：

```text
[frame0 whole pixels][frame0 ref pixels][frame1 whole pixels]...
```

Triton 一个 tile 使用连续 `offsets`，所以同一 program 的线程读取连续像素。这比随机访问更能利用显存带宽。

## 8. Kernel launch 有固定开销

CPU 发起一个 GPU kernel 需要调度。对巨大计算这点开销可忽略，对极小 kernel 可能占主要比例。

不理想设计：

```text
每帧 × 每标签都 launch 一次
```

一万帧、五标签就可能产生五万次 launch。

当前 Triton 设计一次 launch 处理整个 batch 的所有帧和 tile，再用第二个 launch 归约，不会按帧/标签从 Python 循环 launch。

## 9. Reduction 归约

计数本质上是把很多局部 0/1 相加：

```text
[1,0,1,1,0,...] → sum → count
```

并行归约常采用树形结构：

```text
8 个值
→ 4 个局部和
→ 2 个局部和
→ 1 个总和
```

若每个像素都对同一个全局 counter 做 atomic add：

- 大量线程争用少数地址；
- atomic 序列化；
- 成为热点。

当前 Triton 使用两阶段：

```text
每 tile 得 10 个 partial
→ 每帧/来源/target 再合并 tiles
```

全程无需每像素全局 atomic。

## 10. Pinned memory 是什么

普通 pageable host memory 可能被操作系统换页。CUDA 做异步 DMA 传输时需要地址稳定的 page-locked/pinned memory。

大致路径：

```text
pageable NumPy
  → pin_memory() 复制到 pinned host buffer
  → non_blocking H2D
```

优点：

- 支持真正的异步传输；
- H2D 通常更稳定、更高效。

代价：

- pinning 有开销；
- 当前每批临时 `.pin_memory()` 会多一次 host copy；
- pinned memory 太多会压缩操作系统可分页内存，影响全机。

理想优化是预分配少量固定 pinned buffers，reader 直接填入并循环复用，而不是每批临时 pin。

## 11. `non_blocking=True` 不等于自动流水并行

满足真正传输—计算重叠通常需要：

1. pinned host memory；
2. non-blocking copy；
3. 支持并发的 GPU/驱动；
4. 不同 CUDA streams；
5. 正确 event 依赖；
6. 不立即执行会强制等待的 host 操作；
7. buffer 生命周期持续到异步操作完成。

当前代码有前两项的一部分，但没有显式多 stream 和跨 batch 调度；每批最后 D2H `.numpy()` 前必须等 GPU 结果。因此不能只看到 `non_blocking=True` 就断言 H2D、kernel、D2H 已经完全重叠。

## 12. Stream 与 Event

### Stream

stream 是设备工作的有序队列。同一 stream 中：

```text
copy A → kernel A → copy result A
```

按提交顺序执行。

不同 stream 之间在硬件允许且资源足够时可以重叠。

### Event

event 用于表达依赖：

```text
copy stream 完成 H2D
→ 记录 event
→ compute stream 等 event
→ 启动 kernel
```

若每批都调用全局 `cuda.synchronize()`，会等待所有 stream，破坏细粒度流水。正确做法通常只等待对应 slot/batch 的完成 event。

## 13. CUDA Graph

常规运行每批都由 CPU重新提交 copy/kernel 等操作。CUDA Graph 可以捕获固定操作图并重复 replay，减少 launch 和调度开销。

它适合：

- batch shape 固定；
- 内存地址固定；
- 操作序列固定；
- kernel 很短，launch 开销占比明显。

当前最后一批大小可能不同，buffer 每批新建，pinned 地址不固定，所以还不具备直接捕获的完整条件。即使实现，若磁盘读取占 95%，端到端收益也有限。

## 14. 算术强度与 Roofline 直觉

算术强度：

```text
每读取 1 byte 数据，做多少计算
```

semantic 计数对一个 `uint16` 像素只做五次整数比较和少量加法，算术强度较低，通常更像显存带宽型任务，而不是算力型任务。

因此优化重点是：

- 每个像素少读几次；
- 不写大 bool mask；
- 连续访问；
- 减少 H2D 和 host copy；
- 让 I/O、copy、compute 重叠。

购买或使用更多浮点 Tensor Core 算力，不会自动让整数像素计数同比加速。

## 15. GPU 利用率为何可能很低

可能原因：

- batch 太小；
- GPU 等磁盘；
- CPU pinning/copy 太慢；
- 每批同步造成空洞；
- kernel launch 过碎；
- kernel occupancy 不佳；
- GPU 同时被 Isaac Sim 占用；
- PCIe 带宽受限；
- 首次 Triton JIT 编译计入时间。

`nvidia-smi` 中瞬时利用率低只是一条线索，不能直接断定 kernel 慢。要结合时间线 profiler 区分 GPU 是在工作、等数据还是根本没有任务。

## 16. 正确计时 GPU

GPU 操作通常异步。下面的 CPU 计时可能只测到“提交”：

```python
t0 = time.perf_counter()
launch_kernel()
elapsed = time.perf_counter() - t0
```

精确 kernel 时间应使用 CUDA Event，或在计时边界明确 synchronize。端到端时间则应包含真实等待，但把 Triton 首次 JIT 编译与热态运行分开。

至少区分：

```text
cold time   = import + context + JIT + allocation + 首次运行
warm time   = 已编译后重复 batch
end-to-end  = discovery + I/O + copy + compute + ledger/report
```

## 17. 何时优先 CPU

CPU 可能更好：

- 数据已经在系统 page cache；
- 图像较小或帧数少；
- GPU 初始化/JIT 占比大；
- PCIe 传输占主导；
- GPU 正忙；
- 没有兼容 CUDA/Triton；
- NumPy `bincount` 已经快于磁盘供给。

因此 `auto` 理想状态应做实测调优。当前 `auto` 只是优先用可用的 Triton，不能保证端到端最快。

## 18. 远端实测怎样印证本章

RTX 4090、64 帧 720p `uint16` 热态实测：

```text
warm reader                 111.4 ms
pageable→pinned              10.3 ms
pinned H2D                   35.2 ms
Torch 五目标算子             13.1 ms
Triton 两个 kernel            0.327 ms
```

Triton 纯 kernel 约比 Torch 通用算子快 40 倍，但 H2D 又约为 Triton kernel 的 108 倍。1026 帧完整 pipeline 中，Torch 中位数 2.720 s，Triton 2.837 s，二者远没有 40 倍差距。

这组数据真实展示了：

- kernel microbenchmark 不能代替端到端 benchmark；
- 算术已极快时，I/O 和数据搬运主导；
- `auto` 选择 Triton 只代表能力优先级；
- 小样本上 GPU 固定启动成本可能完全压过计算收益。

实验设计和全部版本见 [第 19 章](19_remote_gpu_validation.md)。

## 19. 本章自检

1. 为什么 semantic 计数更像带宽型而不是算力型任务？
2. H2D 与 D2H 分别是什么？
3. pinned memory 的收益和代价是什么？
4. 为什么 `non_blocking=True` 不能单独证明跨 batch 重叠？
5. 为什么每像素 global atomic 不好？
6. kernel 已经很快时，为什么 CUDA Graph 可能对端到端帮助很小？
7. 为什么 Triton kernel 快 40 倍，完整 pipeline 却没有快 40 倍？
