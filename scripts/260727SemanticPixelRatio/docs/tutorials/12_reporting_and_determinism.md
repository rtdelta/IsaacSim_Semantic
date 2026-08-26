# 12｜报告、异常状态与确定性

对应源码：[reporter.py](../../semantic_pixel_ratio/results/reporter.py)

## 1. 输出文件总览

```text
output_root/
├── manifest.json
├── counts_manifest.json
├── counts/
│   └── part-*.npz
├── counts_cache.npz
├── per_frame.csv
├── anomalies.csv
├── summary.csv
└── summary.json
```

理解顺序：

```text
先看 manifest 状态
→ 再看 summary
→ 需要逐帧时看 per_frame
→ 排错看 anomalies
→ 深度复算看 counts_cache/parts
```

## 2. per-frame 行数

每帧有：

```text
5 个单齿 target + 1 个 group = 6 行
```

N 帧：

```text
target_rows = 6N
```

行顺序是：

```text
frame 0 的五 target + group
frame 1 的五 target + group
...
```

字段：

| 字段 | 含义 |
|---|---|
| `frame_id` | 上游文件名中的 ID |
| `target` | 单标签名或 group name |
| `whole_pixels` | numerator count |
| `reference_pixels` | denominator count |
| `pixel_ratio` | whole/reference；无定义时空 |
| `status` | valid/reference_missing/ratio_over_one |

## 3. `_ratio` 的全部规则

```text
reference == 0
→ ratio=None
→ reference_missing

reference > 0 且 whole/reference > 1
→ 保留 ratio
→ ratio_over_one

其他
→ valid
```

`whole=0, reference=0` 仍是 `reference_missing`，不是 ratio 0。数学上的 `0/0` 无定义。

## 4. CSV 浮点格式

```python
format(value, ".12g")
```

表示最多约 12 位有效数字，并可能根据大小使用普通或科学计数法。

CSV 是展示和交换格式，不是保存原始精确有理数。可复算时应使用整数：

```text
whole_pixels / reference_pixels
```

不要从格式化 ratio 再反推计数。

## 5. group 如何生成

每帧从账本五列求和：

```text
whole_group = sum(whole_counts[frame,:])
reference_group = sum(reference_counts[frame,:])
```

group 不在 backend output 中单独保存，避免后端提供的 group 与五列不一致。

报告层再次检查 group 不超过 `pixels_per_frame`。

## 6. summary 指标

每个 target/group：

```text
frames
whole_pixels_total
reference_pixels_total
aggregate_ratio
valid_frame_count
zero_reference_frame_count
ratio_over_one_frame_count
mean_frame_ratio
median_frame_ratio
min_frame_ratio
max_frame_ratio
```

顶层：

```text
schema_version
status
backend
frames
target_rows
elapsed_seconds
frames_per_second
targets
```

这里的 `valid_frame_count` 实际含义是“ratio 有定义的帧数”，即 `reference>0`。它包含 status 为 `ratio_over_one` 的帧；不要把它误读成 `status=="valid"` 的数量。

## 7. aggregate ratio

```text
aggregate_ratio = Σwhole / Σreference
```

它不是：

```text
mean_frame_ratio = mean(whole_f/reference_f)
```

示例：

```text
frame A: 900/1000 = 0.9
frame B: 1/10     = 0.1
```

```text
mean_frame_ratio = (0.9+0.1)/2 = 0.5
aggregate_ratio  = 901/1010 ≈ 0.89208
```

第一帧拥有更多参考像素，所以 aggregate 更接近 0.9。

## 8. 零分母帧在 summary 中的影响

单帧 ratio 统计会排除 `None`：

```text
valid_ratios 只包含 reference > 0 的帧
```

但是 totals 不排除任何帧：

```text
whole_total 包含 reference=0 帧的 whole
reference_total 加 0
```

因此若出现：

```text
whole=10, reference=0
```

这帧会：

- 增加 zero_reference count；
- 不进入 mean/median/min/max；
- 增加 aggregate numerator；
- 可能使 aggregate ratio 上升或大于 1。

这是“先汇总所有整数，再相除”的严格定义。

## 9. median 为什么有价值

mean 对极端 ratio 很敏感。例如少数 reference 极小的帧可能产生很大的 ratio。

median 表示排序后的中间位置，更稳健地描述“典型帧”。它仍不替代 aggregate，因为两者的权重语义不同。

建议同时看：

```text
aggregate_ratio
mean_frame_ratio
median_frame_ratio
ratio_over_one_frame_count
zero_reference_frame_count
```

## 10. anomalies.csv

它复用 per-frame 相同字段，只保留：

```text
status != valid
```

包括：

- `reference_missing`；
- `ratio_over_one`。

它不是程序错误日志，而是数据结果中的异常/边界集合。pipeline 失败信息在 manifest 中。

## 11. JSON 与 CSV 的 null 表达

JSON：

```json
"aggregate_ratio": null
```

CSV：

```text
空字段
```

JSON 写出设置 `allow_nan=False`，因此代码若产生 NaN/Infinity 会失败，而不是写非标准值。

## 12. 账本验证

报告前 `_validate_ledger` 检查：

- ordinals 精确等于 `0...N-1`；
- frame IDs 无重复；
- single target counts 不超过每帧像素数。

注意 CountLedgerData dataclass 检查的是数组形状，reporter 检查的是业务内容。多层验证各守不同边界。

## 13. 为什么报告是确定的

固定条件：

1. frame order 来自 ordinal；
2. target order 来自配置 labels，再加 group；
3. counts 是整数；
4. group 在 CPU 按固定五列求和；
5. per-frame ratio 只有一次除法；
6. summary 用固定遍历顺序；
7. mean 使用 `math.fsum` 降低普通浮点连续相加误差；
8. JSON/CSV 从同一 ledger 生成。

GPU block 完成顺序、reader future 完成顺序、batch size 都不改变整数账本。

`elapsed_seconds`、`frames_per_second`、backend 字段会随运行环境变化，所以整个 summary 文件并非逐字节永远相同；**数据计数和由其导出的指标**才是确定性核心。

## 14. `build_rows/build_summary` 与 `write_reports`

测试使用：

```text
build_rows
build_summary
```

生产写出使用：

```text
write_reports
```

`write_reports` 为减少一次完整 `TargetRow` 大列表的峰值，按 target 构造 summary，并通过 generator 流式写 per-frame CSV。

当前 `_iter_rows` 会为 per-frame 和 anomalies 各遍历一次 ledger，报告阶段是 CPU 上的 O(N×6)，相对于读取图像通常很小。

## 15. `ratio_config` 当前为何被丢弃

`write_reports` 开头：

```python
del ratio_config
```

因为 `load_config` 已将 ratio 策略限制为唯一支持的固定值，reporter 无需分支。

这揭示一个设计事实：

```text
配置文件表达了策略意图
当前实现只支持其中一个策略
```

未来真要支持不同 numerator/zero policy，必须修改 reporter、fingerprint、测试和输出契约，不能只放宽 config 校验。

## 16. 手工审计一个结果

从 `per_frame.csv` 选一帧：

1. 确认有恰好 6 行；
2. 五个 target 顺序与 config 相同；
3. group whole 等于前五行 whole 和；
4. group reference 等于前五行 reference 和；
5. 分母非零时用整数重算 ratio；
6. 比值大于 1 时 status 正确；
7. 分母为 0 时 CSV ratio 为空；
8. 在 `anomalies.csv` 能找到非 valid 行。

从 `summary.json` 选一个 target：

1. 对 per-frame 的 whole/reference 分别求和；
2. 用 totals 重算 aggregate；
3. 统计 missing/over-one；
4. 对有效 ratio 求 mean/median；
5. 与 summary 对比。

## 17. 本章自检

1. 为什么每帧有 6 行？
2. `0/0` 在 CSV/JSON 中分别如何表示？
3. aggregate 和 mean frame ratio 为什么常不同？
4. reference=0, whole>0 的帧如何影响 aggregate？
5. anomalies 是程序错误日志吗？
6. 哪些 summary 字段天然会因运行环境改变？
