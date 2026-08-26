# `04_semantic_mapping.example.json` 参数说明

该文件将 Isaac/Replicator 每帧返回的原始语义标签映射为稳定的数据集类别 ID，并为每个 ID 定义可视化颜色。字段说明严格按照 JSON 顺序排列。

## 顶层字段

| 顺序 | JSON 路径 | 类型 | 必填 | 含义与填写要求 |
|---:|---|---|---:|---|
| 1 | `schema_version` | 整数 | 建议 | 映射文件的文档版本，示例为 `1`。当前加载器主要读取 `classes`。 |
| 2 | `classes` | 非空对象数组 | 是 | 稳定类别表。至少包含一个类别；通常把 ID `0` 留给背景/未知标签。 |

## `classes[]` 每个类别

每个对象按照以下顺序填写：

| 顺序 | 字段 | 类型 | 必填 | 含义与填写要求 |
|---:|---|---|---:|---|
| 1 | `id` | 非负整数 | 是 | 数据集稳定类别 ID，整个文件中不能重复。类别最大 ID 不超过 65535 时输出使用 `uint16`。 |
| 2 | `name` | 非空字符串 | 是 | 类别标准名称，同时自动作为一个匹配别名。名称比较不区分大小写。也可以用字段名 `label` 代替，但推荐统一使用 `name`。 |
| 3 | `color` | 三个整数的数组 | 是 | `[R, G, B]`，每项范围 `0..255`。用于生成 `semantic_color.png`。不同类别应选择明显不同的颜色。 |
| 4 | `aliases` | 字符串数组 | 否 | Stage/Replicator 可能返回的原始 `class` 标签。多个 USD 标签可合并到一个稳定类别。匹配不区分大小写。 |

## 示例类别的含义

| 稳定 ID | 标准名称 | 示例别名用途 |
|---:|---|---|
| 0 | `BACKGROUND` | 把 Replicator 的 `UNLABELLED` 也归入背景。未匹配标签默认同样写为 ID 0。 |
| 1 | `excavator_body` | 将驾驶室和履带标签合并为“挖掘机主体”。 |
| 2 | `excavator_work_equipment` | 将大臂、小臂和无齿铲斗合并成工作装置。 |
| 3 | `bucket_tooth` | 将多个前斗齿标签合并为一个斗齿类别。 |

## 应如何填写

1. 先从 Stage 的 Semantics 或一次 `semantic_segmentation.info.json` 中收集真实标签。
2. 决定“一个 USD 标签一个类别”还是“多个零件合并为一个类别”。
3. 为每个稳定类别分配永久不变的 ID；已有数据集发布后不要重排 ID。
4. 把所有可能的原始拼写放入 `aliases`。
5. 颜色只用于查看，训练真值以 `semantic_id.npy` 为准。

主配置通过以下字段引用：

```json
"scene": {
  "mapping": "04_semantic_mapping.example.json"
}
```

如果 `scene.mapping` 为 `null`，文件系统 sink 不会使用这张表生成稳定 ID 和彩色语义图。
