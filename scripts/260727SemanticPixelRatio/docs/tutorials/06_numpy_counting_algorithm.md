# 06｜NumPy CPU 计数算法

对应源码：[numpy_backend.py](../../semantic_pixel_ratio/backends/numpy_backend.py)

NumPy 后端有双重角色：

1. 没有 GPU 时的正式计数后端；
2. Torch/Triton 结果的精确整数 reference。

因此它首先追求清晰、稳定、可验证，然后才是 CPU 性能。

## 1. 最朴素的错误起点

如果用 Python 双重循环逐像素：

```python
for row in image:
    for semantic_id in row:
        if semantic_id == target_1:
            count_1 += 1
        ...
```

算法复杂度虽然也是 `O(P)`，但每个像素都执行 Python 解释器循环，速度很差。

关键经验：

> 复杂度相同不代表实际速度相同。Python 循环与连续原生机器码循环的常数差别可能巨大。

## 2. 五张布尔 mask 的向量化方法

容易想到：

```python
count_1 = np.count_nonzero(image == id_1)
...
count_5 = np.count_nonzero(image == id_5)
```

它已经比 Python 循环好，因为比较和计数由 NumPy 原生代码完成。

但图像被扫描五次：

```text
内存读取量约为 5 × image payload
```

每次 `image == id` 还会产生完整 bool 临时数组。对于内存带宽型任务，这些临时内存流量很重要。

另一种广播：

```python
image[..., None] == target_ids
```

会一次得到 `[H,W,5]` bool 数组。代码短，但临时数组元素数变成原图的五倍。

## 3. 当前 NumPy 方法：直方图

核心代码等价于：

```python
histogram = np.bincount(image.reshape(-1))
count = histogram[target_id]
```

`bincount` 扫描图像一次，构造：

```text
histogram[v] = 图像中值 v 出现的次数
```

然后五个目标只需做五次数组索引。

对于两个来源，流程：

```text
whole     → 1 个 histogram → 取 5 个 bin
reference → 1 个 histogram → 取 5 个 bin
```

所以每帧主扫描次数是两个来源各一次，而不是各五次。

## 4. 小例子

```text
image = [1,1,2,5,5,5]
```

`bincount`：

```text
index:      0 1 2 3 4 5
histogram:  0 2 1 0 0 3
```

取 target IDs `(1,2,3,4,5)`：

```text
[2,1,0,0,3]
```

若 target ID 大于当前 histogram 长度，源码返回 0，而不是越界：

```python
histogram[id] if id < histogram.size else 0
```

## 5. 输入与输出形状

单帧 worker 输入：

```text
frame_data.shape = [2,H,W]
target_ids.shape = [5]
```

单帧输出：

```text
output.shape = [2,5]
output.dtype = uint32
```

batch 主函数：

```text
B 个 [2,5] stack → [B,2,5]
```

该形状正是所有后端的统一接口。

## 6. 时间复杂度与空间复杂度

设每帧每来源 P 个像素，最大 ID 为 M：

```text
时间：O(2P + 2M + 10 个索引)
空间：histogram 大小 O(M)
```

`np.bincount` 的 histogram 长度由最大像素值决定，而不是唯一类别数量。

对于 `uint16`：

```text
M ≤ 65535
int64 histogram 最大约 65536 × 8 bytes = 512 KiB
```

通常可接受。

若未来允许 `uint32` 且出现极稀疏的大 ID，例如 10 亿，`bincount` 会尝试分配极大的 histogram。这时应改用：

- 对五个 target 的融合比较；
- 排序/unique；
- 哈希计数；
- 针对小 K 的原生 SIMD 内核。

所以算法选择依赖 ID 值域，不只依赖标签数量。

## 7. 非负值隐含前提

`np.bincount` 要求输入是非负整数。mapping 验证 target ID 非负，但 `load_pair_arrays` 只检查数组是整数 dtype，没有逐元素验证像素值非负。

正式 `uint16` 天然非负，所以没有问题。若改成有符号 dtype 并包含负像素，NumPy 后端会抛错。

扩展支持 signed dtype 时，应在数据契约层明确：

```text
semantic pixel ID 必须 >= 0
```

或采用能忽略/处理负值的算法。

## 8. 为什么不用共享 atomic

当前一帧完全归一个 worker：

```text
worker 0 → frame 0 的私有 [2,5]
worker 1 → frame 1 的私有 [2,5]
```

没有两个线程更新同一个计数数组，因此：

- 不需要 mutex；
- 不需要 atomic increment；
- 不存在数据竞争；
- 完成顺序不影响结果。

主线程只在 future 完成后读取返回值。

## 9. `uint32` 输出为何安全

单目标计数不可能超过：

```text
P = H×W
```

当前 720p 只有 921,600。`uint32` 上限约 42.9 亿。

五个互异 semantic ID 的 group count 也不应超过 P。pipeline 同时检查：

```text
任一 target count <= P
五 target sum <= P
```

报告跨帧求和时再转 `uint64` 或 Python `int`。

## 10. 线程池的粒度

任务粒度是“一帧”，而不是：

- 一个像素；
- 一个 target；
- 整个数据集。

若任务太细，future 调度开销占比过大；若太粗，不能利用多个 core。

一帧 720p 的两次 `bincount` 通常足以摊薄一次 future 的开销，同时让 B 帧可分给多个 worker。

当 `batch_frames < cpu_workers` 时，一批能同时工作的 worker 不会超过帧数。若 B 太小，CPU 利用率可能不足。

## 11. `bincount` 与内存带宽

像素计数几乎没有复杂算术。每个像素主要是：

1. 从输入内存读取一个 ID；
2. 更新 histogram 某个位置。

这类任务常受内存系统限制，而不是浮点计算能力限制。增加 core 到某个点后，内存带宽或 cache contention 饱和，更多线程不会继续线性加速。

这也是为什么需要测 `cpu_workers=1,2,4,8,16...`，而不是直接使用所有逻辑核心。

## 12. 正确性 reference 的边界

GPU 抽样验证调用同一个 `_count_frame`：

```text
expected = NumPy histogram
actual   = GPU count
np.array_equal(expected, actual)
```

它验证的是整数完全相等，而不是近似浮点误差。

但 reference 与被测实现仍共享若干上游前提：

- 使用同一 LoadedBatch；
- 使用同一 target IDs；
- mapping 若错，两者会一起算错；
- 配对若错，两者也会一起算错。

因此 GPU 抽样验证只证明“GPU 计数算法与 NumPy 对同一输入一致”，不能替代输入语义验证。

## 13. 可替代 CPU 算法

### 五次 `count_nonzero`

优点：简单，不依赖 ID 值域。  
缺点：多次扫描和 bool 临时量。

### `bincount`

优点：一次扫描得到全部 ID 直方图。  
缺点：内存与最大 ID 相关，随机 histogram 更新可能影响 cache。

### 原生融合五比较

```text
load vector → compare id1...id5 → local counters → thread reduce
```

优点：只扫描需要的五个 ID，内存固定，适合 AVX-512。  
缺点：需 C++/编译/CPU 特性分发和严谨测试。

当前 NumPy 方案是很合理的正确性基线，但不是规划中的 AVX-512 极速后端。

## 14. 本章自检

1. `bincount` 为什么比五次 `count_nonzero` 少扫描？
2. `bincount` 的内存为何与最大 ID 而非类别数有关？
3. 为什么每个线程返回私有 `[2,5]` 能避免锁？
4. GPU 与 NumPy 完全相等能证明 mapping 选对了吗？
5. 增加 `cpu_workers` 为什么可能不再加速？

