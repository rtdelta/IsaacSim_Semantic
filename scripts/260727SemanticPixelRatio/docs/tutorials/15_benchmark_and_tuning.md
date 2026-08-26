# 15｜基准测试、瓶颈定位与参数调优

优化的第一原则：

> 先保证结果相同，再测量时间；先找到最大瓶颈，再改代码。

“GPU 利用率更高”“线程更多”“kernel 更短”都不是最终目标。最终目标通常是：在正确性、资源上限和可恢复性不退化的前提下，缩短完整数据集从输入到可靠报告的时间。

## 1. 明确你测的指标

### 端到端 wall time

从启动到 completed 报告落盘的真实经过时间。它最接近用户体验。

### 吞吐

```text
frames_per_second = N / elapsed_seconds
```

还可换算输入 payload 吞吐：

```text
bytes_per_frame_pair = 2 × H × W × dtype_bytes
payload_GB/s = fps × bytes_per_frame_pair / 1e9
```

720p uint16 两来源：

```text
2×720×1280×2 = 3,686,400 bytes/frame
```

若 100 fps，纯 payload 相当于约 0.369 GB/s，不含 NPY header、metadata 与额外内存复制。

### 阶段时间

至少拆：

```text
discovery/fingerprint
NPY load
batch copy
pinning
H2D
kernel
D2H
validation
ledger append/fsync/checksum
report
```

只有一个 total 时无法判断优化哪一段。

## 2. 正式数据规模

720p、uint16、两套：

```text
单帧对 = 3,686,400 bytes ≈ 3.516 MiB
10,000 帧 = 36.864 GB ≈ 34.33 GiB
100,000 帧 = 368.64 GB ≈ 343.32 GiB
```

文件数：

```text
两目录合计 = 2N 个 .npy
```

十万帧意味着 20 万次文件打开/读 header，metadata/IOPS 可能比顺序带宽更早成为瓶颈。

## 3. 历史测量与当前远端复测

[OptimizationGaps_v01.md](../OptimizationGaps_v01.md) 记录：

```text
64 对真实帧读取约 0.435 s
Triton 热态计数约 0.019 s
```

那次读取约为“热态计数”时间的 23 倍，但原文没有完整记录当前可复现环境、计时边界和 cache 状态，因此应把它视为历史优化线索。

2026-07-29 又在当前 RTX 4090 环境对 64 帧正式数据分阶段复测：

| 阶段 | 中位数 |
|---|---:|
| warm NPY reader + batch copy | 111.4 ms |
| pageable→pinned | 10.3 ms |
| pinned H2D | 35.2 ms |
| Torch 五目标通用算子 | 13.1 ms |
| Triton 两个 kernel | 0.327 ms |

当前数据更强地说明：

```text
reader/host准备
> H2D
> pin copy
> Triton kernel
```

1026 帧热 cache 三轮中位数：

```text
NumPy  4.351 s / 235.78 fps
Torch  2.720 s / 377.27 fps
Triton 2.837 s / 361.68 fps
```

全部账本逐整数一致。Triton kernel 虽比 Torch 算子快约 40 倍，但完整 pipeline 中 Torch 略快，实证 kernel 不是唯一决定因素。完整方法和版本见 [第 19 章](19_remote_gpu_validation.md)。

## 4. 为什么要区分冷/热缓存

第一次读文件：

```text
存储设备 → page cache → 用户数组
```

第二次：

```text
page cache → 用户数组
```

第二次可能明显更快。你要明确实验问题：

- 生产任务通常只跑一次：冷缓存更相关；
- 重复分析同一数据：热缓存/packed cache 更相关；
- 比较 CPU/GPU backend：若第二个后端享受热 page cache，会不公平。

不要在不清空/控制 cache 的情况下依次跑 A、B，然后宣布 B 更快。

清理操作系统 page cache 是全机影响操作，生产服务器上需要权限与协调；更安全的方法是：

- 轮换顺序 AB/BA；
- 使用大于可用内存的数据；
- 报告冷/热两组；
- 多次重复并给中位数；
- 在独占测试机执行。

## 5. 正确性基线先冻结

性能实验前保存：

```text
counts_cache.npz 的整数 arrays
summary 数据字段（不含时间/backend）
config 和环境版本
```

每个候选运行完成后：

```text
ordinals equal
frame_ids equal
whole_counts equal
reference_counts equal
```

先比较整数，不要只比较格式化 ratio。

## 6. 公平比较后端

每个后端必须：

- 使用相同输入；
- 使用相同 target IDs；
- 使用独立的新 output root；
- 从 0 处理全部帧；
- 不把 resume 的快速报告时间当处理时间；
- 明确 cold/warm；
- GPU 区分首次 JIT；
- 尽量在相同机器负载下；
- 至少重复 3 次，报告中位数和范围。

如果只测 kernel，先将数据放在内存/device 并排除 I/O；如果测端到端，就不要只报告 kernel event。

## 7. `batch_frames` 的影响

增大 B：

优点：

- 摊薄 Python/launch/part/checksum 固定开销；
- GPU 有更多并行工作；
- CPU 线程池有更多 frame 任务；
- H2D 传输更大、更连续。

缺点：

- host 与 device 峰值线性增加；
- 首批延迟增加；
- 出错时当前未提交工作更多；
- 最后一批 shape 仍可能不同；
- 过大 batch 可能挤压 page cache 或 CUDA OOM。

单 batch 公式：

```text
M_batch = B×2×H×W×dtype_bytes
```

720p uint16：

| B | 单 batch |
|---:|---:|
| 16 | 56.25 MiB |
| 32 | 112.5 MiB |
| 64 | 225 MiB |
| 128 | 450 MiB |
| 256 | 900 MiB |

这只是一个 payload，不是总进程峰值。

## 8. `reader_threads` 的影响

候选：

```text
1,2,4,8,16,32
```

观察：

- 读 batch 时间；
- 磁盘 MB/s；
- IOPS；
- CPU system time；
- queue empty 比例；
- 上下文切换。

小文件 NVMe 可能需要一定并发才能跑满；机械盘或网络存储并发过高可能使性能恶化。

## 9. `ring_slots` 的影响

作用是吸收读取抖动：

- 太小：偶发慢读让后端饥饿；
- 适中：预取覆盖抖动；
- 太大：占用大量 RAM/page cache，收益趋零。

当前不是 buffer reuse，所以增加 slots 还增加分配和在途对象数量。常从 2、3、4 测，不应直接设几十。

## 10. `cpu_workers` 的影响

NumPy 后端候选：

```text
1,2,4,8,16,32...
```

在 CPU 利用率尚未满时也可能已达到内存带宽上限。看：

- fps 是否继续增；
- memory bandwidth；
- context switches；
- reader 是否被 counter 抢走 CPU；
- 是否存在 NUMA 跨节点流量。

服务器有 64 个物理核不等于 `cpu_workers=64` 一定最佳。

## 11. `block_pixels/num_warps` 的影响

Triton 当前默认：

```text
block_pixels=16384
num_warps=8
```

block 太小：

- tiles 增多；
- partial 增多；
- 第二归约更大；
- program 数和调度开销增。

block 太大：

- 寄存器压力增；
- 单 program 资源过多；
- occupancy 可能下降；
- 编译/硬件约束。

候选必须在热态 kernel microbenchmark 中比较，并用 NumPy 验证每个配置。最终还要确认端到端收益。

## 12. 如何判断瓶颈

| 观察 | 可能瓶颈 | 下一步 |
|---|---|---|
| Queue 经常空、GPU 低利用 | 读取/host准备 | 测 reader、packed、线程 |
| Queue 经常满、CPU NumPy 满 | CPU计数 | 调 cpu_workers/原生 SIMD |
| Queue 满、GPU kernel 长 | GPU核心 | Triton profiler/tile调优 |
| pin_memory 时间大 | host复制 | 固定 pinned ring |
| H2D 时间大 | PCIe/批布局 | pinned、连续批、重叠 |
| kernel 短但有空洞 | launch/同步 | streams/events/graph |
| part append 抖动大 | fsync/checksum/输出盘 | 分离输出盘、part粒度 |
| 第二次快很多 | page cache/小文件 | packed cache/明确冷热 |

## 13. 监控工具层次

### 粗粒度

- `time` / PowerShell `Measure-Command`；
- Task Manager / `top` / `htop`；
- `iostat`；
- `nvidia-smi`；
- 输出盘空间。

### Python

- `time.perf_counter` 分阶段；
- `cProfile` 看 Python 调度；
- 自定义 batch timing 与 queue occupancy；
- `tracemalloc` 只看 Python 分配，不等于 NumPy/GPU 总内存。

### GPU

- PyTorch profiler；
- CUDA Events；
- NVIDIA Nsight Systems 看 CPU/I/O/CUDA 时间线；
- Nsight Compute 看单 kernel memory throughput、occupancy、warp 行为。

先用时间线工具确定空洞，再用 kernel 工具深挖。不要在 I/O 瓶颈时先研究某条 GPU 指令。

## 14. 建议实验矩阵

不要一次全组合爆炸。分阶段：

### A. reader-only

固定一个不会计数或用足够快消费的测量工具，扫描：

```text
reader_threads × batch_frames
```

### B. backend-only

把固定 synthetic/内存 batch 重复计数：

```text
backend × B
```

GPU 预热后测。

### C. end-to-end

先选 A/B 的少数最佳候选：

```text
backend × reader_threads × B × ring_slots
```

每组独立 output，多次重复。

### D. 稳定性

长时间运行，观察：

- RSS/显存是否随 N 增长；
- 文件描述符是否泄漏；
- 吞吐是否退化；
- resume 是否正确。

## 15. 结果记录模板

| run | backend | B | readers | slots | cpu_workers | cache | frames | wall s | fps | max RSS | max VRAM | counts equal |
|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---|
| A1 | numpy | 64 | 8 | 3 | 16 | cold | ... | ... | ... | ... | - | yes |
| B1 | triton | 128 | 8 | 3 | - | cold | ... | ... | ... | ... | ... | yes |

另存：

- 软件/驱动版本；
- GPU/CPU/存储型号；
- config；
- Git commit；
- 是否其他任务占用设备。

## 16. 常见错误结论

### “GPU kernel 快 10 倍，所以项目快 10 倍”

忽略 I/O、pin、H2D、同步和报告。

### “CPU 利用率没 100%，所以加线程”

可能已经磁盘或内存带宽饱和。

### “nvidia-smi 利用率低，所以 kernel 写坏了”

可能 GPU 在等文件。

### “第二次运行 100 倍更快”

可能只是 resume 没有计数，或 page cache 热了。

### “batch 越大越快”

存在饱和点、OOM 和 host 峰值。

### “auto 就是自动调优”

当前只是能力优先级。

## 17. 本章自检

1. 100 fps 对 720p 双 uint16 payload 约多少 GB/s？
2. 为什么要用新 output 比较性能？
3. cold cache 与 warm cache 分别回答什么问题？
4. 增大 batch 的收益和代价是什么？
5. 读取比 kernel 慢 23 倍时，优化优先级应怎样？
6. 为什么 Nsight Compute 通常不是第一步？
