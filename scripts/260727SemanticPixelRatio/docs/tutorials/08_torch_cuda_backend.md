# 08｜Torch CUDA 后端逐步拆解

对应源码：[torch_backend.py](../../semantic_pixel_ratio/backends/torch_backend.py)

Torch 后端是容易理解的 GPU 基准实现。它使用 PyTorch 张量操作，不写自定义 kernel。

## 1. 可用性检查

```python
def torch_cuda_available(device="cuda"):
    import torch
    return device.startswith("cuda") and torch.cuda.is_available()
```

需要同时满足：

- PyTorch 可导入；
- 设备字符串以 `cuda` 开头；
- PyTorch 检测到可用 CUDA 设备。

指定 `backend="torch_cuda"` 但不可用时会报错。`backend="auto"` 时会继续降级到 NumPy。

## 2. 初始化阶段

五个 target IDs 一次复制到 GPU：

```python
self._target_ids = torch.tensor(
    target_ids,
    dtype=torch.int32,
    device=self._device,
)
```

这是小型、整个运行都不变的数据，没必要每 batch 重传。

## 3. NumPy 到 Torch 的 host view

```python
host = torch.from_numpy(batch.data)
```

`from_numpy` 通常与 NumPy 数组共享 CPU 内存，不立刻复制 payload。两者生命周期相关，修改一方可能影响另一方。

当前 pipeline 在 `count_batch` 返回前一直持有 `LoadedBatch`，因此共享内存不会提前消失。

## 4. pinning

```python
if not host.is_pinned():
    host = host.pin_memory()
```

reader 创建的是普通 `np.empty`，所以通常不 pinned。`.pin_memory()` 会创建 pinned host 张量并复制整个 batch。

对 `B=128`、720p、uint16，这一步涉及约 450 MiB host copy。它是当前 GPU 路径的重要成本。

理想版本应让 reader 直接填充预分配 pinned buffer，省掉 pageable→pinned 临时复制。

## 5. H2D

```python
device_data = host.to(self._device, non_blocking=True)
```

输入形状保持：

```text
[B,2,H,W]
```

当 host pinned 时，copy 可以异步提交。但当前使用默认 stream，且本批最终要把结果取回 CPU，所以函数返回前仍会等待相关工作完成。

## 6. 五目标计数

核心：

```python
per_target = [
    torch.count_nonzero(
        device_data == target_ids[index],
        dim=(-2, -1),
    )
    for index in range(5)
]
```

以一个 target 为例：

```text
device_data == id
```

产生逻辑形状：

```text
[B,2,H,W] bool
```

沿最后两个维度计数：

```text
count_nonzero(..., dim=(-2,-1))
→ [B,2]
```

五个 target 得五个 `[B,2]`，再：

```python
torch.stack(per_target, dim=-1)
```

得到：

```text
[B,2,5]
```

## 7. Torch 实现的性能特征

优点：

- 代码简洁；
- 结果语义清楚；
- 易作为 GPU baseline；
- PyTorch 负责设备和 kernel 调度；
- 不依赖手写地址公式。

代价：

- 每个 target 都做一次全张量相等比较；
- 输入数据逻辑上被扫描五遍；
- 每个 target 产生大 bool 临时量；
- 多个通用 kernel 的 launch 和中间张量开销；
- 没有把“五个比较 + 计数”融合进一次自定义 kernel。

720p、B=128 时：

```text
B×2×H×W = 235,929,600 个元素
一个 bool mask 若按 1 byte/元素，约 225 MiB
```

不一定同时长期保留五张完整 mask，PyTorch allocator 和异步执行会影响实际峰值，但每个目标的巨大临时内存流量是真实问题。

## 8. D2H 与隐式同步

```python
cpu_counts = counts.to(
    device="cpu",
    dtype=torch.int64,
).numpy()
```

CPU 不能读取尚未计算完成的 GPU 结果，因此这一步会形成必要的同步点：相关比较和计数必须完成，D2H 完成后才能得到 NumPy 数组。

只回传 `[B,2,5]` 是正确设计。B=128、int64 时也只有：

```text
128×2×5×8 = 10,240 bytes
```

随后转换为统一的 `uint32`：

```python
np.asarray(cpu_counts, dtype=np.uint32)
```

## 9. 为什么中间转 int64 再 uint32

PyTorch `count_nonzero` 通常返回 64 位计数类型。D2H 时明确转 int64，随后项目接口统一为 NumPy uint32。

只要单帧像素数小于 uint32 上限，这一转换不会丢失。pipeline 还会检查 count 不超过 `H×W`。

## 10. 当前没有做什么

Torch 后端当前没有：

- `torch.compile`；
- 自定义 CUDA extension；
- 显式 CUDA streams；
- CUDA events；
- 固定 device buffer 复用；
- 跨 batch 双缓冲；
- CUDA Graph；
- 五目标融合 kernel；
- autocast/Tensor Core（整数精确计数也不需要）。

不要因为文件名含 CUDA 就自动认为所有 GPU 优化都存在。

## 11. 结果为何精确

操作只有：

```text
整数相等比较
整数 count_nonzero
整数 stack/copy
```

没有浮点加法和近似误差。GPU 抽样验证要求与 NumPy `uint32` 数组逐元素完全相等。

## 12. 可能的优化方向

从小到大：

1. 预分配并复用 pinned host buffer；
2. 复用 device input/output buffer；
3. 用 `torch.compile` 测试是否能融合部分操作；
4. 把 target IDs 广播比较与归约写成自定义 kernel；
5. 使用多个 stream 和 event 做跨批重叠；
6. 固定形状后评估 CUDA Graph。

但项目已经有 Triton 自定义融合后端，所以 Torch 更适合作为可读基线，而不是主要极限优化方向。

## 13. 如何验证 Torch 后端

在有 CUDA 的环境：

1. 用几帧已知小数组运行 NumPy；
2. 清理或使用不同输出 root；
3. 改 backend 为 `torch_cuda`；
4. 设置 `verify_sample_frames` 覆盖全部小样本；
5. 比较两个 `counts_cache.npz` 的四个数组；
6. 再比较 CSV/summary；
7. 最后才做大规模性能测试。

不要先拿正式几十 GB 数据验证一个未运行过的 GPU 环境。

## 14. 远端真机验证

当前源码已在以下环境实测：

```text
RTX 4090
PyTorch 2.11.0+cu128
CUDA runtime 12.8
```

结果：

- 三帧 demo 全部由 NumPy 逐整数复核；
- 1026 帧正式数据与历史 NumPy cache 完全一致；
- 64 帧热态 Torch 通用算子约 13.11 ms；
- 包含 pin、H2D、allocation、kernel 和 D2H 的 `count_batch` 约 55.1 ms；
- 1026 帧热 cache pipeline 三轮中位数约 2.720 s、377.27 fps。

这证明当前 Torch 代码不是只在纸面上可行。完整进程 shell wall 中位数约 5.149 s，说明 import/启动/外围报告也占可见时间。详情见 [第 19 章](19_remote_gpu_validation.md)。

## 15. 本章自检

1. `torch.from_numpy` 是否必然复制？
2. 当前 `.pin_memory()` 为什么既帮助 H2D 又增加成本？
3. 一个 target 计数后的张量形状为何是 `[B,2]`？
4. Torch 后端为何逻辑上扫描五遍？
5. 哪一步迫使 CPU 等待 GPU 结果？
6. 为什么不需要 Tensor Core 或混合精度？
7. 为什么 Torch kernel 本身的时间不能直接等同于 `count_batch`？
