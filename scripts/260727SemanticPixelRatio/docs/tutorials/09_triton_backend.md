# 09｜Triton 两阶段融合计数 Kernel

对应源码：[triton_backend.py](../../semantic_pixel_ratio/backends/triton_backend.py)

Triton 是用 Python 风格代码描述 GPU kernel 的语言与编译器。`@triton.jit` 函数不是普通 Python 数组函数：它会被 JIT 编译成 GPU 代码。

## 1. 为什么需要自定义 kernel

Torch 表达式易读，但五个 target 各自创建比较与归约。Triton 目标是：

```text
每个 whole pixel 读一次
每个 reference pixel 读一次
在寄存器中同时与五个 ID 比较
只写小型 partial counts
```

它优化的主要是显存读取、临时张量和 launch 组织，而不是改变数学结果。

## 2. 两阶段总览

输入：

```text
data       [B,2,H,W]
target_ids [5]
```

第一阶段：

```text
_count_partials_kernel
grid = [B,T]
输出 partial [B,T,2,5]
```

第二阶段：

```text
_reduce_partials_kernel
grid = [B×2×5]
输出 counts [B,2,5]
```

其中：

```text
P = H×W
T = ceil(P / block_pixels)
block_pixels 默认 16384
```

## 3. 为什么是二维 grid

第一维：

```python
frame_index = tl.program_id(0)
```

选择 batch 中哪一帧。

第二维：

```python
tile_index = tl.program_id(1)
```

选择这帧连续像素中的哪一段。

所以一个 program instance 负责：

```text
一帧 × 一个连续 tile × 两个来源 × 五个 target
```

同一帧由多个 tile 并行处理，不会因为“一帧只给一个 block”而并行度不足。

## 4. 线性内存布局

`LoadedBatch.data` 是 C-contiguous `[B,2,H,W]`。把 `H,W` 展平成 P：

```text
frame 0:
  whole     P 个元素
  reference P 个元素
frame 1:
  whole     P 个元素
  reference P 个元素
...
```

因此：

```python
source_stride = P
frame_stride = 2*P
```

地址公式：

```text
whole(frame,offset)
= base + frame×2P + offset

reference(frame,offset)
= base + frame×2P + P + offset
```

这是 reader 把单帧文件复制进统一连续 batch 的一个核心收益。

## 5. tile offsets 与边界 mask

```python
offsets = tile_index * block_pixels + tl.arange(0, block_pixels)
mask = offsets < pixels_per_frame
```

最后一个 tile 通常不足 `block_pixels`，mask 使越界位置不读不计。

load 使用：

```python
tl.load(..., mask=mask, other=0)
```

越界 lane 得到 0。

比较时仍写：

```python
(whole == semantic_id) & mask
```

为什么已经 `other=0` 还必须与 mask？因为 semantic ID 0 可能是合法 target。若不与 mask，最后 tile 的填充 0 会被误计数。

当前五个 target 是齿部非零 ID，但 kernel 的边界逻辑仍应保持普适正确。

## 6. 五目标融合

```python
for target_index in tl.static_range(0, target_count):
```

`target_count=5` 是 compile-time constant。`tl.static_range` 允许编译器展开循环，近似生成五份比较/归约指令，而不是运行时 Python 循环或五次独立 kernel launch。

每个 target：

```text
whole == semantic_id
reference == semantic_id
tl.sum(...)
```

whole/reference 像素值已经加载到当前 program 的局部张量中，五次比较复用这些值。

## 7. partial 的布局

逻辑形状：

```text
[frame, tile, source, target]
```

扁平地址：

```text
((((frame×T)+tile)×2 + source)×5 + target)
```

源码先算：

```python
partial_base = (frame*T + tile) * 2 * 5
```

然后：

```text
whole target k     → partial_base + k
reference target k → partial_base + 5 + k
```

每个 `(frame,tile)` program 只写自己的十个位置，不与其他 program 冲突，所以不需要 atomic。

## 8. 第二阶段归约

输出一共：

```text
B×2×5
```

个标量。第二 kernel 启动相同数量的 program，每个 program 负责一个：

```text
(frame, source, target)
```

从线性 `output_index` 反解：

```python
frame = output_index // 10
remainder = output_index % 10
source = remainder // 5
target = remainder % 5
```

然后读取该 frame/source/target 在所有 T 个 tile 的 partial 并求和。

## 9. 为什么 reduce_block 取 2 的幂

```python
reduce_block = _next_power_of_two(tiles)
```

Triton 的 `tl.arange(0, reduce_block)` 要求适合编译和归约的静态块大小，2 的幂方便树形归约。

多出来的位置：

```text
mask = tile_offsets < tiles_per_frame
other = 0
```

不会影响总和。

## 10. 720p 实例

```text
P = 720×1280 = 921,600
block_pixels = 16,384
T = ceil(921,600 / 16,384) = 57
reduce_block = 64
```

若 B=128：

第一 kernel grid：

```text
[128,57] = 7,296 个 program
```

partial 大小：

```text
128×57×2×5×4 bytes
= 291,840 bytes
≈ 0.278 MiB
```

最终 output：

```text
128×2×5×4 = 5,120 bytes
```

与 450 MiB 输入相比，中间计数非常小。

## 11. `num_warps`

第一 kernel：

```text
num_warps=8
```

一个 program 使用更多 warp 协作处理 16384 元素和归约。

第二 kernel：

```text
num_warps=1
```

每个 program 只归约约 57 个 partial，工作量很小。

这些是性能参数，不改变数学结果。最优值依赖 GPU、Triton 版本、block size 和寄存器压力，应通过 benchmark/autotune 确认。

## 12. 为什么 block_pixels 必须是正 2 次幂

构造函数检查：

```text
>0 且 value & (value-1) == 0
```

`tl.arange(0, block_pixels)` 和归约通常要求编译期大小满足 Triton 的约束；2 的幂也利于规则并行归约。

## 13. 整数范围

输入值 load 后转 `tl.int32`，target IDs 也是 int32。

partial 单 tile 最大：

```text
16,384
```

一帧 output 最大：

```text
H×W = 921,600
```

都远小于 int32 上限。回 CPU 后先转 int64，再转统一 NumPy uint32。

若未来允许单帧超过约 21 亿像素，当前 int32 output 会有溢出风险；现实 720p/4K 不接近该边界，但接口设计时应知道假设。

## 14. host/device 路径

Triton 后端复用与 Torch 相同的准备：

```text
NumPy → torch.from_numpy view
→ 若需要，pin_memory copy
→ non_blocking H2D
→ 分配 partial/output
→ kernel 1
→ kernel 2
→ output D2H
```

所以 Triton 只优化 GPU 计数核心，没有消除当前的：

- NPY 小文件读取；
- 单帧→batch host copy；
- pageable→pinned copy；
- 每批 device allocation；
- 默认 stream 串行；
- 本批 D2H 同步。

## 15. JIT 冷启动

第一次遇到特定 kernel specialization 时，Triton 要编译。compile-time 参数可能影响缓存键：

- block_pixels；
- tiles_per_frame；
- target_count；
- dtype/设备等。

因此第一次 batch 可能明显慢于后续 batch。性能报告应区分：

```text
cold first batch
warm repeated batches
full end-to-end
```

正式端到端运行仍会真实承担一次冷启动，但调 kernel 性能时不能把编译时间平均进少量迭代后得出误导结论。

## 16. 为什么不用 atomic

第一阶段每 program 写唯一 partial，第二阶段每 program 写唯一 output：

```text
writer ownership 唯一
```

没有写冲突，所以不需 atomic。代价是多一个 partial buffer 和第二个 kernel，但通常远好于每像素争用十个全局 counter。

## 17. 与 Torch 后端比较

| 维度 | Torch | Triton |
|---|---|---|
| 易读性 | 高 | 中 |
| 像素读取 | 逻辑上每 target 一遍 | 每来源每 tile 一次 |
| bool 临时量 | 大 | 局部比较结果 |
| kernel 控制 | 框架决定 | 项目明确设计 |
| 中间输出 | 通用 op 中间张量 | 小型 partial |
| 维护难度 | 低 | 较高 |
| 首次 JIT | PyTorch op 通常已有 | Triton specialization 编译 |

## 18. GPU 抽样复核

Triton 返回后，pipeline 对前若干帧使用 NumPy `_count_frame`，要求 `[2,5]` 完全相同。

它能发现：

- 地址 stride 写错；
- source 维度颠倒；
- target 索引错；
- 最后 tile mask 错；
- partial layout/reduction错；
- dtype 转换造成的错误。

建议修改 kernel 后用覆盖这些情况的小测试：

- P 不是 block_pixels 的整数倍；
- target ID 为 0；
- 某 target 完全不存在；
- 同一 target 占满整图；
- batch 最后一批不足 B；
- 多帧各自分布不同。

## 19. 远端真机验证

当前两个 kernel 已在 Triton 3.6.0、RTX 4090 上真实编译和运行：

- 三帧 demo 与 NumPy/Torch 逐整数一致；
- 1026 帧正式数据与历史 NumPy cache 逐整数一致；
- `auto` 实际选择 `triton_cuda`；
- 64 帧热态两个 kernel CUDA Event 中位数约 0.327 ms；
- 同一个内存 batch 的完整 `count_batch` 中位数约 42.6 ms。

`0.327 ms` 与 `42.6 ms` 的巨大差距来自 pin、H2D、device allocation、D2H 和 host 调度。1026 帧完整 pipeline 的三轮中位数约 2.837 s，略慢于当前 Torch 的 2.720 s。这不否定融合 kernel，而是说明 kernel 已经不在端到端临界路径上。

显式 Triton 的三帧首次运行约 2.44 s，而随后 `auto` 的 Triton 路径约 0.73 s，展示了 JIT/cache 冷热差异。完整记录见 [第 19 章](19_remote_gpu_validation.md)。

## 20. 本章自检

1. grid `[B,T]` 两个维度各代表什么？
2. 为什么 `other=0` 后仍要 `& mask`？
3. partial 的 `[B,T,2,5]` 每一维是什么？
4. 为什么两阶段设计不需要 atomic？
5. 720p、block 16384 时为什么是 57 tiles？
6. Triton 优化了什么，又没有优化什么？
7. 为什么 0.327 ms kernel 对应的完整 `count_batch` 仍约 42.6 ms？
