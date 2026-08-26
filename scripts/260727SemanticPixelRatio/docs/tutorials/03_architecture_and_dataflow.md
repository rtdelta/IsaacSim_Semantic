# 03｜项目架构与完整执行链

## 1. 先看真实目录，不看理想蓝图

当前实现：

```text
260727SemanticPixelRatio/
├── run_compare.py
├── configs/
├── semantic_pixel_ratio/
│   ├── config.py
│   ├── models.py
│   ├── discovery.py
│   ├── semantic_io.py
│   ├── pipeline.py
│   ├── backends/
│   │   ├── base.py
│   │   ├── factory.py
│   │   ├── numpy_backend.py
│   │   ├── torch_backend.py
│   │   └── triton_backend.py
│   ├── io/
│   │   └── npy_reader.py
│   └── results/
│       ├── atomic_io.py
│       ├── ledger.py
│       ├── lock.py
│       └── reporter.py
└── tests/
```

规划文档中出现但当前不存在的 `validation.py`、`pinned_ring.py`、`runtime/scheduler.py`、`autotuner.py`、`cpu_avx512_backend.py` 等，不应在阅读源码时寻找。

## 2. 入口到结果的调用链

```text
run_compare.main
  ├── load_config
  └── pipeline.run
      ├── load_semantic_mapping
      ├── resolve_target_ids
      ├── discover_frame_pairs
      ├── inspect_dataset_contract
      ├── fingerprint_pairs + mapping_sha256 + _fingerprint
      ├── _prepare_output
      ├── OutputLock
      ├── create_backend
      ├── CountsLedger
      ├── PrefetchingNpyReader
      │   └── load_pair_arrays
      ├── backend.count_batch
      ├── _validate_batch_counts
      ├── _verify_batch（GPU 抽样）
      ├── ledger.append
      ├── ledger.mark_completed + load_all
      └── write_reports
```

阅读项目时，永远先问“当前对象的输入和输出形状是什么”，比逐行记语法有效得多。

## 3. 三条数据流

### 3.1 大数据流：semantic pixels

```text
.npy 文件
  → 单帧 NumPy 数组
  → 连续 LoadedBatch [B,2,H,W]
  → CPU 或 GPU
```

这是最重的数据流，吞吐和内存优化主要围绕它。

### 3.2 小数据流：integer counts

```text
后端输出 [B,2,5]
  → counts/part-*.npz
  → CountLedgerData
  → CSV / JSON / cache
```

它非常小。以一万帧、两个来源、五个目标、每计数 4 字节计算：

```text
10000 × 2 × 5 × 4 = 400,000 bytes
```

所以正确架构是让 GPU 只回传计数，而不是回传整张布尔 mask。

### 3.3 元数据流：配置与契约

```text
config + mapping + 文件 metadata
  → target IDs + dataset contract + fingerprint
  → manifest / resume validation
```

它确保“小计数”确实对应“当前这些输入和标签”，防止拿旧缓存生成新结果。

## 4. 分层职责

| 层 | 只负责什么 | 不负责什么 |
|---|---|---|
| CLI | 解析配置路径、打印结果和退出码 | 不计数 |
| config | JSON 结构、字段和路径合法性 | 不扫描帧 |
| discovery | 发现和严格配对 frame ID | 不加载 payload |
| semantic I/O | mapping、首帧契约、逐帧加载校验 | 不汇总 |
| reader | 分批、并行读、预取、背压 | 不算 ratio |
| backend | `[B,2,H,W] → [B,2,5]` | 不写 CSV |
| pipeline | 组织生命周期、验证、提交 | 不实现具体 kernel |
| ledger | 持久化整数计数和恢复点 | 不计算浮点比值 |
| reporter | 从账本生成 ratio 和报告 | 不重读 semantic 图 |

这种分层使得优化某一层时可以保持其他层不变。例如实现 AVX-512 后端，只要继续满足：

```text
count_batch(LoadedBatch) -> BatchCounts
```

账本和报告都不必修改。

## 5. 为什么整数账本是架构中心

如果 worker 直接写 CSV，会出现：

- 多线程写入互相穿插；
- 完成顺序改变行顺序；
- 崩溃时 CSV 只写了一半；
- 想改变 ratio 精度就要重扫几十 GB 图像；
- GPU 浮点归约顺序可能影响结果。

当前设计让所有后端只回答一个非常窄的问题：

```text
这一批每帧、两个来源、五个 ID，各有多少像素？
```

主进程按 ordinal 提交整数。CSV、summary、anomalies 和 cache 都来自同一账本，因此报告之间不会各算一套口径。

## 6. 一次运行的生命周期

### 阶段 A：启动前验证

1. 读取配置；
2. 检查输入目录和 mapping 文件存在；
3. 解析五个目标 ID；
4. 扫描两目录并严格配对；
5. 用第一帧确定 shape/dtype；
6. 读取所有文件的 path、size、mtime 构造 fingerprint。

此时还没有批量读取全部 payload。

### 阶段 B：建立输出事务边界

1. 根据 overwrite/resume 准备目录；
2. 原子创建 `.run.lock`；
3. 选择后端；
4. 创建或验证 `counts_manifest.json`；
5. 写 `manifest.json` 的 `running` 状态。

### 阶段 C：有界流水处理

```text
后台 producer:
  分 batch → reader 线程池并行 np.load → 连续 batch → 有界 Queue

主线程:
  Queue.get → backend.count_batch → 校验/抽样复核 → ledger.append
```

reader 和计数可以跨 batch 重叠。例如主线程计算 batch 0 时，producer 可以读取 batch 1。

### 阶段 D：提交与报告

1. 标记计数账本 completed；
2. 读取全部小型计数 part；
3. 计算 ratio 与 summary；
4. 原子写出报告；
5. 更新顶层 manifest 为 completed；
6. 离开锁上下文并删除 `.run.lock`。

## 7. 当前真正重叠了什么

当前实现的主要流水重叠是：

```text
下一批磁盘读取  ||  当前批后端计数
```

GPU 后端内部每个 batch：

```text
pageable host
→ pin_memory copy
→ H2D
→ kernel
→ D2H counts
→ 返回
```

没有显式多 stream，也没有在返回前把多个 batch 同时放入 GPU。因此目前不能声称：

```text
batch n 的 D2H || batch n+1 的 kernel || batch n+2 的 H2D
```

`non_blocking=True` 是实现异步传输的必要条件之一，但因为随后要把结果复制回 CPU并返回，调用路径最终仍会同步等待本 batch。

## 8. 背压如何保护内存

队列最多容纳 `ring_slots` 个 `LoadedBatch`。如果后端慢：

```text
Queue 满
→ producer 的 put 等待
→ 不再无限读取更多文件
```

如果磁盘慢：

```text
Queue 空
→ 主线程 get 等待
→ 不会制造没有数据的计算任务
```

这就是背压：下游处理速度通过有界缓冲自动限制上游。

但要精确理解内存：

- 队列中最多有 `ring_slots` 个 batch；
- producer 还可能正在构造一个 batch；
- 主线程还持有正在计算的一个 batch；
- `_load_batch` 期间 futures 可能各自持有单帧数组；
- GPU 路径的 `pin_memory()` 还可能创建一个 pinned 副本；
- GPU 上另有 device batch。

所以 `ring_slots=3` 不代表进程总共只有三个 batch 的内存。

## 9. 错误如何传播

### 配置/发现错误

在加锁和创建大部分输出之前失败，通常不会产生新计数。

### reader 后台错误

producer 捕获异常，放入 `_ReaderFailure`。主线程迭代器重新抛出，pipeline：

```text
ledger.mark_failed
manifest.status = failed
重新抛出
```

### 后端或验证错误

本批在 `ledger.append` 之前失败，因此不会提交半批计数。已经提交的前序 part 保留，可用于恢复。

### 报告错误

可能所有计数已经 completed，但 manifest 被标为 failed。重新运行时可以加载全部计数并重新生成报告，无需重读图像。

## 10. 依赖方向为什么重要

理想依赖关系：

```text
models ← I/O / backends / results
config ← pipeline
backends ← pipeline
reader ← pipeline
ledger/reporter ← pipeline
```

后端不应该导入 reporter，reader 不应该知道 CSV，reporter 不应该调用 GPU。这样单元测试可以用很小的假数据独立验证每层。

当前有一个有意的内部复用：

```python
pipeline.py 从 numpy_backend.py 导入 _count_frame
```

用于 GPU 抽样复核。它说明 NumPy 后端既是 CPU 运行路径，也是正确性 reference。

## 11. 架构级不变量

无论使用哪个后端、batch 多大、线程完成顺序怎样，都必须保持：

```text
frame ordinal 连续
每批 pair 顺序不变
counts.shape == [batch,2,5]
counts 是非负整数
group count <= H×W
同一输入与目标产生同一整数账本
```

性能优化只允许改变“怎么更快得到计数”，不允许改变“计数是什么”。

## 12. 本章自检

1. 为什么后端不能直接计算 summary？
2. 为什么 discovery 阶段不打开全部数组？
3. 当前有哪些跨 batch 重叠，哪些没有？
4. `ring_slots=3` 时为什么内存可能超过三个 batch？
5. 报告生成失败后，为什么续跑通常无需重新计数？

