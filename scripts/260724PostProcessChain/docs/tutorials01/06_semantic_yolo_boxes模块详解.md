# 06 `semantic_yolo_boxes` 模块详解

这个模块把 semantic 数组中的指定 label 转换为独立 YOLO 框，同时发布给下游使用的完整 `SemanticBoxSet`。

## 1. 输入、输出和职责

输入：

- `FrameContext.semantic`：二维整数数组；
- `RunContext.label_to_id`：mapping 解析结果；
- 本模块 JSON：YOLO 类别、semantic labels、像素阈值和输出目录。

输出：

- YOLO `YoloAnnotationSet`；
- artifact：`<module_id>.semantic_boxes`；
- metrics：`small_masks`、`missing_masks`。

模块不负责：

- 找文件和配对帧；
- 加载 RGB 像素；
- 写标签文件；
- 多进程调度；
- 处理下游集合框。

## 2. 配置怎样解析

加载模块配置时，把文本 label 解析成整数 ID：

```text
模块配置 semantic_labels: ["tooth_1", "tooth_2"]
                       │
                       ▼
mapping: {"tooth_1": 5, "tooth_2": 6}
                       │
                       ▼
ResolvedTarget.semantic_ids: (5, 6)
```

如果任何 label 不在 mapping 中，模块在处理第一帧之前就拒绝启动。这比运行到一半才发现缺 label 更安全。

`targets` 最终按连续的 `yolo_id` 排序，并生成：

```python
class_names = ("tooth", "bucket", ...)
labels_to_ids = {
    "tooth_1": 5,
    "tooth_2": 6,
    ...
}
```

## 3. 一次扫描提取所有目标像素

核心几何函数 `extract_semantic_boxes()` 的思路：

```python
target_mask = np.isin(semantic, target_ids)
all_y, all_x = np.nonzero(target_mask)
values = semantic[all_y, all_x]
```

它先找出所有目标 ID 的像素坐标，然后对每个 label/ID 筛选：

```python
selected = values == semantic_id
pixel_count = count_nonzero(selected)
x_values = all_x[selected]
y_values = all_y[selected]
```

最后得到：

```python
PixelBox(
    left=min(x_values),
    top=min(y_values),
    right=max(x_values) + 1,
    bottom=max(y_values) + 1,
)
```

没有任何目标像素时直接返回空 tuple。

## 4. 输出粒度：每个 label 一个框

假设：

```json
{
  "yolo_id": 0,
  "yolo_name": "tooth",
  "semantic_labels": ["tooth_1", "tooth_2", "tooth_3"]
}
```

如果三种 label 都可见且达到阈值，得到三条 YOLO detection：

```text
0 ...
0 ...
0 ...
```

三条都属于 `tooth` 类，但框分别来自三个 semantic label。

不要误解为：

- 每个像素实例一个框；
- 三个 label 合并成一个框；
- 一个 label 的多个连通区域拆成多个框。

当前精确语义是“每个配置 semantic label 的全图外包框”。

## 5. artifact 与 YOLO 输出的关键差异

模块先对所有目标 label 构造 `SemanticBoxSet`，然后才应用 `min_pixels` 生成 YOLO detections。

因此：

```text
pixel_count = 7
上游 min_pixels = 10

SemanticBoxSet：保留
上游 YOLO：过滤
```

这样下游可以用自己的阈值：

```text
下游 min_pixels = 5
```

同一个 7 像素框仍可被下游用于端点选择。

对应设计在测试
`test_keeps_small_box_in_artifact_but_not_yolo_output` 中被明确验证。

## 6. 逐 target 生成 detection

模块遍历每个 target，再遍历其 labels：

```text
该 label 没有像素
  -> missing_masks += 1
  -> 不产生 detection

有像素，但 pixel_count < min_pixels
  -> small_masks += 1
  -> 不产生 detection

有像素，且达到阈值
  -> 产生 target.yolo_id / target.yolo_name 的 detection
```

无论最终 detections 是否为空，模块都返回：

```python
artifacts={"semantic_boxes": semantic_boxes}
```

如果所有目标都缺失，annotation 是空 `YoloAnnotationSet`，所以会写一份空标签，而不是排除或报错。

## 7. metrics 怎样解读

`small_masks`：

- 目标 label 出现；
- 但真实目标像素数小于阈值；
- 是 mask 像素数，不是 bbox 面积。

`missing_masks`：

- 配置中的目标 label 在这一帧完全没有像素。

summary 中的数值是所有已处理帧的累加。例：

```json
"tooth_boxes": {
  "written": 100,
  "boxes": 470,
  "small_masks": 8,
  "missing_masks": 22
}
```

若每帧期望 5 齿，100 帧最多 500 个框；`470 + 8 + 22 = 500` 时数据行为完全可解释。

## 8. 多类别配置

可以让一个模块同时输出多个 YOLO class：

```json
{
  "schema_version": 1,
  "output": {
    "directory": "modules/parts",
    "layout": "flat_yolo"
  },
  "min_pixels": 10,
  "targets": [
    {
      "yolo_id": 0,
      "yolo_name": "tooth",
      "semantic_labels": ["tooth_1", "tooth_2", "tooth_3", "tooth_4", "tooth_5"]
    },
    {
      "yolo_id": 1,
      "yolo_name": "bucket",
      "semantic_labels": ["bucket_noteeth"]
    }
  ]
}
```

输出 `classes.txt`：

```text
tooth
bucket
```

每个 semantic label 只能在整个 targets 数组中出现一次，防止同一 mask 被重复分配给多个 YOLO 类别。

## 9. 边界行为

### 恰好等于阈值

判断条件是：

```python
pixel_count < min_pixels
```

所以等于阈值会保留。

### 标签存在，但该帧不可见

这是正常缺失，记 `missing_masks`，不报错。

### label 分成多个岛

所有岛合成一个大外包框。若这种情况频繁出现，应先判断：

- 上游是否把多个物理实例错误赋成同一 semantic label；
- 是否真正需要连通域模块；
- 是否应改为实例 ID 数据。

### mapping 中有目标，数组从不出现该 ID

配置仍能启动，但每帧都会累加 `missing_masks`。这通常是上游标签、遮挡或所选采集场景问题。

### 背景或 unknown

只有 targets 中的 label/ID 被扫描。mapping 的 background/unknown 元数据当前不参与本模块。

## 10. 算法复杂度与性能

主要成本：

- `np.isin` 扫描整张 semantic 图；
- `np.nonzero` 创建目标像素坐标；
- 每个配置 label 再对目标像素值做比较。

粗略理解：

```text
整图扫描成本 + 目标 label 数 × 目标像素筛选成本
```

比为每个 label 重复扫描整张图更经济，但当目标像素很多、label 很多时仍会产生临时数组。性能优化前应先用真实数据测量，不要把 `workers` 盲目设为 CPU 核数。

## 11. 建议的单元测试

新增或修改算法时至少覆盖：

1. 目标像素得到正确半开框；
2. 多个 label 映射到同一 YOLO 类；
3. 缺失 label 增加 `missing_masks`；
4. 小 mask 保留 artifact 但过滤 annotation；
5. 等于阈值时保留；
6. 同 ID 多个岛得到一个外包框；
7. mapping 缺 label 在加载配置时失败。

## 本章验收

1. 解释 ResolvedTarget 为什么同时保存 labels 和 IDs。
2. 解释 `pixel_count` 与框面积为何不同。
3. 解释小 mask 为什么仍可能影响下游集合框。
4. 解释五个 label 映射同一 YOLO class 后 `classes.txt` 为什么只有一行。
5. 判断当前算法能否正确处理同一 label 的两个物理实例，并说明原因。

---

上一篇：[05_执行引擎与源码主线.md](05_执行引擎与源码主线.md)  
下一篇：[07_tooth_group_yolo模块详解.md](07_tooth_group_yolo模块详解.md)
