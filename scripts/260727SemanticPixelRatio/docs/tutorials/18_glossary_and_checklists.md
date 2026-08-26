# 18｜术语表、公式表与检查清单

## 1. 术语表

| 术语 | 本项目中的含义 |
|---|---|
| semantic ID | 每个像素所属语义类别的整数编号 |
| mapping | label 字符串到 semantic ID 的映射 |
| whole scene | ratio numerator，完整场景语义图 |
| reference | excavator-only denominator 语义图 |
| frame ID | 从文件名提取的业务标识 |
| ordinal | 排序后从 0 开始的内部连续位置 |
| contract | 全数据统一 shape/dtype 等必须条件 |
| batch | 一次读取/计数的一组帧 |
| backend | 实现 `[B,2,H,W]→[B,2,5]` 的算法 |
| histogram | 值到出现次数的数组 |
| concurrency | 多任务交错推进 |
| parallelism | 多执行单元真正同时工作 |
| asynchronous | 发起后不必立即阻塞等待 |
| producer | 读取并产生 LoadedBatch 的一方 |
| consumer | 从 queue 取 batch 并计数的主流程 |
| backpressure | 有界队列满时下游反向限制上游 |
| GIL | CPython 执行 Python bytecode 的全局锁 |
| host | CPU 与系统内存侧 |
| device | GPU 与显存侧 |
| H2D / D2H | host-device 两方向的数据传输 |
| pinned memory | 页锁定、适合异步 DMA 的 host memory |
| CUDA stream | GPU 操作的有序提交队列 |
| CUDA event | stream 间依赖和设备计时原语 |
| kernel | 在 GPU 上执行的函数 |
| launch | CPU 向 GPU 提交 kernel |
| grid | 一次 kernel 的全部并行 program/block |
| warp | NVIDIA GPU 常见的 32 线程调度组 |
| tile | 一帧中由一个 Triton program 处理的连续像素段 |
| reduction | 把许多局部值合并成一个总值 |
| atomic | 对共享位置不可分割的更新 |
| coalescing | 相邻执行单元访问相邻显存形成高效事务 |
| JIT | 运行时按 specialization 编译 kernel |
| cold/warm | 含初始化/编译/冷 I/O 与预热后的不同状态 |
| page cache | 操作系统缓存文件内容的内存 |
| IOPS | 每秒 I/O 操作数，小文件场景很重要 |
| throughput | 单位时间处理帧数或字节数 |
| latency | 一个任务从开始到完成的时间 |
| fingerprint | 判断旧计数是否属于当前输入/目标的摘要 |
| ledger | 规范化、可恢复的整数计数账本 |
| part | 一个已原子提交的账本分片 |
| checksum | 检测 part 是否改变/损坏的 SHA-256 |
| atomic replace | 正式路径从旧完整文件瞬间切到新完整文件 |
| resume | 从最后连续、已验证 part 后继续 |
| stale lock | 进程异常结束后遗留的锁 |
| aggregate ratio | 所有 whole 总和除以所有 reference 总和 |
| mean frame ratio | 有定义的单帧 ratio 的算术平均 |
| anomaly | reference_missing 或 ratio_over_one 结果行 |
| Amdahl 定律 | 优化非主要阶段时整体提升受限 |
| arithmetic intensity | 每字节数据对应的计算量 |
| memory-bound | 速度主要受数据搬运/带宽限制 |
| compute-bound | 速度主要受计算吞吐限制 |
| AVX-512 | CPU 宽向量指令集，不是当前已实现后端 |
| io_uring | Linux 异步 I/O 接口，不是当前已实现读取器 |
| CUDA Graph | 固定 GPU 操作图 replay，不是当前已实现功能 |
| GDS | GPUDirect Storage，不是有 GPU 就自动可用 |

## 2. 形状公式

```text
P = H×W

LoadedBatch.data
= [B,2,H,W]

BatchCounts.counts
= [B,2,5]

Triton tiles
T = ceil(P / block_pixels)

Triton partial
= [B,T,2,5]
```

## 3. 像素与内存公式

```text
每帧对 payload
= 2×H×W×dtype_bytes

单 batch payload
= B×2×H×W×dtype_bytes

队列 payload 上限
= ring_slots×batch_payload
```

实际峰值还要加 producer、consumer、单帧 futures、pinned、device 和临时量。

720p uint16：

```text
P = 921,600
每单图 = 1.758 MiB
每帧对 = 3.516 MiB
B=128 = 450 MiB
```

## 4. ratio 公式

单帧单 target：

```text
r(f,t)=W(f,t)/R(f,t)
```

group：

```text
r_group(f)=Σ_t W(f,t)/Σ_t R(f,t)
```

dataset aggregate：

```text
R_aggregate(t)=Σ_f W(f,t)/Σ_f R(f,t)
```

frame mean：

```text
R_mean(t)=mean({W(f,t)/R(f,t) | R(f,t)>0})
```

aggregate、group 都是“先加整数，再除”，不是 ratio 简单平均。

## 5. status 速查

| 条件 | ratio | status |
|---|---|---|
| reference=0 | null/CSV空 | `reference_missing` |
| reference>0 且 whole/reference>1 | 保留真实值 | `ratio_over_one` |
| 其他 | 正常值 | `valid` |

## 6. backend 速查

| backend | 主要算法 | 当前优势 | 当前局限 |
|---|---|---|---|
| NumPy | 两来源各一次 bincount | 清晰、CPU reference | 非 AVX-512 专用内核 |
| Torch | 五次 compare + count_nonzero | 易读 GPU baseline | 多扫描和大临时量 |
| Triton | tile 融合五比较 + 二次归约 | 少显存流量、小 partial | JIT、仍有 host/pin/同步成本 |

auto：

```text
Triton available → Torch CUDA available → NumPy
```

不是实测自动调优。

## 7. 当前实现/未实现检查

### 已实现

- strict pairing；
- 全帧 shape/dtype 校验；
- mapping/五 ID 严格解析；
- reader 线程池；
- 有界 Queue 背压；
- NumPy/Torch/Triton；
- GPU NumPy抽样；
- part checksum/resume；
- lock；
- 原子 CSV/JSON/NPZ；
- deterministic reporting。

### 未实现

- 固定 pinned ring；
- 跨 batch multi-stream；
- CUDA Graph；
- io_uring；
- packed cache；
- AVX-512；
- GDS；
- benchmark autotuner；
- CPU/GPU work stealing。

## 8. 已完成的远端 GPU 验证

当前 RTX 4090 环境已验证：

- [x] 本地/旧远端 32 个共有执行文件 SHA-256 一致；
- [x] v02 项目 venv 可导入 NumPy/Torch/Triton；
- [x] Torch 与 Triton 三帧全量 NumPy复核；
- [x] `auto` 实际选择 Triton；
- [x] 1026 帧三后端 cache 与历史 NumPy cache 一致；
- [x] 三轮轮换顺序性能基准；
- [x] reader/pin/H2D/kernel 阶段计时；
- [x] GPU 测试前后无其他 compute process。

证据和边界见 [第 19 章](19_remote_gpu_validation.md)。换软件版本后，这些勾选不能自动继承，必须重跑。

## 9. 新数据运行前检查清单

- [ ] 两个目录属于同一次可比较采集；
- [ ] 文件命名为 `semantic_id_<frame_id>.npy`；
- [ ] 两边 frame ID 集合相同；
- [ ] 抽查相机/姿态/时间对齐；
- [ ] mapping 来自同一数据集；
- [ ] 五个 label 字符串精确存在；
- [ ] mapping dtype 与数组一致；
- [ ] output 是专用目录；
- [ ] output 与输入目录不相等、不互相包含；
- [ ] 磁盘空间足够；
- [ ] 小样本 NumPy 手算通过；
- [ ] GPU 环境小样本全量 cross-check；
- [ ] 记录配置、版本和 commit。

## 10. 性能实验检查清单

- [ ] 每组独立新 output；
- [ ] 不用 resume 时间比较；
- [ ] counts_cache 整数一致；
- [ ] 明确 cold/warm；
- [ ] GPU 明确 cold JIT/warm；
- [ ] 同一机器负载；
- [ ] 多次重复并报告中位数；
- [ ] 记录最大 RSS/VRAM；
- [ ] 记录磁盘吞吐/IOPS；
- [ ] 分阶段计时；
- [ ] 一次只改变有限因素；
- [ ] 端到端结论不只基于 kernel。

## 11. 失败恢复检查清单

- [ ] 先看 `manifest.json`；
- [ ] 再看 `counts_manifest.json`；
- [ ] 不手改 fingerprint/checksum；
- [ ] part 缺失或 hash 错时停止；
- [ ] stale lock 先核对 hostname/PID；
- [ ] 确认无活跃 writer 才删精确锁；
- [ ] 相同输入/目标使用 resume；
- [ ] 新输入/目标使用新 output；
- [ ] overwrite 前再次核对完整路径；
- [ ] 报告失败而 counts 完整时优先 resume 重生报告。

## 12. 代码评审检查清单

- [ ] 输入/输出 shape 是否明确？
- [ ] dtype 与溢出边界是否明确？
- [ ] batch 最后一批是否正确？
- [ ] target ID=0 是否正确？
- [ ] frame/target/source 顺序是否保持？
- [ ] 异步 buffer 生命周期是否覆盖完成 event？
- [ ] 是否出现共享无锁写？
- [ ] ledger 是否仍只提交连续 ordinal？
- [ ] 异常是否能传播到主线程？
- [ ] part/manifest 提交顺序是否安全？
- [ ] fingerprint/version 是否应变化？
- [ ] NumPy cross-backend 测试是否新增？
- [ ] 性能收益是否由端到端证据支持？

## 13. 真正掌握的最终标准

你应该能够在不看教程的情况下说明：

1. 为什么这个项目需要两套图与严格 pairing；
2. group/aggregate/mean 三种 ratio 的差别；
3. `[B,2,H,W] → [B,2,5]` 每一维是什么；
4. reader 线程池、producer、Queue 和 counter/GPU 如何协作；
5. NumPy histogram、Torch 五扫描、Triton 两阶段的差别；
6. pinned、H2D、stream、event、JIT、reduction 分别解决什么；
7. 为什么 GPU kernel 快不等于项目快；
8. part、manifest、checksum、lock 怎样支持恢复；
9. 为什么并行完成顺序不改变报告；
10. 下一项优化应怎样通过测量选择，而不是凭技术名词选择。

当你能把这些内容讲给另一位初学者，并能用 demo 和测试证明时，就已经完整掌握了这个项目的架构、代码、算法与核心思想。
