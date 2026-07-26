# 07 `tooth_group_yolo` 模块详解

这个模块不重新扫描 semantic 数组。它消费上游 `SemanticBoxSet`，选择两个端部斗齿框，再生成一个集合框。

## 1. 数据流

```text
tooth_boxes.semantic_boxes
       │
       ▼
按本模块 min_pixels 过滤
       │
       ▼
选择两个端点
       │
       ▼
对两个端点框求外包矩形
       │
       ├─ YOLO class 0: tooth_group
       └─ artifact: tooth_group.group_box
```

本模块的 `process_frame()` 不使用 `FrameContext` 中的 semantic 或图片内容，只使用上游 artifact。

## 2. 启动时验证

`source_artifact` 必须看起来像：

```text
<module_id>.<artifact_name>
```

并且来源模块 ID 必须在本模块的 `depends_on` 中。例：

```json
"source_artifact": "tooth_boxes.semantic_boxes"
```

对应总配置：

```json
"depends_on": ["tooth_boxes"]
```

运行时读取后还会检查对象确实是 `SemanticBoxSet`。格式正确但 artifact 名写错，会在逐帧运行时失败。

## 3. 独立过滤阈值

```python
eligible = tuple(
    box for box in semantic_boxes.boxes
    if box.pixel_count >= min_pixels
)
```

阈值使用真实 semantic 像素数。它与上游阈值相互独立，因为上游 artifact 保留小框。

建议：

- 上下游都用于同一质量标准时，设成相同值；
- 集合框可以接受更小端点时，下游设小一些；
- 端点定位要求更严格时，下游设大一些。

调整后要检查 `missing_endpoints` 的变化，不要只看总帧数。

## 4. 选择器一：`semantic_labels`

配置：

```json
"endpoint_selector": {
  "type": "semantic_labels",
  "labels": ["tooth_1", "tooth_5"]
}
```

算法按 label 精确查两个框。两者都存在且达到本模块阈值才成功。

优点：

- 语义明确；
- 与相机旋转或画面左右顺序无关；
- 能稳定表示物理端部。

风险：

- 任一端部被遮挡或出画即失败；
- 上游标签命名必须稳定；
- 真实数据若使用 `tooth_01`，配置也必须使用 `tooth_01`。

这里“端点一”和“端点二”不要求按画面左右排序，因为最终外包框使用 min/max。

## 5. 选择器二：`image_extrema`

配置：

```json
"endpoint_selector": {
  "type": "image_extrema",
  "labels": [
    "tooth_1",
    "tooth_2",
    "tooth_3",
    "tooth_4",
    "tooth_5"
  ]
}
```

算法先从这些候选 label 中保留可见且合格的框，再选择：

```text
左端 = left 最小的框，center_x 用于平局
右端 = right 最大的框，center_x 用于平局
```

至少两个候选框才能成功。

优点：

- 不要求固定两个物理 label 可见；
- 相机角度变化时可按画面实际左右边界构造。

风险：

- 选的是“画面极值”，不一定是物理定义的第 1/第 5 齿；
- 候选列表中混入异常大框会污染集合框；
- 仍需至少两个候选可见。

## 6. `visible_extrema` 是失败回退，不是选择器

当主选择失败且：

```json
"missing_policy": "visible_extrema"
```

只要所有上游合格框中至少有两个，模块就从它们中选择画面左右极值。

注意范围：

- `image_extrema` 主选择只看 `endpoint_selector.labels`；
- `visible_extrema` 回退看所有上游 eligible 框。

如果上游 `semantic_yolo_boxes` targets 中还包含 `bucket_noteeth` 等非斗齿 label，那么它也可能进入回退范围。当前默认上游只发布配置的五个斗齿框，所以没有这个问题；扩展 targets 后必须重新评估。

## 7. 集合框计算

对端点框 A、B：

```text
left   = min(A.left,   B.left)
top    = min(A.top,    B.top)
right  = max(A.right,  B.right)
bottom = max(A.bottom, B.bottom)
```

例：

```text
A = [10, 20, 15, 40)
B = [30, 12, 39, 35)
```

得到：

```text
group = [10, 12, 39, 40)
```

### 一个重要边界

集合框只使用两个端点框，不计算所有中间斗齿框的总外包。

假设中间斗齿比两个端点更高：

```text
端点 top = 20, 18
中间齿 top = 5
```

集合框 top 仍是 18，不会自动扩到 5。当前算法表达的是“端点外包”，不是“全部斗齿外包”。如果业务要求覆盖所有可见齿的垂直极值，需要新增或修改算法，并补测试。

## 8. 四种缺失策略

主选择及可能的 `visible_extrema` 回退仍拿不到两个端点时：

| policy | `ModuleResult` | 文件行为 | 训练语义 |
| --- | --- | --- | --- |
| `exclude_frame` | `disposition="exclude"` | 不应存在该帧图片/标签 | 信息不足，样本不可信 |
| `empty_label` | 空 annotation | 写图片和空 `.txt` | 可信负样本 |
| `error` | 抛异常 | 写 errors，最终退出码 1 | 数据契约被破坏 |
| `visible_extrema` | 回退仍失败后 exclude | 同排除帧 | 尽力回退，仍不足则不用 |

默认 `exclude_frame` 最保守。对于“端部缺失只是遮挡”的数据，它通常比空标签更安全。

## 9. 排除与 overwrite 的交互

当某帧返回 `exclude`：

- `overwrite=true`：删除该模块目录中可能已有的同名 `.txt` 和图片；
- `overwrite=false`：不写新文件，也不删除已有文件。

所以如果输入数据或策略变化导致“以前输出、现在排除”，而你继续复用旧目录且
`overwrite=false`，陈旧文件可能保留。最安全的方法是每次业务配置变化使用新输出目录。

## 10. 返回的 artifact

成功时发布：

```text
<本模块id>.group_box
```

类型是 `PixelBox`。当前没有第三个模块消费它，但这是后续扩展方向，例如：

- 对集合框增加边距；
- 生成裁剪图；
- 统计集合区域；
- 构造更高层部件框。

缺失时不发布 `group_box`。若未来下游依赖它，要让下游能处理上游“计算成功但 artifact 缺失”的情况，或让本模块对缺失使用错误策略。

## 11. metrics

对成功返回 `ModuleResult` 的帧：

```text
成功得到集合框 -> missing_endpoints = 0
无法得到集合框，但策略返回 exclude/空标签 -> missing_endpoints = 1
```

`missing_policy="error"` 会直接抛异常，没有 `ModuleResult`，所以该帧只增加模块
`error`，不会把 `missing_endpoints=1` 聚合进 summary。

summary 中该 metric 是成功返回结果的累加值。通常：

```text
missing_endpoints
= excluded帧 + empty_label帧
```

使用 `visible_extrema` 且回退仍失败时也属于 excluded。具体仍要结合本模块状态统计判断。

## 12. 选择策略决策

```text
物理端部 label 稳定且必须是指定两齿？
  ├─ 是 -> semantic_labels
  └─ 否 -> 需要按画面可见极值？
           ├─ 是 -> image_extrema
           └─ 否 -> 需要新的业务算法

端点缺失是否应成为负样本？
  ├─ 明确是 -> empty_label
  └─ 不是 -> 是否必须视为数据错误？
             ├─ 是 -> error
             └─ 否 -> exclude_frame 或 visible_extrema
```

## 13. 建议测试矩阵

| 场景 | 预期 |
| --- | --- |
| 精确两端都在 | 正确外包框 |
| 左右画面顺序颠倒 | 精确标签仍得到正确 min/max |
| 一个端点缺失 | 按 policy 处理 |
| 端点像素数恰好等于阈值 | 保留 |
| 两端之外有更高的中间齿 | 当前框不扩到中间齿 |
| image_extrema 有三个候选 | 选画面左右极值 |
| visible_extrema 主选择失败、另有两框 | 回退成功 |
| artifact 类型错误 | 帧级 TypeError |

## 本章验收

1. 解释 `semantic_labels` 与 `image_extrema` 的业务差异。
2. 解释为什么 `visible_extrema` 可能选到 selector 列表外的框。
3. 手算两个端点框的集合框。
4. 解释当前集合框为什么可能不覆盖更高的中间斗齿。
5. 说明 `exclude_frame` 为什么通常不等价于负样本。

---

上一篇：[06_semantic_yolo_boxes模块详解.md](06_semantic_yolo_boxes模块详解.md)  
下一篇：[08_输出_断点续跑与错误处理.md](08_输出_断点续跑与错误处理.md)
