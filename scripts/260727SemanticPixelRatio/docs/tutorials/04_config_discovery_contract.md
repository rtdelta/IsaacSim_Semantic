# 04｜配置、输入发现与数据契约

对应源码：

- [config.py](../../semantic_pixel_ratio/config.py)
- [discovery.py](../../semantic_pixel_ratio/discovery.py)
- [semantic_io.py](../../semantic_pixel_ratio/semantic_io.py)
- [models.py](../../semantic_pixel_ratio/models.py)

## 1. 为什么配置要“严格”

科研或数据流水程序最危险的错误不是崩溃，而是悄悄使用错目录、错标签或错比值方向后仍生成看似正常的报告。

`load_config` 因此采用白名单：

```python
_reject_unknown(raw, allowed_fields, "config")
```

拼错字段不会被忽略。例如：

```json
"batch_frame": 128
```

不会悄悄使用默认 `batch_frames=128`，而会报告 unknown field。

## 2. 配置对象如何生成

配置 JSON 被转换为冻结 dataclass：

```text
RunConfig
├── InputsConfig
├── TargetsConfig
├── RatioConfig
├── ExecutionConfig
└── OutputConfig
```

这样 pipeline 使用：

```python
config.execution.batch_frames
```

而不是在各处直接读取易拼错的字典 key。

## 3. 完整字段参考

### 顶层

| 字段 | 约束 |
|---|---|
| `schema_version` | 必须等于 1 |
| `inputs` | 必须是对象 |
| `targets` | 必须是对象 |
| `ratio` | 必须是对象 |
| `pairing` | 必须是对象 |
| `execution` | 必须是对象 |
| `output` | 必须是对象 |

### `inputs`

| 字段 | 含义 |
|---|---|
| `whole_scene_semantic_dir` | 完整场景 semantic_id 目录 |
| `excavator_only_semantic_dir` | 参考场景 semantic_id 目录 |
| `semantic_mapping` | label 到 ID 的 mapping JSON |

两个目录必须存在，mapping 必须是文件。

### `targets`

| 字段 | 约束 |
|---|---|
| `labels` | 恰好五个非空且互不重复的字符串 |
| `group_name` | 非空，且不能与五个 label 同名 |

“恰好五个”不是可配置算法的一般能力，而是当前项目在模型形状、后端和报告中都写死的接口契约。

### `ratio`

当前只支持：

```json
{
  "numerator": "whole_scene",
  "denominator": "excavator_only",
  "zero_denominator": "null",
  "over_one": "keep_and_flag"
}
```

虽然这些值写进配置，它们目前不是自由策略开关。其他值会被拒绝。

### `pairing`

只支持：

```json
{"mode": "strict"}
```

没有“跳过缺帧继续跑”的宽松模式。

### `execution`

| 字段 | 默认/约束 | 实际作用 |
|---|---|---|
| `backend` | auto/numpy/torch_cuda/triton_cuda | 选择计数实现 |
| `batch_frames` | 默认 128，≥1 | 每个 LoadedBatch 帧数 |
| `reader_threads` | 默认 8，≥1 | 并行加载 frame pair 的线程数 |
| `ring_slots` | 默认 3，≥2 | 已加载 batch 的队列容量 |
| `cpu_workers` | 默认 min(CPU数,16)，≥1 | NumPy 计数线程数 |
| `device` | 默认 cuda | 传给 PyTorch 的设备字符串 |
| `on_frame_error` | 只支持 fail_fast | 任一帧错误即失败 |
| `verify_sample_frames` | 默认 8，≥0 | GPU 用 NumPy 复核的帧数 |

### `output`

| 字段 | 含义 |
|---|---|
| `root` | 输出目录 |
| `overwrite` | 删除已有输出后重做 |
| `resume` | 验证账本后从下一连续 ordinal 继续 |
| `write_counts_cache` | 是否额外写单文件 `counts_cache.npz` |

`overwrite=true` 与 `resume=true` 不能同时成立。

## 4. 相对路径的真实基准

`_resolve(base, value)` 中的 `base` 是：

```python
base = config_path.parent
```

例如：

```text
配置：D:/project/configs/run.json
值：  ../output/run001
结果：D:/project/output/run001
```

从哪个终端目录启动不影响配置内部相对路径。

配置文件参数本身 `--config relative/path.json` 则先按当前工作目录解析，因为 argparse 得到的是普通相对 `Path`，`load_config` 一开始调用 `path.resolve()`。

## 5. 输出目录隔离检查

代码禁止输出目录：

- 等于任一输入目录；
- 包含任一输入目录；
- 被任一输入目录包含。

例如下面都不允许：

```text
input  = /data/semantic
output = /data/semantic            # 相等
output = /data/semantic/results    # 输出在输入内
output = /data                     # 输出包含输入
```

这是为了防止 overwrite 删除输入，也防止 discovery 把输出文件与输入树混在一起。

当前这项包含关系检查只覆盖两个 semantic 输入目录，没有检查 `semantic_mapping` 文件或配置文件是否位于 output root 内。因此仍应人为保证 output 是专用目录，不要把 output root 设成 mapping/config 所在的上级目录；否则 `overwrite=true` 仍可能删掉这些文件。这是当前实现值得补强的安全边界。

## 6. mapping 文件契约

项目期待大致结构：

```json
{
  "dataset_dtype": "uint16",
  "classes": [
    {"label": "tooth_1_front_3DGS", "id": 1},
    {"label": "tooth_2_front_3DGS", "id": 2}
  ]
}
```

验证包括：

- 根必须是对象；
- `classes` 是非空数组；
- 每项是对象；
- label 是非空字符串；
- id 是非 bool 的整数；
- id 非负；
- label 不重复；
- id 不重复；
- `dataset_dtype` 若存在，必须是整数 dtype。

Python 中 `bool` 是 `int` 的子类，所以源码特意排除：

```python
isinstance(True, int) == True
```

否则 JSON 中的 `true` 可能被错误接受为 semantic ID 1。

## 7. label 如何解析为 ID

`resolve_target_ids` 按配置中 label 的顺序生成 tuple：

```text
(id_of_label_0, ..., id_of_label_4)
```

这个顺序贯穿：

- 后端输出最后一维；
- 账本 `whole_counts[:, target_index]`；
- summary target 顺序；
- CSV 中每帧的 target 顺序。

所以 label 顺序本身属于结果契约，不只是展示顺序。

## 8. 文件发现规则

`_discover` 使用 `os.scandir` 只扫描指定目录的直接子文件，只接受：

```text
semantic_id_*.npy
```

例如：

```text
semantic_id_0042.npy → frame_id "0042"
semantic_id_a7.npy   → frame_id "a7"
other.npy            → 忽略
subdir/...           → 不递归
```

前缀后没有内容：

```text
semantic_id_.npy
```

会报“没有 frame ID”。

## 9. strict pairing

分别得到：

```text
whole:     frame_id → path
reference: frame_id → path
```

然后计算集合差：

```text
missing_reference = whole IDs - reference IDs
missing_whole     = reference IDs - whole IDs
```

任一不为空，整个发现阶段失败。错误信息最多展示前 10 个缺失 ID，并说明还有多少个。

这比 `zip(sorted(whole), sorted(reference))` 安全得多。后者可能在缺一帧后把所有后续帧错位配对。

## 10. frame ID 排序

纯数字 ID 按整数排序：

```text
"1", "2", "10"
```

而不是字符串排序：

```text
"1", "10", "2"
```

非纯数字 ID 放在数字 ID 后，再按字符串排序。每个 pair 得到从 0 开始的连续 `ordinal`：

```text
FramePair(ordinal=0, frame_id="1", ...)
```

frame ID 是业务标识，ordinal 是内部确定顺序和断点位置。两者不能混为一谈。

## 11. dataset contract 如何建立

项目只用第一对文件建立全局契约：

```text
shape = (H,W)
dtype = integer dtype
```

首帧用 `mmap_mode="r"` 轻量检查：

- 必须二维；
- dtype 必须是整数；
- whole 与 reference shape 相同；
- whole 与 reference dtype 相同；
- mapping 若声明 dtype，必须匹配。

后续每帧在真正读取时由 `load_pair_arrays` 验证：

- 二维；
- shape 等于 contract；
- dtype 等于 contract。

这种设计避免为预检把全部 payload 读两遍，同时仍然保证所有帧一致。

## 12. 当前数据契约的隐含边界

以下事项值得知道：

1. 数据数组的像素值没有显式逐元素检查为非负；NumPy `bincount` 遇到负值会失败。
2. target ID 没有显式检查能否由 dataset dtype 表示。
3. mapping ID 会送入 GPU `int32`，正式 `uint16` 数据没有问题，但极大的整数 ID 不适合当前 GPU 后端。
4. discovery fingerprint 使用文件路径、大小和纳秒 mtime，不读取全部文件内容做 hash。
5. 第一帧只是确定契约，后续异常要到该 batch 真正加载时才发现。

这些不是当前正式 `uint16` 数据下的必然 bug，但属于扩展项目时应补强的边界。

## 13. 两层 fingerprint

### `fingerprint_pairs`

对每个 pair 按顺序加入：

```text
frame_id
whole path + size + mtime_ns
reference path + size + mtime_ns
```

得到 SHA-256。

### pipeline `_fingerprint`

再加入：

- pipeline version；
- 输入目录和 mapping 路径；
- pair fingerprint；
- mapping 文件内容 SHA-256；
- label、resolved ID、group name；
- ratio 固定策略；
- shape 和 dtype。

不加入：

- backend；
- batch size；
- reader/cpu 线程数；
- ring slots；
- GPU device；
- verify sample 数；
- 输出格式开关。

这是有意的：性能参数改变不应使已经得到的整数计数失效，也允许不同后端续接同一个账本，只要它们满足同一整数结果契约。

## 14. metadata fingerprint 的风险模型

文件大小和 mtime 能高效发现绝大多数正常修改，但不是强内容证明。若有人替换 payload 后故意保持相同大小和 mtime，缓存可能不失效。

选择取决于威胁模型：

- 常规工程流水：path + size + mtime 通常足够且快；
- 法证/不可抵赖要求：需内容 hash；
- 海量数据：内容 hash 会额外读取全部 payload，可能接近再跑一次 I/O。

规划文档建议在第一次正常读取 payload 时顺便计算 checksum，而不是为 hash 单独再读一遍。

## 15. 本章自检

1. 为什么 unknown field 要报错而不是忽略？
2. 配置内部相对路径相对于哪里？
3. strict pairing 比两个 sorted 列表直接 zip 安全在哪里？
4. frame ID 和 ordinal 分别解决什么问题？
5. 为什么 fingerprint 不包含 batch size 和 backend？
6. 当前 fingerprint 为什么不等于输入内容的密码学证明？
