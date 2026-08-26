# 14｜源码地图与推荐阅读顺序

这一章把全部源码串成一张可查的地图。第一次阅读按“输入输出契约”走，不要从 Triton 第一行开始。

## 1. 第一遍：只追主流程

推荐顺序：

1. [run_compare.py](../../run_compare.py)
2. [pipeline.py](../../semantic_pixel_ratio/pipeline.py) 的 `run`
3. [models.py](../../semantic_pixel_ratio/models.py)
4. [factory.py](../../semantic_pixel_ratio/backends/factory.py)
5. [npy_reader.py](../../semantic_pixel_ratio/io/npy_reader.py)
6. [numpy_backend.py](../../semantic_pixel_ratio/backends/numpy_backend.py)
7. [ledger.py](../../semantic_pixel_ratio/results/ledger.py)
8. [reporter.py](../../semantic_pixel_ratio/results/reporter.py)

第一遍只回答：

```text
函数收到什么？
返回什么？
数组 shape 是什么？
失败会传播到哪里？
```

## 2. 第二遍：补齐边界与可靠性

1. [config.py](../../semantic_pixel_ratio/config.py)
2. [discovery.py](../../semantic_pixel_ratio/discovery.py)
3. [semantic_io.py](../../semantic_pixel_ratio/semantic_io.py)
4. [atomic_io.py](../../semantic_pixel_ratio/results/atomic_io.py)
5. [lock.py](../../semantic_pixel_ratio/results/lock.py)
6. [tests](../../tests)

第二遍回答：

```text
哪些非法状态会被拒绝？
在哪个阶段被拒绝？
哪些状态会落盘？
崩溃后以谁为准？
```

## 3. 第三遍：GPU 与性能

1. [torch_backend.py](../../semantic_pixel_ratio/backends/torch_backend.py)
2. [triton_backend.py](../../semantic_pixel_ratio/backends/triton_backend.py)
3. [Plan_v01.md](../Plan_v01.md)
4. [OptimizationGaps_v01.md](../OptimizationGaps_v01.md)

顺序不能反过来。先知道当前实现，再读计划，才能区分现实与蓝图。

## 4. 文件职责速查

| 文件 | 核心符号 | 一句话职责 |
|---|---|---|
| `run_compare.py` | `main` | CLI、退出码、完成摘要 |
| `config.py` | `load_config` | 严格解析 JSON 并解析路径 |
| `models.py` | 多个 dataclass | 跨层数据形状契约 |
| `discovery.py` | `discover_frame_pairs` | 扫描、严格配对、排序、ordinal |
| `discovery.py` | `fingerprint_pairs` | path/size/mtime 输入指纹 |
| `semantic_io.py` | `load_semantic_mapping` | mapping 结构与唯一性 |
| `semantic_io.py` | `inspect_dataset_contract` | 第一对 shape/dtype 契约 |
| `semantic_io.py` | `load_pair_arrays` | 每帧真实加载与契约校验 |
| `backends/base.py` | `PixelCounterBackend` | 后端统一接口 |
| `backends/factory.py` | `create_backend` | auto 能力降级 |
| `numpy_backend.py` | `_count_frame` | 两次 bincount 得十个计数 |
| `numpy_backend.py` | `NumpyBackend` | frame 级 CPU 线程池 |
| `torch_backend.py` | `TorchCudaBackend` | 五次通用 GPU 比较/计数 |
| `triton_backend.py` | 两个 JIT kernel | tile partial + tile reduction |
| `npy_reader.py` | `PrefetchingNpyReader` | producer、线程读、有界队列 |
| `pipeline.py` | `run` | 生命周期、验证、提交、失败状态 |
| `ledger.py` | `CountsLedger` | part 事务、checksum、resume |
| `atomic_io.py` | atomic writers | 临时文件 + fsync + replace |
| `lock.py` | `OutputLock` | output 单 writer |
| `reporter.py` | `write_reports` | ratio、summary、CSV/JSON/cache |

## 5. 数据对象生命周期

### `FramePair`

创建：discovery。  
使用：reader、BatchCounts、ledger。  
持续：整个 run 的 pairs tuple。

### `DatasetContract`

创建：检查第一对文件。  
使用：每帧加载校验、batch 分配、count 上限。  
持续：整个 run。

### `LoadedBatch`

创建：producer `_load_batch`。  
传递：Queue → pipeline → backend → GPU verification。  
释放：append 后循环进入下一批且无队列/临时引用时。

### `BatchCounts`

创建：backend。  
使用：验证、ledger.append。  
释放：part 写完后随循环变量更新。

### `CountLedgerData`

创建：所有计数完成后 `load_all`。  
使用：报告与 cache。  
只含小型计数，不含图像。

## 6. 数组 shape 全链路

```text
单个 .npy
[H,W]

load_pair_arrays
whole [H,W], reference [H,W]

PrefetchingNpyReader
data [B,2,H,W]

任一 backend
counts [B,2,5]

ledger part
whole_counts [B,5]
reference_counts [B,5]

load_all
whole_counts [N,5]
reference_counts [N,5]

reporter
N×6 个逻辑 TargetRow
```

调试 shape 错误时沿这条链逐段打印，而不是在最终 CSV 猜。

## 7. 关键不变量归属

| 不变量 | 主要守护位置 |
|---|---|
| 配置没有未知字段 | `config._reject_unknown` |
| 恰好五标签且不重复 | `load_config` |
| label/id 唯一 | `load_semantic_mapping` |
| frame sets 相同 | `discover_frame_pairs` |
| frame 顺序确定 | `_frame_sort_key` + ordinal |
| 全数据 shape/dtype 一致 | contract + `load_pair_arrays` |
| batch shape `[B,2,H,W]` | `LoadedBatch.__post_init__` |
| count shape `[B,2,5]` | `BatchCounts.__post_init__` |
| count 不超像素 | pipeline validation |
| GPU 与 NumPy 样本一致 | `_verify_batch` |
| ledger 连续 | `CountsLedger.append/resume` |
| part 未损坏 | SHA-256 |
| frame IDs 无重复 | reporter validation |
| group 是五列之和 | reporter 重算 |
| JSON 无 NaN | `allow_nan=False` |

## 8. 测试地图

### `test_discovery.py`

验证：

- `"1","2","10"` 数值排序；
- 缺帧拒绝。

### `test_numpy_backend.py`

直接构造 `[1,2,2,3]` 等小数组，验证 `[B,2,5]`。

### `test_reporter.py`

绕过 I/O/backend，直接构造 ledger，验证：

- group sums；
- group ratio；
- ratio over one；
- zero denominator；
- aggregate ratio。

### `test_pipeline_integration.py`

临时创建 mapping、两套 `.npy`、config，运行两次：

- 第一次计数和报告；
- 第二次 resume；
- 18 行 per-frame；
- part 数量与 completed 状态。

它展示了如何把复杂系统拆成层级测试。

## 9. 一次手动 code tracing

以 demo frame `0000` 为例：

```text
discovery:
  FramePair(ordinal=0, frame_id="0000", ...)

reader:
  data[0,0] = whole 2×4
  data[0,1] = reference 2×4

NumPy:
  whole histogram → [2,1,1,1,1]
  reference histogram → [1,2,1,0,2]
  counts[0] = [[2,1,1,1,1],[1,2,1,0,2]]

ledger:
  whole_counts row 0
  reference_counts row 0

reporter:
  五行单齿
  group whole=6, reference=6
```

能在纸上追完一个 frame，才算读懂数据流。

## 10. 阅读 GPU kernel 的检查顺序

遇到自定义 kernel，按以下顺序：

1. 输入/输出 shape；
2. grid 每维含义；
3. 一个 program 负责什么；
4. 内存线性布局；
5. stride/address 公式；
6. 边界 mask；
7. 写地址是否唯一；
8. 中间 dtype 与溢出；
9. reduction 维度；
10. CPU reference 如何验证。

先验证正确性，再讨论 occupancy 和 num_warps。

## 11. 修改代码时的影响分析

### 从 5 个 target 改成可变 K

至少影响：

- config 恰好五个检查；
- `PixelCounterBackend`；
- `LoadedBatch` 不影响；
- `BatchCounts` shape；
- NumPy output；
- Torch range；
- Triton compile-time target_count 与 tensor shape；
- ledger `[N,5]`；
- reporter 五列/group；
- tests 和 schema/version。

不能只把 `range(5)` 改成 `range(len(ids))`。

### 改 ratio 策略

至少影响：

- config validation；
- fingerprint；
- reporter `_ratio`；
- anomalies 定义；
- CSV/JSON 契约；
- tests。

### 加新后端

至少：

- 继承/实现 `PixelCounterBackend`；
- 返回整数 `[B,2,5]`；
- factory 可用性与选择；
- NumPy交叉验证；
- 资源 close；
- manifest name；
- 单元/集成/性能测试。

## 12. 本章自检

1. 为什么建议最后才读 Triton？
2. 哪个对象同时携带 frame 顺序和两个路径？
3. 哪一层第一次把两个来源合成一个 `[B,2,H,W]`？
4. 修改 target 数量为什么是跨层 schema 变更？
5. 测试为何能直接构造 ledger 而不运行 reader？

