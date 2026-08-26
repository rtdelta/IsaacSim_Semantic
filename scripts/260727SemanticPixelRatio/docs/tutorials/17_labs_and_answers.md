# 17｜分级实验与参考答案

这些实验按“能运行 → 能解释 → 能修改 → 能优化”排序。先独立完成，再看每节末尾参考答案。

## 实验 1：手算一帧

输入：

```text
whole:
1 1 2
3 4 5

reference:
1 2 2
2 5 0
```

目标 IDs `1...5`。

任务：

1. 写出 `[2,5]` counts；
2. 写出五个 ratio/status；
3. 写出 group count/ratio。

### 参考答案

```text
whole     [2,1,1,1,1]
reference [1,3,0,0,1]
```

```text
ID1 2.0 ratio_over_one
ID2 1/3 valid
ID3 null reference_missing
ID4 null reference_missing
ID5 1.0 valid
group 6/5=1.2 ratio_over_one
```

## 实验 2：运行 demo 并审计

```powershell
python docs/tutorials/make_tiny_demo.py
python run_compare.py --config docs/tutorials/_demo/config.json
```

任务：

1. 预测 frames 和 target_rows；
2. 找出全部 anomaly；
3. 手算 frame `0000` group；
4. 解释为什么有两个 part。

### 参考答案

- 3 帧，`3×6=18` rows；
- anomaly 由 `reference_missing` 或 `ratio_over_one` 决定，以实际 CSV 为准逐项手算；
- frame 0000 group 为 `6/6=1`；
- `batch_frames=2`，所以 parts 分别包含 2 帧和 1 帧。

## 实验 3：证明 resume 没有重计数

运行 demo 两次，记录第二次输出和 `counts_manifest.json`。

任务：

1. 第二次 `completed_frames` 是否改变？
2. parts 数是否增加？
3. 为什么仍重写报告？
4. 第二次时间能否用于 backend 性能？

### 参考答案

- completed 仍为 3；
- parts 仍为 2；
- remaining pairs 为空，但 pipeline 会 `load_all → write_reports`；
- 不能，第二次没有扫描 semantic payload。

## 实验 4：制造 strict pairing 错误

复制 demo，在 reference 中把：

```text
semantic_id_0002.npy
```

临时改名为其他名称，然后使用新 output 或删掉 demo 重建后运行。

任务：

1. 预测在哪个函数失败；
2. 是否已创建计数 part；
3. 为什么不能简单用 zip 跳过？

### 参考答案

- `discover_frame_pairs` 在 pipeline 加锁/批读前失败；
- 不应产生新计数 part；
- zip 可能把后续不同 frame ID 配到一起，得到静默错误。

## 实验 5：制造 dtype mismatch

把一个 reference frame 另存为 `int32`，shape 不变。

任务：

1. 若改的是第一帧，何时发现？
2. 若改的是后续帧，何时发现？
3. 已提交的前批是否保留？

### 参考答案

- 第一帧在 `inspect_dataset_contract` 发现 whole/reference dtype 不同；
- 后续帧在 reader 的 `load_pair_arrays` 发现；
- 后端/验证前已完整提交的 part 保留，当前错误 batch 不提交。

## 实验 6：验证 group 不是 ratio 平均

构造两个 target：

```text
whole     [10,1]
reference [100,1]
```

任务：

1. 简单 ratio 平均；
2. group ratio；
3. 说明哪个符合项目定义。

### 参考答案

```text
mean ratios = 0.55
group ratio = 11/101 ≈ 0.10891
```

项目使用后者，因为先合并像素计数再相除。

## 实验 7：观察背压

目标：理解 Queue 不是越大越好。

建议做一个临时实验分支，在 backend `count_batch` 开头仅用于实验加入短暂停顿，或用 debugger 单步；不要把 sleep 提交到正式代码。

分别使用：

```text
ring_slots=2
ring_slots=4
```

任务：

1. 预测后端很慢时 queue 状态；
2. 预测内存变化；
3. slots 从 2 到 4 是否使后端本身更快？

### 参考答案

- queue 很快满，producer 在 put 等待；
- 允许多保留两个 LoadedBatch，内存增加约 `2×M_batch`；
- 不会。最多减少读取抖动导致的饥饿；后端计算速度不变。

## 实验 8：估算内存

条件：

```text
B=64
H=720
W=1280
dtype=uint16
ring_slots=3
```

任务：

1. 单 batch payload；
2. 队列 payload 上限；
3. 列出至少四项额外内存。

### 参考答案

```text
单 batch = 225 MiB
队列最多 = 675 MiB
```

额外项：producer batch、consumer batch、future 单帧 arrays、pinned copy、device input、GPU temp、Python对象、page cache。

## 实验 9：比较 aggregate 与 mean

两帧：

```text
900/1000
1/10
```

再增加第三帧：

```text
10/0
```

任务：

1. 前两帧的 mean 和 aggregate；
2. 加第三帧后 mean 是否改变；
3. aggregate 是否改变，为什么？

### 参考答案

前两帧：

```text
mean = 0.5
aggregate = 901/1010
```

第三帧 ratio 无定义，不进入 mean，所以 mean 仍 0.5；但 whole total 加 10，aggregate 变为 `911/1010`。

## 实验 10：阅读 Triton 地址

条件：

```text
P=8
B=2
frame_index=1
tile offsets=[2,3]
```

任务：给出 frame 1 whole/reference 两个 offset 的线性索引。

### 参考答案

```text
frame_stride=16
source_stride=8

whole:     16+[2,3]   = [18,19]
reference: 16+8+[2,3] = [26,27]
```

## 实验 11：设计 target ID=0 的 kernel 测试

任务：

1. 让 P 不是 block size 整数倍；
2. target 包含 0；
3. 图像有效区域中也有若干 0；
4. 说明若去掉 `& mask` 会怎样。

### 参考答案

最后 tile 越界 lane 的 `other=0` 会与 target 0 相等。若不与 mask，padding 被当成真实 0，计数虚增。该测试能直接发现尾 tile mask bug。

## 实验 12：判断优化优先级

测得：

```text
read 430 ms/batch
pin 40 ms
H2D 25 ms
kernel 18 ms
D2H 1 ms
```

候选：

```text
A. kernel 快一倍
B. 预分配 pinned ring，省掉 35 ms pin
C. packed cache，让 read 降到 150 ms
```

任务：按单项理论端到端收益排序。

### 参考答案

若阶段近似串行：

```text
原总计 514 ms
A 节省 9 ms
B 节省约 35 ms
C 节省 280 ms
```

优先 C、B、A。若流水可重叠，需用时间线重新计算临界路径，但 read 仍明显最大。

## 实验 13：设计跨后端一致性测试

任务：列出最少六个数据边界。

### 参考答案示例

1. target ID=0；
2. target 完全不存在；
3. target 占满整图；
4. P 不是 Triton block 整数倍；
5. B 的最后一批不足；
6. 多帧分布不同；
7. 五 ID 都出现；
8. uint16 高 ID；
9. ratio 无分母；
10. group 接近整帧。

对 NumPy/Torch/Triton 的 `[B,2,5]` 做逐整数 equality。

## 实验 14：设计 crash recovery 测试

任务：为以下中断点写出预期：

```text
part temp 写到一半
part replace 后 manifest 前
manifest 更新后
全部 counts 完成但 summary 写前
```

### 参考答案

- temp 半写：manifest 不含本批，下次重算；
- orphan 正式 part：manifest 不含本批，下次同名 replace；
- manifest 已更新：本批完成，从下一 ordinal 继续；
- counts 完整：remaining 为空，重生报告。

## 实验 15：扩展到可变 K 的设计评审

不要立即改代码。先写影响清单：

```text
配置/schema
models
三后端
Triton compile-time loop/layout
ledger
reporter
fingerprint/version
tests
兼容旧账本
```

### 参考答案

这是跨层格式变更，不是单函数修改。需要决定旧 `[N,5]` part 是否继续兼容，以及 group 定义和报告列如何迁移。最安全通常是新 schema/pipeline version 和新 output。

## 毕业项目

完成一个不改结果语义的阶段 timing 实现：

1. 为 discovery、reader wait、backend、verify、ledger、report 分别计时；
2. 每 batch 只记录小型统计，不打印；
3. completed 后写 `timings.json`；
4. 不让 timing 字段进入 counts fingerprint；
5. 用现有测试证明 counts/report 数据字段不变；
6. 用 demo 验证 timings 各项非负、总关系合理；
7. 写一页分析指出真实最大瓶颈。

完成它后，你已经从“看懂项目”进入“能用证据改进项目”的阶段。

