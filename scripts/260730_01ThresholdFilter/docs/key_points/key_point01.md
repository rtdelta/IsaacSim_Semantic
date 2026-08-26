# ThresholdFilter 高速处理关键点 01

## 1. 文档目的

本文完整整理并扩展以下五个问题：

1. `counts_cache.npz` 是什么格式、包含什么内容，以及它如何由 `260727SemanticPixelRatio` 生成。
2. 万帧数据能否一次性计算，当前批量计算代码如何工作。
3. 输出图片采用硬链接时，输出中究竟保存了什么；删除原图后输出图片是否仍然存在。
4. 单次目录扫描并建立字典映射的可承载数据量与扩展边界。
5. 什么是线程池，为什么 YOLO 小文件过滤适合线程池，以及顺序执行、多进程、逐帧子进程、异步 I/O、GPU 和 NumPy 向量化各自的原理与优缺点。

本文对应当前已实现的项目：

- `260727SemanticPixelRatio`
- `260730_01ThresholdFilter`

当前远端示例运行规模为 1026 帧，实际过滤耗时约 `0.660127 s`，吞吐率约 `1554.246 frame/s`。该结果用于说明当前实现的性能特征，但不应直接视为所有磁盘、数据集和服务器上的固定速度。

---

## 2. 问题一：`counts_cache.npz` 是什么

### 2.1 原问题

> 这个 npz 是什么格式，里面有哪些内容，这份数据是如何得到的，结合 SemanticPixelRatio 项目进行解释。

### 2.2 核心结论

`counts_cache.npz` 是一个 NumPy NPZ 容器。它不是图片、不是 YOLO 标注，也不是数据库，而是一个将多个 NumPy 数组集中存放在同一文件中的二进制归档。

NPZ 文件内部可以理解为一个 ZIP 容器，每个成员都是一个 `.npy` 数组。当前代码使用 `np.savez`，属于不主动压缩的 NPZ，而不是 `np.savez_compressed`。

该文件的主要价值是：

- 将每一帧、每一个斗齿的语义像素数量保存为紧凑的整数矩阵。
- ThresholdFilter 可以直接读取像素计数并计算显露比例，不必再次读取和扫描高分辨率语义图片。
- 相比 CSV，NPZ 读取更快、体积更小，并且可以保留明确的数据类型和矩阵形状。
- 加载时使用 `allow_pickle=False`，不会反序列化任意 Python 对象，数据契约更安全。

### 2.3 当前实际文件内容

远端实际文件为：

```text
/root/gpufree-data/repositories/260727SemanticPixelRatio/output/output0727_01/counts_cache.npz
```

实际文件大小约为 `66,704 bytes`，内部包含四个数组：

| 数组名 | 当前形状 | 数据类型 | 当前数组原始字节数 | 含义 |
| --- | ---: | --- | ---: | --- |
| `ordinals` | `(1026,)` | `int64` | 8,208 | 帧的连续序号，预期为 `0, 1, 2, ...` |
| `frame_ids` | `(1026,)` | Unicode `<U4` | 16,416 | 帧 ID，例如 `0000` |
| `whole_counts` | `(1026, 5)` | `uint32` | 20,520 | 每帧五个斗齿在 whole 语义图中的像素数 |
| `reference_counts` | `(1026, 5)` | `uint32` | 20,520 | 每帧五个斗齿在 reference 语义图中的像素数 |

四个数组的原始数据合计为 `65,664 bytes`。NPZ 文件本身还包含 ZIP 成员头、数组元数据等少量开销，因此磁盘文件为 `66,704 bytes`。

第一帧的实际示例：

```text
frame_id:         0000
whole_counts:     [1129, 1151, 1203, 1364, 1204]
reference_counts: [1144, 1167, 1192, 1408, 1181]
```

矩阵的五列按配置中的物理顺序对应五个斗齿。NPZ 内没有再保存 `tooth_1` 到 `tooth_5` 的字符串列名，因此读取方必须使用同一套目标顺序配置。ThresholdFilter 通过 `labels_in_physical_order` 给这五列赋予业务含义。

### 2.4 显露比例如何从 NPZ 得到

单个斗齿的显露比例定义为：

```text
visible_ratio[frame, tooth]
    = whole_counts[frame, tooth]
    / reference_counts[frame, tooth]
```

例如第一帧第一个斗齿：

```text
1129 / 1144 ≈ 0.9869
```

`counts_cache.npz` 保存的是原始整数计数，不直接保存浮点比例。这样做有几个好处：

- 可以根据需要重新计算比例。
- 不会因为 CSV 文本格式或浮点格式化而损失精度。
- 可以追踪异常来自分子还是分母。
- 可以调整异常处理策略，而无需重新扫描语义图。

斗齿集合的像素计数也没有作为第六列重复存入 NPZ。`SemanticPixelRatio` 在生成报告时动态求和：

```python
whole_values = ledger.whole_counts.sum(axis=1, dtype=np.uint64)
reference_values = ledger.reference_counts.sum(axis=1, dtype=np.uint64)
```

集合比例可表示为：

```text
group_ratio
    = sum(whole_counts of five teeth)
    / sum(reference_counts of five teeth)
```

不过，当前 ThresholdFilter 的“规则 2”不是直接使用集合总比例。它会分别计算五个斗齿的显露比例，然后统计有多少个斗齿低于阈值 `b`；如果数量达到配置值（当前规则为三个或更多），才删除斗齿集合框。

### 2.5 数据从语义图到 NPZ 的完整链路

数据流如下：

```text
每帧 whole/reference 语义数组
        ↓
按批加载为 [B, 2, H, W]
        ↓
分别对 whole 和 reference 做像素 ID 直方图统计
        ↓
抽取五个目标 semantic ID 的计数
        ↓
得到每帧 [2, 5]，每批 [B, 2, 5]
        ↓
按批写入 part-xxxxxxxxx-xxxxxxxxx.npz
        ↓
任务结束后拼接所有 part
        ↓
写出最终 counts_cache.npz
```

其中：

- `B` 是批大小。
- 维度 `2` 分别对应 whole 和 reference 两个输入源。
- 维度 `5` 对应五个斗齿。
- 原始高分辨率语义图按批进入内存，不会为了生成最终 NPZ 而将全部帧图片同时保存在内存中。

### 2.6 SemanticPixelRatio 当前像素统计代码

源码位置：

```text
scripts/260727SemanticPixelRatio/semantic_pixel_ratio/backends/numpy_backend.py
```

核心代码：

```python
def _count_frame(frame_data: np.ndarray, target_ids: np.ndarray) -> np.ndarray:
    output = np.empty((2, 5), dtype=np.uint32)
    for source_index in range(2):
        histogram = np.bincount(frame_data[source_index].reshape(-1))
        for target_index, semantic_id in enumerate(target_ids):
            output[source_index, target_index] = (
                histogram[int(semantic_id)]
                if int(semantic_id) < histogram.size
                else 0
            )
    return output
```

逐步解释：

1. `output = np.empty((2, 5), dtype=np.uint32)`
   - 为一帧创建 `2 × 5` 的计数结果。
   - 两行是 whole/reference，五列是五个斗齿。

2. `for source_index in range(2)`
   - 分别统计 whole 和 reference。

3. `frame_data[source_index].reshape(-1)`
   - 将二维语义图展平成一维像素 ID 序列。
   - `reshape(-1)` 在数组连续时通常只是视图，不复制整张图。

4. `np.bincount(...)`
   - 一次遍历像素 ID，生成直方图。
   - `histogram[k]` 表示 semantic ID 为 `k` 的像素数量。
   - 与对每个目标 ID 分别执行五次整图比较相比，一次直方图统计通常更高效。

5. 遍历五个 `target_ids`
   - 从直方图中直接读取五个目标 semantic ID 的计数。
   - 如果某个 semantic ID 大于直方图范围，说明该 ID 在当前图中没有出现，计数写为 0。

一批帧由线程池并发统计：

```python
def count_batch(self, batch: LoadedBatch) -> BatchCounts:
    futures = [
        self._pool.submit(_count_frame, batch.data[index], self._target_ids)
        for index in range(len(batch.pairs))
    ]
    counts = np.stack([future.result() for future in futures], axis=0)
    return BatchCounts(pairs=batch.pairs, counts=counts)
```

`np.stack` 后得到：

```text
[batch_size, 2, 5]
```

### 2.7 为什么中间还要写分片 NPZ

SemanticPixelRatio 并不是等所有帧处理完才第一次写盘。每完成一批，会将结果写成：

```text
part-000000000-000000xxx.npz
```

每个分片包含：

```python
np.savez(
    handle,
    ordinals=np.asarray(actual_ordinals, dtype=np.int64),
    frame_ids=np.asarray(
        [pair.frame_id for pair in result.pairs],
        dtype=np.str_,
    ),
    whole_counts=np.asarray(
        result.counts[:, 0, :],
        dtype=np.uint32,
    ),
    reference_counts=np.asarray(
        result.counts[:, 1, :],
        dtype=np.uint32,
    ),
)
```

分片设计的作用：

- 避免长任务必须在内存中积累所有结果。
- 每批完成后即可形成持久化检查点。
- 中途失败时，已经完成的批次仍可验证和恢复。
- 每个 part 在清单中记录帧范围和 SHA-256，便于检查完整性。

最终再通过 `np.concatenate` 拼接全部分片，并由以下代码写出最终缓存：

```python
def write_counts_cache(path: Path, ledger: CountLedgerData) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            np.savez(
                handle,
                ordinals=ledger.ordinals,
                frame_ids=np.asarray(ledger.frame_ids, dtype=np.str_),
                whole_counts=ledger.whole_counts,
                reference_counts=ledger.reference_counts,
            )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
```

这里采用“临时文件 + `flush` + `fsync` + 原子替换”：

- 写入未完成时不会直接污染最终文件。
- 只有完整写盘后，临时文件才替换正式路径。
- 进程异常退出时，旧的正式文件不会成为半截 NPZ。

### 2.8 ThresholdFilter 如何读取 NPZ

源码位置：

```text
scripts/260730_01ThresholdFilter/threshold_filter/ratio_reader.py
```

读取逻辑：

```python
archive = np.load(path, allow_pickle=False)

required = {"frame_ids", "whole_counts", "reference_counts"}
missing = sorted(required - set(archive.files))
if missing:
    raise ValueError(
        "counts cache is missing arrays: " + ", ".join(missing)
    )

frame_array = np.asarray(archive["frame_ids"])
frame_ids = tuple(str(value) for value in frame_array.tolist())

if "ordinals" in archive.files:
    expected_ordinals = np.arange(len(frame_ids), dtype=np.int64)
    ordinals = np.asarray(archive["ordinals"], dtype=np.int64)
    if not np.array_equal(ordinals, expected_ordinals):
        raise ValueError(
            "counts cache ordinals are incomplete or unordered"
        )

whole = np.asarray(archive["whole_counts"])
reference = np.asarray(archive["reference_counts"])
```

读取时会验证：

- 必需数组是否存在。
- `frame_ids` 是否是一维。
- 帧 ID 是否为空或重复。
- `ordinals` 是否从 0 开始连续且有序。
- 两个计数矩阵是否具有预期的 `[帧数, 5]` 形状。
- 计数是否是整数、是否非负。

### 2.9 `reference_missing`、`empty_ratio` 和 `ratio_over_one`

NPZ 中不直接保存字符串状态。ThresholdFilter 根据原始计数重新推导状态：

```python
whole = whole_counts.astype(np.uint64, copy=False)
reference = reference_counts.astype(np.uint64, copy=False)
valid = reference > 0
ratios = np.full(expected, np.nan, dtype=np.float64)
np.divide(whole, reference, out=ratios, where=valid)

computed_statuses = np.full(expected, "valid", dtype="<U20")
computed_statuses[~valid] = "reference_missing"
over_one = valid & (ratios > 1.0)
computed_statuses[over_one] = "ratio_over_one"
```

含义如下：

| 状态 | 原始数据特征 | 比例值 |
| --- | --- | --- |
| `valid` | `reference_pixels > 0` 且比例不大于 1 | 正常有限浮点数 |
| `reference_missing` | `reference_pixels == 0` | `NaN`，避免除以零 |
| `ratio_over_one` | `reference_pixels > 0` 且 `whole/reference > 1` | 大于 1，后续按配置保留、裁剪或报错 |
| `empty_ratio` | 主要用于 CSV 输入显式声明比例字段为空 | `NaN` |

远端这批 1026 帧数据中：

- 五个斗齿共 `5130` 个比例条目。
- `4418` 个状态为 `valid`。
- `712` 个状态为 `ratio_over_one`。
- 没有 `reference_missing`。

`ratio_over_one` 不必然表示程序计算错误。语义渲染差异、可见边缘变化、抗锯齿或参考场景与完整场景的像素覆盖差异，都可能使 whole 计数略大于 reference 计数。如何处理由配置中的 `ratio_over_one` 策略决定。

---

## 3. 问题二：万帧数据能否一次性计算

### 3.1 原问题

> 假如文件量达到万帧也能一次性计算完吗？当前批量计算的代码块请展示出来并详细讲解分析。

### 3.2 首先区分两种“一次性”

本项目中有两种容易混淆的“一次性”：

1. SemanticPixelRatio 对原始高分辨率语义图进行像素统计。
   - 原始图数据大。
   - 当前采用分批加载、分批统计、分片落盘。
   - 不会把一万帧的两套原始语义图同时装入内存。

2. ThresholdFilter 对已经生成的 `counts_cache.npz` 进行比例和阈值计算。
   - 每帧只有五个 whole 计数和五个 reference 计数。
   - 数据非常紧凑。
   - 一万帧可以一次加载全部计数并通过 NumPy 向量化一次计算。

因此，“万帧能否处理”的答案是：可以。原始图片阶段应继续按批处理；计数矩阵阶段一次加载一万帧没有压力。

### 3.3 一万帧 NPZ 的大致体积

以 `N = 10,000`、五个斗齿估算：

| 数据 | 计算 | 约占空间 |
| --- | ---: | ---: |
| `ordinals int64` | `N × 8` | 80 KB |
| `frame_ids <U5` | `N × 5 × 4` | 200 KB |
| `whole_counts uint32` | `N × 5 × 4` | 200 KB |
| `reference_counts uint32` | `N × 5 × 4` | 200 KB |
| 合计 | 不含少量 NPZ 元数据 | 约 680 KB |

即使达到一万帧，原始计数缓存仍通常不到 1 MB。它与一万帧 720p 或更高分辨率图片不是同一个数量级。

### 3.4 ThresholdFilter 当前批量比例计算代码

```python
whole = whole_counts.astype(np.uint64, copy=False)
reference = reference_counts.astype(np.uint64, copy=False)
valid = reference > 0
ratios = np.full(expected, np.nan, dtype=np.float64)
np.divide(whole, reference, out=ratios, where=valid)
```

逐行说明：

1. `astype(np.uint64, copy=False)`
   - 将像素数按无符号 64 位整数处理。
   - 避免后续求和时发生 `uint32` 溢出。
   - 当原数组已经是目标类型时允许不复制；当前 NPZ 是 `uint32`，因此这里通常会创建 `uint64` 数组。

2. `valid = reference > 0`
   - 一次生成形状为 `[N, 5]` 的布尔矩阵。
   - 分母为 0 的位置记为无效。

3. `np.full(expected, np.nan, dtype=np.float64)`
   - 先将比例矩阵全部填为 `NaN`。
   - 无效位置会自然保留为 `NaN`。

4. `np.divide(..., where=valid)`
   - NumPy 在底层 C 循环中对所有有效元素批量除法。
   - `where=valid` 避免分母为 0 的位置参与运算。
   - 不需要 Python 写两层循环逐帧、逐斗齿处理。

### 3.5 当前阈值规则的向量化代码

```python
valid = np.isfinite(ratios.ratios)

single_drop = valid & (
    ratios.ratios < config.rules.single_tooth.minimum_visible_ratio
)

group_low = valid & (
    ratios.ratios < config.rules.tooth_group.minimum_visible_ratio
)

group_low_counts = group_low.sum(axis=1, dtype=np.int16)

group_drop = (
    group_low_counts >= config.rules.tooth_group.minimum_low_teeth
)
```

对应业务规则：

1. `single_drop`
   - 形状为 `[N, 5]`。
   - 某个位置为 `True` 表示该帧对应斗齿的显露比例低于阈值 `a`。
   - 处理该帧 YOLO 标注时，需要删除这个斗齿框。

2. `group_low`
   - 同样是 `[N, 5]`。
   - 某个位置为 `True` 表示该斗齿低于集合判断阈值 `b`。

3. `group_low.sum(axis=1)`
   - 沿五个斗齿这一维求和。
   - 每帧得到一个 0 到 5 的整数。
   - 例如 `[True, False, True, True, False]` 的和为 3。

4. `group_drop`
   - 形状为 `[N]`。
   - 当低于阈值 `b` 的斗齿数达到 `minimum_low_teeth` 时为 `True`。
   - 当前配置若为 3，就实现“三个或三个以上斗齿低于阈值 b，则删除斗齿集合框”。

### 3.6 算法复杂度

斗齿数量固定为 5，因此比例与规则计算量为：

```text
O(N × 5)
```

对一万帧只有五万个元素。对 NumPy 来说非常小，计算通常远快于以下操作：

- 扫描目录。
- 打开大量小型 YOLO 文本文件。
- 解析字符串。
- 创建输出目录项。
- 写入新标签。
- 写 CSV 报告。

本次远端运行也印证了这一点：规则矩阵计算只占极短时间，整体约 `0.66 s` 的主要成本来自文件系统和逐帧标注处理。

### 3.7 一万、十万和百万帧的内存判断

不能只看 NPZ 文件大小，还要计算 ThresholdFilter 加载后的派生数组和 Python 对象。

#### 一万帧

主要 NumPy 数据大致包括：

- `whole uint64`：约 400 KB。
- `reference uint64`：约 400 KB。
- `ratios float64`：约 400 KB。
- `statuses <U20`：约 4 MB。
- 若干 `[N, 5]` 布尔掩码：每个约 50 KB。
- 每帧集合计数、集合删除掩码：很小。

即使再加上文件索引、结果对象和报告数据，一般也只是几十 MB，完全适合一次处理。

#### 十万帧

- `statuses <U20` 约 40 MB。
- 两个 `uint64` 计数矩阵约 8 MB。
- 比例矩阵约 4 MB。
- 多个掩码为数 MB。
- 四十万个文件索引项以及大量 Python 结果对象可能成为主要内存开销。

十万帧仍有可能一次运行，但应在目标服务器上做峰值内存和目录性能测试。

#### 一百万帧

- 单独一个 `[1,000,000, 5]` 的 `<U20` 状态矩阵约 400 MB。
- 两个 `uint64` 计数矩阵合计约 80 MB。
- 比例矩阵约 40 MB。
- 多个掩码、文件索引、数百万 Python 决策对象和 CSV 行可能将总内存推到数 GB。

百万帧不建议继续使用“全部加载、全部建立 Python 对象、最后统一写报告”的模式。

### 3.8 超大数据量的扩展方案

如果未来达到数十万或百万帧，建议按优先级采用：

1. 将字符串状态矩阵改成 `uint8` 枚举。
   - 例如 `0=valid`、`1=reference_missing`、`2=ratio_over_one`、`3=empty_ratio`。
   - 一百万帧五列只需约 5 MB，而不是约 400 MB。

2. 每批处理 10,000 到 50,000 帧。
   - 读取一批计数。
   - 计算一批掩码。
   - 过滤一批标注。
   - 立即追加报告，然后释放该批内存。

3. 直接消费 SemanticPixelRatio 的 part NPZ。
   - 不必先把所有 part 拼接成一个内存总表。

4. 流式写 `decisions.csv` 和 `frame_summary.csv`。
   - 不在内存中保留全部 `FrameResult` 和全部决策对象。

5. 使用适合分块或列式读取的格式。
   - `.npy` + `memmap`
   - Apache Arrow
   - Parquet

---

## 4. 问题三：硬链接图片是否只是路径，删除原图后还在吗

### 4.1 原问题

> 这里的意思是否是 output 中并不是真正的图片而是路径链接？如果删除处理前的原文件，处理后的图片还在吗？

### 4.2 核心结论

当前 `hardlink_required` 模式生成的是硬链接，不是符号链接。

输出目录中的图片不是一个“保存源文件路径的快捷方式”。输出路径和输入路径是两个独立目录项，但它们共同指向文件系统中的同一个 inode 和同一份数据块。

因此：

- 删除输入目录中的原图片路径后，输出图片仍然存在且可以正常读取。
- 只有指向该 inode 的最后一个硬链接也被删除后，文件数据才会真正释放。
- 输出硬链接不额外复制整张图片，因此速度快、几乎不增加图片数据占用。

### 4.3 硬链接、符号链接和复制的区别

| 方式 | 输出中保存的本质 | 删除源路径后 | 是否重复占用图片数据 | 能否跨文件系统 |
| --- | --- | --- | --- | --- |
| 硬链接 | 指向同一 inode 的新目录项 | 输出仍可用 | 基本不重复 | 不能 |
| 符号链接 | 一段指向源路径的路径文本 | 通常变成断链 | 基本不重复 | 可以 |
| 文件复制 | 新 inode、新数据副本 | 输出仍可用 | 会重复占用 | 可以 |

### 4.4 当前代码

源码位置：

```text
scripts/260730_01ThresholdFilter/threshold_filter/atomic_io.py
```

```python
def materialize_image(source: Path, destination: Path, mode: str) -> None:
    if mode == "none":
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    if mode == "hardlink_required":
        os.link(source, destination)
        return
    if mode == "hardlink_or_copy":
        try:
            os.link(source, destination)
        except OSError:
            shutil.copy2(source, destination)
        return
    if mode == "symlink":
        os.symlink(source, destination)
        return
    if mode == "copy":
        shutil.copy2(source, destination)
        return
    raise ValueError(f"unsupported image mode: {mode}")
```

模式说明：

- `none`：不输出图片。
- `hardlink_required`：必须创建硬链接，失败即报错。
- `hardlink_or_copy`：先尝试硬链接；如果跨文件系统或文件系统不支持，则回退为复制。
- `symlink`：创建符号链接。
- `copy`：完整复制图片。

### 4.5 删除和修改时的具体行为

假设输入和输出为：

```text
input/rgb_0000.png
output/rgb_0000.png
```

两者是硬链接。

#### 删除输入路径

```text
删除 input/rgb_0000.png
```

结果：

- inode 的链接计数减 1。
- `output/rgb_0000.png` 仍指向原 inode。
- 输出图片内容仍然完整。

#### 重命名输入路径

输入文件重命名不会影响输出硬链接。输出仍指向同一 inode。

#### 在原路径重新创建一个同名文件

如果删除原路径后又创建新的 `input/rgb_0000.png`，新文件通常拥有新的 inode。此时：

- 新输入路径指向新图片。
- 旧输出硬链接仍保留旧图片。
- 虽然文件名相同，两者已经不是同一文件数据。

#### 原地修改任意一个硬链接

如果程序打开输出硬链接并直接改写文件内容，那么输入路径看到的内容也会变化，因为两者共享 inode 和数据。

同理，`chmod`、`chown` 等 inode 元数据变化也会由所有硬链接共同体现。

因此，硬链接图片应视为只读数据。ThresholdFilter 当前只创建链接并读取图片，不会改写其像素内容。

需要注意一个细节：如果编辑软件采用“写临时文件，再原子替换原路径”的保存方式，它可能只让被替换的那个路径指向新 inode，另一个硬链接仍指向旧 inode。这与直接原地覆盖字节的行为不同。

### 4.6 当前远端结果的实际验证

已经对远端示例中的一张源图和输出图执行 inode 检查：

```text
source inode = 1445391
output inode = 1445391
hard link count = 5
```

源和输出 inode 相同，证明当前输出图片确实是硬链接，不是符号链接，也不是复制得到的新 inode。

链接计数为 5 表示当时共有五个目录项指向同一份文件数据。删除其中一个路径只会让计数减少，不会立刻删除数据。

### 4.7 哪些文件使用硬链接

当前策略只针对图片：

- 输出 PNG 图片使用配置指定的硬链接、复制或符号链接模式。
- 输出 YOLO `.txt` 标注不是硬链接。
- 标注文件经过规则过滤后会重新生成，因为内容已经与输入标注不同。
- CSV、JSON 和运行清单也是新写出的结果文件。

---

## 5. 问题四：单次目录扫描和字典映射的数据量极限

### 5.1 原问题

> 单次目录扫描建立字典映射的数据量极限大约是多少？

### 5.2 核心结论

这里没有一个固定的“帧数硬上限”。极限主要由以下因素共同决定：

- 可用内存。
- 单目录中的文件数量。
- 文件系统类型和目录索引能力。
- 存储介质的随机访问与元数据性能。
- Python 字典、字符串和 `Path` 对象的内存开销。
- 后续是否还在内存中保留所有帧结果和报告对象。

对于当前设计：

- 一万帧很安全。
- 十万帧通常仍可行，但应测试内存和目录元数据性能。
- 百万帧不建议将所有文件平铺在单个目录，并一次建立数百万条 Python 映射。

### 5.3 当前扫描代码

源码位置：

```text
scripts/260730_01ThresholdFilter/threshold_filter/file_index.py
```

```python
def _scan_module(directory: Path) -> ModuleFileIndex:
    labels: Dict[str, Path] = {}
    images: Dict[str, Path] = {}
    with os.scandir(directory) as entries:
        for entry in entries:
            if not entry.is_file():
                continue
            if entry.name == "classes.txt":
                continue
            if entry.name.startswith(PREFIX) and entry.name.endswith(LABEL_SUFFIX):
                frame_id = entry.name[len(PREFIX) : -len(LABEL_SUFFIX)]
                target = labels
            elif entry.name.startswith(PREFIX) and entry.name.endswith(IMAGE_SUFFIX):
                frame_id = entry.name[len(PREFIX) : -len(IMAGE_SUFFIX)]
                target = images
            else:
                continue
            if not frame_id:
                raise ValueError(f"module file has an empty frame ID: {entry.name}")
            if frame_id in target:
                raise ValueError(
                    f"module directory contains duplicate frame ID {frame_id}: "
                    f"{directory}"
                )
            target[frame_id] = Path(entry.path)
```

当前每个模块只扫描一次：

- 遇到 `.txt` 时写入 `labels[frame_id] = Path`。
- 遇到 `.png` 时写入 `images[frame_id] = Path`。
- 后续每帧通过字典按 `frame_id` 查找，不再反复遍历目录。

### 5.4 为什么比逐帧搜索更快

假设有 `N` 帧：

- 单次扫描建立索引：扫描复杂度约 `O(N)`。
- 字典平均查找：每次约 `O(1)`。
- 整体仍约 `O(N)`。

如果每处理一帧都重新遍历目录寻找对应文件，最坏可能接近：

```text
O(N²)
```

而且会重复触发大量目录项读取和文件系统元数据访问。

### 5.5 当前示例索引规模

远端当前数据：

- 单齿模块标签：1026。
- 单齿模块图片：1026。
- 集合模块标签：627。
- 集合模块图片：627。

合计：

```text
1026 + 1026 + 627 + 627 = 3306 个字典条目
```

这个规模非常小。

### 5.6 不同帧数的粗略内存范围

若两个模块在每一帧都有标签和图片，则每帧最多产生四个索引条目：

```text
tooth label + tooth image + group label + group image
```

Python 64 位环境中，一个映射条目不仅有字典槽，还包括：

- `frame_id` 字符串对象。
- `Path` 对象。
- Path 内部的路径字符串和组成部分。
- Python 对象头、引用和内存对齐。

因此不能只按文件名的字符数计算。根据路径长度和 Python 版本，可用下面的数量级作为规划参考：

| 帧数 | 最大映射条目数 | 索引内存粗略范围 | 建议 |
| ---: | ---: | ---: | --- |
| 1 万 | 4 万 | 约 10–30 MB | 很安全 |
| 10 万 | 40 万 | 约 100–300 MB | 可行，但应实测 |
| 100 万 | 400 万 | 约 1–3 GB 或更高 | 不建议当前方式 |

这只是文件索引，不含比例矩阵、标注解析结果、报告对象和线程任务。

### 5.7 单次扫描是否会同时打开所有文件

不会。

`os.scandir` 遍历目录项时，代码保留的是路径对象，不会为每个文件长期保持打开的文件描述符。退出 `with os.scandir(...)` 后目录句柄关闭。

因此当前映射的主要成本是内存中的 Python 对象，不是“同时打开几万个文件”。

处理帧时才会按需打开对应的 `.txt` 文件；线程池还通过 `max_in_flight` 限制同时在途的帧任务数。

### 5.8 文件系统层面的现实限制

即使 Python 内存足够，把数百万文件放进一个目录也会产生工程问题：

- 首次扫描时间变长。
- `ls`、查找、备份、同步、删除和运维工具响应变慢。
- inode 数量可能耗尽。
- 大量元数据随机访问会使机械盘和网络文件系统明显变慢。
- 即使 ext4 等文件系统支持大型哈希目录，“技术上能放”也不等于“工程上适合这样组织”。

### 5.9 超大规模目录的改进方案

1. 按帧 ID 前缀分片目录。

```text
tooth/
  000/
  001/
  002/
```

或：

```text
tooth/00/00/rgb_00000123.png
```

2. 生成显式文件清单。

```text
frame_id,tooth_label,tooth_image,group_label,group_image
```

处理程序可以顺序读取清单，不必每次扫描大型目录。

3. 使用 SQLite 保存索引。

- 适合数十万到数百万条路径。
- 可按 `frame_id` 建索引。
- 无需在 Python 内存中保留全部映射。

4. 使用排序后归并或流式处理。

- 文件名与 NPZ 帧 ID 都按 frame ID 排序。
- 像合并两个有序序列一样前进。
- 内存中只保留当前批次。

5. 将索引、比例计算、报告写出统一改为分块流水线。

---

## 6. 问题五：什么是线程池，为什么本项目适合线程池

### 6.1 原问题

> 什么是线程池？为什么适合线程池而不是其它的？请分别讲解各个办法的原理以及优劣。

### 6.2 线程池是什么

线程池由以下部分组成：

- 固定数量或受控数量的工作线程。
- 一个等待执行的任务队列。
- 一个负责提交任务和收集结果的主线程。

线程创建后会被重复使用。处理 1026 帧并不是创建 1026 个线程，而是例如创建 8 个工作线程，让它们不断从任务队列中领取帧任务。

示意：

```text
主线程
  ├─ 提交 frame 0000 ─┐
  ├─ 提交 frame 0001 ─┤
  ├─ 提交 frame 0002 ─┤→ 有界任务队列 → 8 个可复用工作线程
  └─ 收集完成结果 ────┘
```

### 6.3 为什么 YOLO 过滤适合线程池

ThresholdFilter 的逐帧工作主要是：

- 打开小型 `.txt` 文件。
- 读取 YOLO 行。
- 解析少量字符串和浮点数。
- 根据预先计算好的掩码保留或删除行。
- 写入新的 `.txt` 文件。
- 调用 `os.link` 创建图片硬链接。
- 写少量异常和决策记录。

这些工作的大量时间不是在执行复杂数学运算，而是在等待操作系统和文件系统：

- 等待目录项查询。
- 等待文件打开。
- 等待读取。
- 等待写入。
- 等待创建硬链接。

一个线程等待 I/O 时，其他线程可以继续处理别的帧。Python 的文件 I/O 和许多系统调用会在等待期间释放 GIL，所以多个线程可以重叠这些等待时间。

而且：

- 所有线程可以直接共享只读的比例矩阵和规则掩码。
- 不需要把大数组复制到多个进程。
- 每个线程写入不同帧的输出文件，天然避免多个线程同时写同一个标签文件。
- 启动和调度成本远低于为每帧创建进程。

### 6.4 当前线程池实现

源码位置：

```text
scripts/260730_01ThresholdFilter/threshold_filter/pipeline.py
```

核心代码：

```python
with ThreadPoolExecutor(max_workers=config.execution.workers) as executor:
    pending: Dict[Future, int] = {}
    next_ordinal = 0

    def submit_until_full() -> None:
        nonlocal next_ordinal
        while (
            next_ordinal < frame_count
            and len(pending) < config.execution.max_in_flight
        ):
            ordinal = next_ordinal
            next_ordinal += 1
            future = executor.submit(
                _process_frame,
                ordinal,
                config,
                ratios,
                masks,
                file_index,
                resolver,
                writer,
            )
            pending[future] = ordinal

    submit_until_full()
    stop_submitting = False
    while pending:
        done, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
        for future in done:
            ordinal = pending.pop(future)
            try:
                results.append(future.result())
            except BaseException as exc:
                errors.append((ordinal, exc))
                if config.execution.on_error == "fail_fast":
                    stop_submitting = True
        if stop_submitting:
            for future in pending:
                future.cancel()
            break
        submit_until_full()
```

关键设计点：

#### `max_workers`

控制真正工作的线程数量。

当前远端示例配置为：

```text
workers = 8
```

#### `max_in_flight`

控制“已经提交但尚未完成”的任务上限。

当前远端示例配置为：

```text
max_in_flight = 32
```

它可以避免一次把一万或十万帧全部提交成 `Future`：

- 降低任务对象的内存开销。
- 限制同时活跃的文件 I/O。
- 避免文件系统队列被瞬间灌满。
- 让失败停止提交时更及时。

#### `FIRST_COMPLETED`

只要有一批任务中的任意一个完成，主线程就立刻收集它，并补交新任务，使线程池持续保持忙碌。

#### 最终按 ordinal 排序

线程完成顺序不确定。代码最终执行：

```python
return tuple(sorted(results, key=lambda item: item.ordinal))
```

因此报告仍按原始帧顺序稳定输出。

### 6.5 各种执行方式对比

| 方法 | 基本原理 | 优点 | 缺点 | 本项目适用性 |
| --- | --- | --- | --- | --- |
| 顺序执行 | 一个线程逐帧完成全部工作 | 最简单；调试容易；顺序天然确定 | 等待一个文件时 CPU 和程序都闲着；小文件很多时吞吐较低 | 可作为基准或 `workers=1` 安全模式 |
| 线程池 | 多个可复用线程共享内存并重叠 I/O 等待 | 启动轻；无需序列化共享数组；适合大量小文件 I/O | CPU 密集 Python 代码受 GIL 限制；线程过多会竞争磁盘和元数据锁 | 当前首选 |
| 进程池 | 多个独立 Python 进程并行执行 | 绕过 GIL；适合纯 Python CPU 密集计算 | 启动、IPC、序列化和结果回传成本高；内存更大；错误处理更复杂 | 不适合当前细粒度小文件任务 |
| 每帧创建子进程 | 每帧启动一个新进程或外部程序 | 隔离强；单帧工具可独立运行 | 进程启动成本巨大；容易达到进程或句柄上限；调度和日志混乱 | 最不推荐 |
| `asyncio` | 单线程事件循环在任务等待时切换 | 网络 socket、大量高延迟请求中表现好；任务切换轻 | 普通本地文件 I/O 往往不是真正异步，最终仍需线程；代码复杂度增加 | 收益通常不如线程池直接 |
| GPU | 将大规模并行数值计算送到显卡 | 对大数组、像素统计、深度学习推理极快 | 不能加速 `open/read/write/os.link`；传输和启动有成本 | 适合上游像素计算，不适合本过滤器 I/O |
| NumPy 向量化 | 用底层 C 循环批量计算矩阵 | 比 Python 双重循环快；代码简洁；内存连续 | 仍需占用矩阵内存；不负责小文件 I/O | 已用于比例和规则计算，与线程池互补 |

### 6.6 为什么不使用多进程

多进程最有价值的场景是：

- 大量纯 Python CPU 计算。
- 单个任务足够重，进程通信成本只占很小比例。
- 各任务可以相对独立地运行较长时间。

当前一帧 YOLO 过滤任务非常小。如果改为进程池，还需要处理：

- 将任务参数发送给子进程。
- 在子进程中重新建立或继承运行状态。
- 将 `FrameResult` 序列化后传回主进程。
- 多进程共享或复制 NumPy 数据。
- 多进程同时争用同一磁盘和同一目录元数据。

在 Windows 上默认 `spawn`，新进程启动成本尤其明显；远端 Linux 的 `fork` 较轻，但仍存在进程调度、IPC 和文件系统竞争。对于当前任务，这些成本很可能超过它带来的收益。

### 6.7 为什么不能每帧启动一个子进程

若一万帧启动一万个进程，即使不是同时启动，也会反复支付：

- 创建进程。
- 初始化 Python 解释器或外部程序。
- 加载模块。
- 建立文件描述符和环境。
- 回收进程。

如果并发不受控，还可能：

- 达到系统进程上限。
- 达到文件描述符上限。
- 让磁盘随机 I/O 和目录锁严重竞争。
- 造成大量上下文切换。

线程池的关键优势正是“少量工作线程反复复用”，不会为每帧重新启动执行环境。

### 6.8 为什么 GPU 不适合 ThresholdFilter

GPU 擅长：

- 对大型连续数组执行同一种数值运算。
- 图像像素统计。
- 矩阵运算。
- 神经网络推理。

GPU 不擅长或无法直接替代：

- 打开 1026 个文本文件。
- 解析每个文件中少量不定长文本行。
- 创建目录项。
- 写不同大小的小文件。
- 调用 Linux `link` 系统调用。

即使把五万个比例元素传到 GPU，数据传输、CUDA kernel 启动和结果回传的成本也可能高于 CPU NumPy 直接计算。当前阈值矩阵本身极小，真正瓶颈是文件 I/O。

上游 SemanticPixelRatio 的输入是整张语义图，数据规模远大于 `[N, 5]`，因此像素计数阶段可以考虑 GPU 后端；下游 ThresholdFilter 则不需要 GPU。

### 6.9 为什么线程数不是越多越好

线程过多可能导致：

- 上下文切换增加。
- 多线程争抢同一磁盘带宽。
- 同一目录的元数据操作竞争。
- 文件系统缓存命中率下降。
- 同时打开文件数过多。
- 内存中 `Future`、缓冲区和结果对象增多。

建议以实际机器为准做基准测试，例如：

```text
workers = 1, 2, 4, 8, 16
```

每次保持同一份输入，记录：

- 总耗时。
- frame/s。
- CPU 使用率。
- 磁盘利用率与 IOPS。
- 峰值内存。
- 是否出现文件系统错误。

如果从 8 增加到 16 后速度不升反降，说明瓶颈已经转移到磁盘、目录元数据或调度，不应继续增加线程。

### 6.10 当前远端实测

本次运行配置：

```text
workers = 8
max_in_flight = 32
image_mode = hardlink_required
frames = 1026
```

实测：

```text
elapsed_seconds ≈ 0.660127
frames_per_second ≈ 1554.246
```

该速度来自以下组合，而不是只来自线程池：

- NPZ 紧凑计数缓存。
- 一次加载并向量化计算全部比例。
- 一次目录扫描建立字典索引。
- 有界线程池处理小文件 I/O。
- 图片使用硬链接，不复制 PNG 数据。
- 输出先写 staging 目录，完成后统一提交。

---

## 7. 综合建议

### 7.1 当前数据规模

对于一万帧级别，保持当前架构即可：

1. SemanticPixelRatio 分批读取原始语义图。
2. 每批写入 part NPZ。
3. 最终生成紧凑的 `counts_cache.npz`。
4. ThresholdFilter 一次加载全部计数。
5. 用 NumPy 向量化计算规则 1 和规则 2。
6. 单次扫描标注与图片目录。
7. 用有界线程池过滤小型 YOLO 文件。
8. 图片继续使用硬链接，但保持只读。

### 7.2 达到十万帧

需要重点监控：

- Python 文件索引占用。
- 状态字符串矩阵占用。
- `FrameResult` 和决策对象占用。
- 大型单目录的扫描与元数据操作速度。
- CSV 报告生成时间。

优先优化字符串状态为枚举，并考虑目录分片。

### 7.3 达到百万帧

建议升级为完整的分块流式流水线：

```text
读取一批计数
    ↓
计算一批比例和规则
    ↓
加载该批文件路径
    ↓
过滤并写出标注
    ↓
流式追加报告
    ↓
释放内存
```

同时使用：

- 分片目录或清单/数据库索引。
- `uint8` 状态枚举。
- 分块 NPZ、memmap、Arrow 或 Parquet。
- 有界线程池。
- 分批或分区报告。

---

## 8. 相关源码位置

- SemanticPixelRatio NumPy 像素统计：
  `D:\learning\IntelligentDepartment\CodesSet\Self\260707IsaacSIm\scripts\260727SemanticPixelRatio\semantic_pixel_ratio\backends\numpy_backend.py`
- SemanticPixelRatio 分片账本：
  `D:\learning\IntelligentDepartment\CodesSet\Self\260707IsaacSIm\scripts\260727SemanticPixelRatio\semantic_pixel_ratio\results\ledger.py`
- SemanticPixelRatio 最终缓存与报告：
  `D:\learning\IntelligentDepartment\CodesSet\Self\260707IsaacSIm\scripts\260727SemanticPixelRatio\semantic_pixel_ratio\results\reporter.py`
- ThresholdFilter NPZ/CSV 比例读取：
  `D:\learning\IntelligentDepartment\CodesSet\Self\260707IsaacSIm\scripts\260730_01ThresholdFilter\threshold_filter\ratio_reader.py`
- ThresholdFilter 向量化规则：
  `D:\learning\IntelligentDepartment\CodesSet\Self\260707IsaacSIm\scripts\260730_01ThresholdFilter\threshold_filter\rules.py`
- ThresholdFilter 单次目录索引：
  `D:\learning\IntelligentDepartment\CodesSet\Self\260707IsaacSIm\scripts\260730_01ThresholdFilter\threshold_filter\file_index.py`
- ThresholdFilter 有界线程池：
  `D:\learning\IntelligentDepartment\CodesSet\Self\260707IsaacSIm\scripts\260730_01ThresholdFilter\threshold_filter\pipeline.py`
- ThresholdFilter 图片硬链接：
  `D:\learning\IntelligentDepartment\CodesSet\Self\260707IsaacSIm\scripts\260730_01ThresholdFilter\threshold_filter\atomic_io.py`
