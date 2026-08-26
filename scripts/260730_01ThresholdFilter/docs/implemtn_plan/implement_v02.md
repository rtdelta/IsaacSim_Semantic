# 260730_01ThresholdFilter 实现方案 v02

## 文档信息

| 项目 | 内容 |
|---|---|
| 项目名称 | `260730_01ThresholdFilter` |
| 文档版本 | `v02` |
| 文档日期 | 2026-07-30 |
| 当前状态 | 实现前设计方案 |
| 核心主题 | 基于显露比例高速过滤单斗齿与斗齿集合的 YOLO 标注框 |

---

## 1. 项目背景

现有流程已经由两个独立项目产生以下结果：

1. `260724PostProcessChain`
   - 根据 full-scene semantic ID 生成单斗齿 YOLO 框；
   - 根据可用端部斗齿生成斗齿集合 YOLO 框；
   - 输出逐帧 YOLO 标注、对应 RGB 图片、`manifest.json` 和 `summary.json`。
2. `260727SemanticPixelRatio`
   - 对齐 full-scene 与 excavator-only 两套 semantic ID；
   - 统计五个斗齿在两套场景中的像素数；
   - 计算每个斗齿的显露比例；
   - 输出 `counts_cache.npz`、`per_frame.csv`、`manifest.json` 和统计报告。

本项目作为第三个独立后处理阶段，组合上述两类输出，根据显露比例删除不适合作为训练标注的 YOLO 框。

本项目不得重新渲染场景，不重新计算原始框，不修改上游结果，也不依赖 Isaac Sim 运行环境。

---

## 2. 核心目标

项目需要完成以下目标：

1. 根据阈值 `a` 过滤显露比例过低的单斗齿框；
2. 根据阈值 `b` 和低显露斗齿数量过滤斗齿集合框；
3. 同时支持当前全部单斗齿 class ID 为 `0` 的旧数据；
4. 支持未来五个斗齿使用独立 class ID 的新数据；
5. 所有输入、输出、规则、解析模式、异常策略和性能参数全部通过 JSON 配置文件读取；
6. 在保证严格校验、输出可审计和结果可复现的前提下尽可能提高运行速度；
7. 只生成新的过滤结果，不修改任何上游目录和文件。

---

## 3. 范围与非目标

### 3.1 本项目负责

- 读取 PostProcess full-scene YOLO 标注；
- 读取 PixelRatio 像素计数或比例结果；
- 对齐 frame ID；
- 识别每一个单斗齿 YOLO 行对应的物理斗齿；
- 计算或读取显露比例；
- 应用单斗齿过滤规则；
- 应用斗齿集合过滤规则；
- 输出新的 YOLO 数据集；
- 输出逐框决策、逐帧决策、异常和汇总报告；
- 记录输入指纹、配置指纹、耗时和吞吐量。

### 3.2 本项目不负责

- 启动 Isaac Sim；
- 修改 USD；
- 重新采集 RGB 或 semantic 数据；
- 重新读取 semantic NPY 计算边界框；
- 修改原始 YOLO 坐标；
- 生成新的斗齿集合框；
- 修复上游缺失的标注；
- 下载或迁移远端数据；
- 自动选择业务阈值 `a` 和 `b`。

---

## 4. 数据定义

对第 `f` 帧、第 `i` 个斗齿，定义：

```text
whole_pixels[f, i]
    = full-scene semantic 图中该斗齿的像素数

reference_pixels[f, i]
    = excavator-only semantic 图中该斗齿的像素数

ratio[f, i]
    = whole_pixels[f, i] / reference_pixels[f, i]
```

其中：

- `whole_scene` 是包含遮挡物的实际场景；
- `excavator_only` 是斗齿理论可见像素的参考场景；
- `ratio` 表示当前场景下斗齿相对于参考场景的显露比例。

当前五个目标 semantic label 为：

```text
tooth_1_front_3DGS
tooth_2_front_3DGS
tooth_3_front_3DGS
tooth_4_front_3DGS
tooth_5_front_3DGS
```

---

## 5. 业务过滤规则

### 5.1 规则一：单斗齿框

设单斗齿显露阈值为 `a`。

```text
ratio[f, i] < a
    → 删除第 f 帧中第 i 个斗齿已有的 YOLO 框

ratio[f, i] >= a
    → 保留第 f 帧中第 i 个斗齿已有的 YOLO 框
```

边界规定：

- 比例等于 `a` 时保留；
- 原始 YOLO 框不存在时，不创建新框；
- 原始框存在但比例不可计算时，交由异常策略处理；
- 不允许使用集合比例代替单斗齿比例。

### 5.2 规则二：斗齿集合框

设集合判断使用的单斗齿显露阈值为 `b`。

首先计算：

```text
low_count[f]
    = 第 f 帧五个斗齿中满足 ratio[f, i] < b 的斗齿数量
```

然后：

```text
low_count[f] >= 3
    → 删除第 f 帧已有的斗齿集合 YOLO 框

low_count[f] < 3
    → 保留第 f 帧已有的斗齿集合 YOLO 框
```

边界规定：

- 比例等于 `b` 时不计入 `low_count`；
- 判断必须统计全部五个斗齿；
- 即使某个斗齿没有单齿 YOLO 框，也必须使用它的比例参与集合判断；
- `per_frame.csv` 中的 `tooth_front_group` 聚合比例不参与规则二；
- 上游本来没有集合框时，本项目不得补造集合框。

### 5.3 数学表达

单斗齿删除掩码：

```text
single_drop[f, i] = ratio[f, i] < a
```

集合低显露数量：

```text
group_low_count[f] = Σ I(ratio[f, i] < b), i = 1..5
```

集合删除掩码：

```text
group_drop[f] = group_low_count[f] >= 3
```

其中 `I(condition)` 为条件成立时取 `1`，否则取 `0`。

---

## 6. 配置驱动原则

程序唯一允许的命令行任务参数是配置文件路径：

```powershell
python run_filter.py --config configs/output0727_filter.json
```

除配置文件路径外，不允许通过命令行覆盖以下内容：

- 输入目录和输入文件；
- 输出目录；
- ratio 输入格式；
- YOLO 身份解析模式；
- class ID 映射；
- 物理斗齿顺序；
- `a` 和 `b`；
- 集合删除所需的低显露斗齿数量；
- `reference_missing` 等异常策略；
- worker 数量；
- 最大并发任务数量；
- 图片输出方式；
- dry-run；
- overwrite；
- 验证级别；
- 报告级别。

所有相对路径均相对于主配置文件所在目录解析。

配置解析器必须拒绝未知字段，防止拼写错误被静默忽略。

---

## 7. 主配置文件设计

以下为完整配置结构示例。示例中的 `0.2` 和 `0.3` 仅用于展示配置格式，不代表最终业务阈值。

```json
{
  "schema_version": 1,

  "inputs": {
    "postprocess": {
      "output_root": "/root/gpufree-data/repositories/260724PostProcessChain/output/output0727_01_full_scene",
      "manifest": "manifest.json",
      "tooth_module_dir": "modules/tooth_boxes",
      "group_module_dir": "modules/tooth_group"
    },
    "pixel_ratio": {
      "output_root": "/root/gpufree-data/repositories/260727SemanticPixelRatio/output/output0727_01",
      "manifest": "manifest.json",
      "input_format": "counts_cache_npz",
      "counts_cache": "counts_cache.npz",
      "per_frame_csv": "per_frame.csv"
    }
  },

  "targets": {
    "labels_in_physical_order": [
      "tooth_1_front_3DGS",
      "tooth_2_front_3DGS",
      "tooth_3_front_3DGS",
      "tooth_4_front_3DGS",
      "tooth_5_front_3DGS"
    ],
    "group_name": "tooth_front_group"
  },

  "identity": {
    "mode": "legacy_zero_class_order",

    "legacy_zero_class_order": {
      "source_class_id": 0,
      "source_min_pixels": 10
    },

    "class_id_map": {
      "mapping": {
        "1": "tooth_1_front_3DGS",
        "2": "tooth_2_front_3DGS",
        "3": "tooth_3_front_3DGS",
        "4": "tooth_4_front_3DGS",
        "5": "tooth_5_front_3DGS"
      }
    }
  },

  "rules": {
    "single_tooth": {
      "minimum_visible_ratio": 0.2
    },
    "tooth_group": {
      "minimum_visible_ratio": 0.3,
      "minimum_low_teeth": 3
    }
  },

  "ratio_handling": {
    "reference_missing": "error",
    "empty_ratio": "error",
    "ratio_over_one": "use_raw"
  },

  "execution": {
    "workers": 8,
    "max_in_flight": 32,
    "on_error": "fail_fast",
    "dry_run": false,
    "staging_mode": "atomic_directory"
  },

  "performance": {
    "vectorized_rules": true,
    "directory_scan": "single_pass",
    "durability": "run_level",
    "verification_level": "sample",
    "verification_sample_frames": 32
  },

  "output": {
    "root": "/root/gpufree-data/repositories/260730_01ThresholdFilter/output/output0727_01_filtered",
    "overwrite": false,
    "image_mode": "hardlink_required",
    "keep_empty_label_files": true
  },

  "reporting": {
    "level": "full"
  }
}
```

### 7.1 必要配置约束

- `schema_version` 必须为 `1`；
- `targets.labels_in_physical_order` 必须恰好包含五个不重复字符串；
- `rules.single_tooth.minimum_visible_ratio` 必须位于 `[0, 1]`；
- `rules.tooth_group.minimum_visible_ratio` 必须位于 `[0, 1]`；
- `rules.tooth_group.minimum_low_teeth` 必须位于 `[1, 5]`；
- `execution.workers >= 1`；
- `execution.max_in_flight >= execution.workers`；
- `output.root` 不得等于、包含或被任一输入目录包含；
- `output.overwrite=false` 时，正式输出目录必须不存在或为空；
- `identity.mode` 必须为支持的解析模式之一；
- class ID 映射必须完整覆盖五个物理斗齿标签。

---

## 8. YOLO 斗齿身份解析

项目必须支持两种解析模式，并通过统一接口向后续规则提供：

```text
semantic_label → 原始 YOLO 标注行
```

### 8.1 模式一：`legacy_zero_class_order`

该模式用于当前所有单斗齿 YOLO 行 class ID 都为 `0` 的数据。

上游生成器按以下物理顺序遍历：

```text
tooth_1
tooth_2
tooth_3
tooth_4
tooth_5
```

但是，上游会跳过：

- semantic mask 完全不存在的斗齿；
- `whole_pixels < min_pixels` 的斗齿。

因此不能直接把第 `N` 行解释为 `tooth_N`。

解析步骤：

1. 从 ratio 计数结果中取得当前帧五个斗齿的 `whole_pixels`；
2. 按 `labels_in_physical_order` 遍历五个斗齿；
3. 保留满足 `whole_pixels >= source_min_pixels` 的斗齿；
4. 将保留下来的标签按原顺序与 YOLO 文件中的非空行逐一对应；
5. 校验实际 YOLO 行全部使用 `source_class_id`；
6. 校验推导出的标签数量与实际 YOLO 行数完全一致；
7. 数量不一致时禁止根据坐标位置猜测身份，必须报告错误。

示例：

```text
whole_pixels:
tooth_1 = 100
tooth_2 = 0
tooth_3 = 80
tooth_4 = 70
tooth_5 = 90
```

如果 YOLO 文件包含四行，则对应关系为：

```text
第 1 行 → tooth_1
第 2 行 → tooth_3
第 3 行 → tooth_4
第 4 行 → tooth_5
```

这里的“顺序”指 YOLO 文件的原始行序，不重新按 `x`、`y` 坐标排序。

### 8.2 模式二：`class_id_map`

该模式用于未来五个斗齿具有独立 class ID 的数据。

每一个 YOLO 行直接根据：

```text
class_id → semantic_label
```

进行身份解析。

配置可以支持：

```text
0 → tooth_1
1 → tooth_2
2 → tooth_3
3 → tooth_4
4 → tooth_5
```

也可以支持：

```text
1 → tooth_1
2 → tooth_2
3 → tooth_3
4 → tooth_4
5 → tooth_5
```

过滤器不得重新编号，只保留或删除原始 YOLO 行。

该模式必须检查：

- class ID 是否存在于配置映射；
- 映射是否完整覆盖五个斗齿；
- 一个 class ID 是否只映射到一个 semantic label；
- 一个 semantic label 是否只对应一个 class ID；
- 同一帧同一个斗齿是否出现多个框；
- 原始 `classes.txt` 是否与配置契约兼容。

### 8.3 模式选择原则

- 模式必须由配置文件明确指定；
- 不允许根据单帧中出现的 class ID 自动猜测；
- 单帧可能只剩一个斗齿框，因此单帧自动判断不可靠；
- 可以在 preflight 中根据整个数据集和 `classes.txt` 验证所选模式是否合理，但不能静默切换模式。

---

## 9. Ratio 输入后端

### 9.1 高速后端：`counts_cache_npz`

默认高速模式读取：

```text
counts_cache.npz
```

其中包含：

```text
frame_ids
whole_counts
reference_counts
```

预期形状：

```text
frame_ids:        [frames]
whole_counts:     [frames, 5]
reference_counts: [frames, 5]
```

目标标签顺序从 PixelRatio 的 `manifest.json` 读取并与本项目配置进行校验。

优点：

- 一次读取全部计数；
- 避免逐行解析 CSV；
- 便于 NumPy 向量化计算；
- legacy 模式可直接利用 `whole_counts` 推导已有框身份；
- 适合更大规模数据集。

### 9.2 兼容后端：`per_frame_csv`

CSV 后端读取：

```text
per_frame.csv
```

需要校验：

- 字段完整；
- `(frame_id, target)` 唯一；
- 每帧具有五个单斗齿记录；
- 数字字段合法；
- 空比例只允许与明确的异常状态同时出现；
- `tooth_front_group` 行只用于报告校验，不用于规则二。

### 9.3 两个后端的一致性

两个后端必须输出统一内部模型：

```text
RatioMatrix
```

并保证在同一数据集、同一配置下产生完全相同的过滤决策。

测试必须验证 NPZ 和 CSV 后端结果一致。

---

## 10. `reference_missing` 与异常比例

当：

```text
reference_pixels == 0
```

显露比例没有数学定义，必须标记为无效，而不能自动当作 `0` 或无穷大。

CSV 中可能表现为：

```csv
frame_id,target,whole_pixels,reference_pixels,pixel_ratio,status
0123,tooth_2_front_3DGS,0,0,,reference_missing
```

也可能出现不一致数据：

```csv
0123,tooth_2_front_3DGS,37,0,,reference_missing
```

默认配置：

```json
"reference_missing": "error"
```

支持预留策略：

- `error`：默认，终止运行；
- `keep`：保留相关已有框；
- `drop`：删除相关已有框；
- `quarantine`：不进入正式输出，写入隔离报告。

任何非默认策略都必须由配置明确指定。

对于：

```text
ratio > 1
```

默认：

```json
"ratio_over_one": "use_raw"
```

即保留原始比例并记录异常。由于 `a`、`b` 被限制在 `[0,1]`，该斗齿不会因显露比例过低而被删除。

---

## 11. 高性能总体方案

本项目的计算量很小。当前数据约为：

```text
1026 帧 × 5 个斗齿
```

阈值比较不是主要瓶颈，主要开销来自：

- 大量小型 YOLO 文本文件的读取和创建；
- 图片输出；
- 文件系统元数据操作；
- 逐文件持久化；
- 重复目录扫描；
- 不必要的全量输出复核。

推荐的高速组合为：

```text
counts_cache.npz
    +
NumPy 向量化规则计算
    +
单次目录扫描
    +
线程池并发小文件 I/O
    +
PNG 硬链接
    +
staging 目录整体提交
    +
报告集中写入
    +
抽样复核
```

---

## 12. 具体加速措施

### 12.1 比例和规则向量化

一次性生成：

```text
valid_ratio_mask[frames, 5]
ratio_matrix[frames, 5]
single_drop_mask[frames, 5]
group_low_count[frames]
group_drop_mask[frames]
legacy_eligible_mask[frames, 5]
```

计算关系：

```text
valid_ratio_mask = reference_counts > 0

ratio_matrix =
    whole_counts / reference_counts
    where valid_ratio_mask

single_drop_mask =
    ratio_matrix < a

group_low_count =
    sum(ratio_matrix < b, axis=1)

group_drop_mask =
    group_low_count >= minimum_low_teeth

legacy_eligible_mask =
    whole_counts >= source_min_pixels
```

逐帧工作线程不得重复计算比例。

### 12.2 不读取 semantic NPY

本项目不得重新读取：

```text
semantic_id_XXXX.npy
```

semantic 路径只用于 manifest 一致性检查。

### 12.3 不解码 PNG

图片只执行文件链接或复制操作：

- 不读取像素；
- 不检查图片尺寸；
- 不重新编码；
- 不通过图像库加载；
- 不生成缩略图。

### 12.4 图片输出模式

支持：

- `none`：不输出图片，速度最快；
- `hardlink_required`：推荐，同一文件系统内建立硬链接；
- `hardlink_or_copy`：硬链接失败后复制；
- `symlink`：符号链接；
- `copy`：完整复制。

高速默认值：

```json
"image_mode": "hardlink_required"
```

`hardlink_required` 失败时必须报告错误，不允许静默退化为大文件复制。

YOLO 文本不得使用硬链接，以免后续修改过滤结果时改变源标注。

### 12.5 单次目录扫描

使用 `os.scandir()` 对各源模块目录只扫描一次，建立：

```text
frame_id → tooth TXT path
frame_id → tooth image path
frame_id → group TXT path
frame_id → group image path
```

禁止在逐帧处理过程中重复：

- `glob`；
- 递归目录扫描；
- manifest 加载；
- classes 文件加载；
- 对同一路径多次执行存在性检查。

### 12.6 线程池并发 I/O

使用：

```text
ThreadPoolExecutor
```

不使用：

- `ProcessPoolExecutor`；
- GPU；
- 每帧子进程；
- 每帧独立 Python 解释器。

每个线程处理完整帧任务：

```text
读取单齿 YOLO
→ 解析身份
→ 应用单齿掩码
→ 读取集合 YOLO
→ 应用集合掩码
→ 写两个模块的结果
→ 创建图片链接
→ 返回 FrameResult
```

默认调优起点：

```text
workers = 8
max_in_flight = 32
```

最终必须在远端数据盘比较：

```text
workers = 1、4、8、16
```

选择实际最快且稳定的值。

### 12.7 有界任务提交

不得一次提交全部帧任务。

使用：

```text
max_in_flight
```

限制同时等待执行的任务数，避免：

- 同时打开过多文件；
- 线程池队列无界增长；
- 文件系统元数据压力过大；
- 内存中积累过多中间结果。

### 12.8 staging 目录整体提交

正式输出先写到与目标目录同级的临时目录：

```text
.<output-name>.staging-<run-id>/
```

处理成功后：

1. 写入最终报告；
2. 将 staging manifest 状态更新为 `completed`；
3. 执行抽样复核；
4. 将整个 staging 目录重命名为正式输出目录。

这样可以：

- 避免每个文件执行独立的高成本持久化；
- 避免中断后留下貌似完整的正式输出；
- 保证最终提交发生在同一文件系统内；
- 只进行一次正式目录切换。

第一版默认：

```json
"overwrite": false
```

每次运行使用新的输出目录。

### 12.9 报告集中写入

worker 不得直接写共享 CSV。

worker 仅返回：

```text
FrameResult
```

主线程在所有任务结束后：

1. 按 frame ordinal 排序；
2. 汇总计数；
3. 一次性写入 CSV；
4. 一次性写入 summary；
5. 一次性完成 manifest。

当前数据规模下，约六千条决策记录可安全保存在内存中。

### 12.10 避免全量输出重读

所有输出行在写入前已在内存中完成校验。

默认验证方式：

```json
"verification_level": "sample",
"verification_sample_frames": 32
```

支持：

- `none`：不重新读取输出；
- `sample`：抽样复核；
- `full`：全量重新读取。

默认推荐 `sample`。

---

## 13. 程序总体处理流程

### 阶段 1：配置加载

1. 读取主 JSON 配置；
2. 校验 schema version；
3. 拒绝未知字段；
4. 解析路径；
5. 校验阈值、模式和并发参数；
6. 检查输入输出路径隔离。

### 阶段 2：Preflight

1. 读取 PostProcess manifest；
2. 读取 PixelRatio manifest；
3. 检查两个 manifest 状态均为 `completed`；
4. 确认 PostProcess 使用 full-scene semantic；
5. 确认 PostProcess semantic 路径等于 PixelRatio 的 `whole_scene_semantic_dir`；
6. 确认 semantic mapping 一致；
7. 确认目标标签一致；
8. 确认帧数量和 frame ID 契约；
9. 检查所选身份解析模式；
10. 检查输出路径安全；
11. 计算输入指纹和配置指纹。

### 阶段 3：Ratio 加载

1. 根据配置选择 NPZ 或 CSV reader；
2. 加载五个斗齿计数；
3. 校验数组形状和数据类型；
4. 校验 frame ID 唯一、有序且完整；
5. 生成统一的 `RatioMatrix`。

### 阶段 4：规则预计算

1. 生成无效比例掩码；
2. 计算 ratio matrix；
3. 生成单斗齿删除掩码；
4. 生成集合低显露数量；
5. 生成集合删除掩码；
6. 生成 legacy 已有框推导掩码。

### 阶段 5：文件索引

1. 扫描单斗齿模块；
2. 扫描集合模块；
3. 建立 frame ID 到文件的映射；
4. 检查重复文件；
5. 检查单斗齿帧完整性；
6. 允许集合模块只包含部分帧。

### 阶段 6：并发逐帧处理

1. 有界提交帧任务；
2. 读取单斗齿标注；
3. 使用配置选择的 resolver 恢复斗齿身份；
4. 应用 `single_drop_mask`；
5. 读取已有集合框；
6. 应用 `group_drop_mask`；
7. 写 staging 标注；
8. 创建图片链接；
9. 返回 `FrameResult`。

### 阶段 7：汇总与报告

1. 汇总单斗齿原始、保留和删除数量；
2. 按斗齿类别汇总；
3. 汇总集合框；
4. 汇总异常；
5. 写入 decisions 和 frame summary；
6. 写入 summary；
7. 记录各阶段耗时。

### 阶段 8：验证与提交

1. 校验结果数量；
2. 执行配置指定的输出复核；
3. 写完成状态 manifest；
4. 将 staging 目录整体提交为正式输出目录。

---

## 14. 项目代码目录

```text
scripts/260730_01ThresholdFilter/
├── run_filter.py
├── README.md
├── requirements.txt
├── configs/
│   ├── example.json
│   └── output0727_filter.json
├── docs/
│   └── implemtn_plan/
│       └── implement_v02.md
├── threshold_filter/
│   ├── __init__.py
│   ├── config.py
│   ├── models.py
│   ├── atomic_io.py
│   ├── preflight.py
│   ├── ratio_reader.py
│   ├── file_index.py
│   ├── yolo_reader.py
│   ├── identity_resolver.py
│   ├── rules.py
│   ├── pipeline.py
│   ├── output_writer.py
│   └── reporter.py
└── tests/
    ├── __init__.py
    ├── helpers.py
    ├── test_config.py
    ├── test_preflight.py
    ├── test_ratio_reader.py
    ├── test_file_index.py
    ├── test_yolo_reader.py
    ├── test_identity_resolver.py
    ├── test_rules.py
    └── test_pipeline_integration.py
```

---

## 15. 各文件功能架构

### 15.1 `run_filter.py`

功能块：

- `parse_args()`
  - 只解析 `--config`；
  - 不接受业务参数覆盖。
- `main()`
  - 加载配置；
  - 调用 pipeline；
  - 输出最终状态、总耗时和输出目录；
  - 将配置错误、输入错误和运行错误转换为明确退出码。

不得包含：

- 阈值判断；
- YOLO 解析；
- 路径硬编码；
- 业务默认值散落。

### 15.2 `config.py`

配置数据类：

- `PostProcessInputConfig`
- `PixelRatioInputConfig`
- `TargetsConfig`
- `LegacyIdentityConfig`
- `ClassIdIdentityConfig`
- `IdentityConfig`
- `SingleToothRuleConfig`
- `ToothGroupRuleConfig`
- `RatioHandlingConfig`
- `ExecutionConfig`
- `PerformanceConfig`
- `OutputConfig`
- `ReportingConfig`
- `RunConfig`

功能块：

- JSON 加载；
- UTF-8 BOM 兼容；
- 未知字段拒绝；
- 相对路径解析；
- 枚举值校验；
- 数值范围校验；
- 标签与 class 映射校验；
- 输入输出隔离校验；
- 输出 resolved config；
- 生成配置指纹所需的规范化结构。

### 15.3 `models.py`

只定义数据结构，不执行文件 I/O。

主要模型：

- `RatioMatrix`
  - frame IDs；
  - 标签顺序；
  - whole counts；
  - reference counts；
  - ratio matrix；
  - valid mask。
- `YoloAnnotation`
  - class ID；
  - 归一化坐标；
  - 原始文本行；
  - 原始行号。
- `ResolvedToothAnnotation`
  - semantic label；
  - target index；
  - 原始 YOLO annotation。
- `ToothDecision`
  - frame ID；
  - semantic label；
  - ratio；
  - 阈值；
  - source state；
  - action；
  - reason。
- `GroupDecision`
  - frame ID；
  - 五个比例；
  - low count；
  - 阈值；
  - source state；
  - action；
  - reason。
- `FrameResult`
  - 当前帧处理结果；
  - 输出文本；
  - 统计；
  - 异常。
- `InputContract`
  - preflight 解析后的数据契约。
- `RunSummary`
  - 全局统计和耗时。

### 15.4 `atomic_io.py`

功能块：

- 创建同级 staging 目录；
- 生成唯一 run ID；
- 安全文本写入；
- JSON 写入；
- CSV 集中写入；
- staging 到正式目录的提交；
- 失败状态写入；
- 临时文件与失败 staging 的保留或清理策略。

性能要求：

- 不为每个小文件执行不必要的单独 `fsync`；
- run-level durability 由最终目录提交和 manifest 保证；
- 不允许 staging 位于另一个文件系统。

### 15.5 `preflight.py`

功能块：

- 加载两个 manifest；
- 检查上游完成状态；
- 检查 full-scene 输入；
- 检查 semantic 目录一致；
- 检查 mapping 一致；
- 检查标签顺序；
- 检查 frame count；
- 检查 ratio 后端所需文件；
- 检查单斗齿和集合模块目录；
- 检查 `classes.txt`；
- 验证所选 identity mode；
- 检查输出目录安全；
- 计算输入和配置指纹；
- 返回 `InputContract`。

### 15.6 `ratio_reader.py`

统一接口：

```text
RatioReader
├── NpzRatioReader
└── CsvRatioReader
```

`NpzRatioReader` 功能：

- 一次加载 NPZ；
- 校验数组字段；
- 校验 shape；
- 校验整数计数；
- 校验非负；
- 校验 frame ID；
- 根据 manifest 恢复标签顺序；
- 生成 ratio 和 valid mask。

`CsvRatioReader` 功能：

- 逐行读取 CSV；
- 校验表头；
- 校验唯一键；
- 校验每帧五个标签齐全；
- 解析空比例和状态；
- 生成与 NPZ 相同的 `RatioMatrix`。

### 15.7 `file_index.py`

功能块：

- 使用 `os.scandir()` 扫描目录；
- 提取 `rgb_XXXX` 中的 frame ID；
- 建立 TXT 和图片索引；
- 检查重复 frame ID；
- 检查未知文件模式；
- 检查单斗齿帧集合；
- 记录集合模块的已有帧子集；
- 返回不可变文件索引。

### 15.8 `yolo_reader.py`

功能块：

- 读取小型 YOLO TXT；
- 忽略纯空行；
- 校验每行五个字段；
- 解析 class ID；
- 解析坐标为有限浮点数；
- 校验中心位于 `[0,1]`；
- 校验宽高位于 `(0,1]`；
- 保留原始文本行；
- 集合标注最多允许一个框；
- 支持高速模式下的最小必要校验。

### 15.9 `identity_resolver.py`

统一接口：

```text
AnnotationIdentityResolver
├── LegacyZeroClassOrderResolver
└── ClassIdMapResolver
```

`LegacyZeroClassOrderResolver`：

- 校验所有源行 class ID；
- 读取当前帧 `legacy_eligible_mask`；
- 按物理标签顺序生成预期标签；
- 与源 YOLO 行逐一匹配；
- 检查数量一致；
- 返回统一 resolved annotation。

`ClassIdMapResolver`：

- 读取 class ID；
- 查找配置映射；
- 检查未知 class；
- 检查重复斗齿；
- 返回统一 resolved annotation。

factory：

- 根据 `identity.mode` 创建 resolver；
- 不允许自动切换模式。

### 15.10 `rules.py`

纯函数和 NumPy 规则计算，不进行文件 I/O。

功能块：

- `build_valid_ratio_mask()`；
- `build_ratio_matrix()`；
- `build_single_drop_mask()`；
- `build_group_low_counts()`；
- `build_group_drop_mask()`；
- `build_legacy_eligible_mask()`；
- `resolve_invalid_ratio_policy()`；
- 单帧决策对象构建。

必须明确使用严格小于：

```text
ratio < threshold
```

### 15.11 `pipeline.py`

功能块：

- `run_pipeline()`：总入口；
- `prepare_run()`：配置、preflight、ratio、规则和索引准备；
- `process_frame()`：单帧完整处理；
- 有界线程池调度；
- fail-fast 控制；
- dry-run 控制；
- 线程结果收集；
- 按 frame ordinal 确定性排序；
- 阶段耗时记录；
- 报告调用；
- 验证调用；
- staging 提交。

并发原则：

- 共享 ratio matrix 和决策掩码只读；
- worker 不写共享报告；
- worker 不修改源文件；
- 最终统计由主线程完成；
- 不同 worker 数量下输出必须完全一致。

### 15.12 `output_writer.py`

功能块：

- 准备模块输出目录；
- 复制 `classes.txt`；
- 写单斗齿标注；
- 写集合标注；
- 写空标签文件；
- 建立图片硬链接；
- 实现其他 image mode；
- dry-run 时禁止写模块输出；
- 返回写入统计；
- 不重新格式化保留的原始 YOLO 行。

安全要求：

- 不修改源 TXT；
- 不硬链接源 TXT；
- 不解码图片；
- 正式输出只由 staging 提交产生。

### 15.13 `reporter.py`

输出：

- `manifest.json`
- `summary.json`
- `decisions.csv`
- `frame_summary.csv`
- `anomalies.csv`

统计内容：

- 总帧数；
- 单斗齿原始框数；
- 单斗齿保留框数；
- 单斗齿删除框数；
- 每个斗齿分别统计；
- 集合框原始数量；
- 集合框保留数量；
- 集合框删除数量；
- 上游本来不存在的集合框数量；
- invalid ratio 数量；
- ratio over one 数量；
- 解析模式；
- `a`、`b`；
- minimum low teeth；
- 输入指纹；
- 配置指纹；
- worker 参数；
- 各阶段耗时；
- 总吞吐量。

---

## 16. 输出目录与语义

### 16.1 正式输出结构

```text
output_root/
├── manifest.json
├── summary.json
├── decisions.csv
├── frame_summary.csv
├── anomalies.csv
└── modules/
    ├── tooth_boxes/
    │   ├── classes.txt
    │   ├── rgb_0000.png
    │   └── rgb_0000.txt
    └── tooth_group/
        ├── classes.txt
        ├── rgb_0000.png
        └── rgb_0000.txt
```

### 16.2 单斗齿输出语义

对源单斗齿模块存在的每一帧：

- 至少一个框保留：写保留后的原始行；
- 所有框被删除：写空 `.txt`；
- 图片按 `image_mode` 处理；
- 没有源框的斗齿不生成框。

### 16.3 集合输出语义

- 源集合框存在且通过规则：保留原始行；
- 源集合框存在但被过滤：写空 `.txt`，保留对应图片；
- 源集合框原本不存在：保持不存在，不补造标注或模块帧；
- 不重新计算集合框坐标。

### 16.4 Dry-run

当：

```json
"dry_run": true
```

只执行：

- 配置校验；
- preflight；
- ratio 加载；
- 规则计算；
- YOLO 身份解析；
- 决策和统计；
- 报告输出。

不生成：

- `modules/tooth_boxes`；
- `modules/tooth_group`；
- 图片链接；
- 过滤后 YOLO TXT。

Dry-run 用于在正式运行前评估 `a` 和 `b` 会删除多少标注。

---

## 17. 报告设计

### 17.1 `decisions.csv`

单斗齿逐对象决策，建议字段：

```text
frame_id
semantic_label
target_index
source_present
source_class_id
source_line_number
whole_pixels
reference_pixels
pixel_ratio
ratio_status
threshold
action
reason
```

`action` 支持：

- `keep`
- `drop`
- `source_absent`
- `indeterminate`
- `quarantine`

### 17.2 `frame_summary.csv`

逐帧集合决策，建议字段：

```text
frame_id
tooth_1_ratio
tooth_2_ratio
tooth_3_ratio
tooth_4_ratio
tooth_5_ratio
group_threshold
low_count
minimum_low_teeth
source_group_present
group_action
reason
```

### 17.3 `anomalies.csv`

记录：

- reference missing；
- empty ratio；
- ratio over one；
- 未知 class；
- 重复 class；
- legacy 数量不匹配；
- 缺失文件；
- 输出失败；
- 抽样验证失败。

### 17.4 `summary.json`

包含：

- 完整运行统计；
- 输入输出路径；
- 解析模式；
- 阈值；
- 各类框数量；
- 异常数量；
- 各阶段性能；
- 配置和输入指纹；
- 运行是否完成。

### 17.5 `manifest.json`

状态生命周期：

```text
running
→ completed
```

或：

```text
running
→ failed
```

正式输出目录中只允许出现 `completed` manifest。

---

## 18. 错误处理

默认使用：

```json
"on_error": "fail_fast"
```

以下错误必须阻止正式输出提交：

- 配置字段错误；
- 输入目录不存在；
- manifest 状态不是 completed；
- 两个上游数据集不匹配；
- mapping 不一致；
- ratio frame ID 与 YOLO frame ID 不一致；
- NPZ shape 不正确；
- 非法计数；
- reference missing 且策略为 error；
- 未知 class；
- 同一斗齿重复框；
- legacy 推导数量与 YOLO 行数不一致；
- 非法 YOLO 坐标；
- staging 写入失败；
- 图片硬链接失败且配置为 hardlink required；
- 输出抽样验证失败。

发生错误时：

1. 不提交正式输出目录；
2. staging manifest 写为 failed；
3. 记录异常类型和 frame ID；
4. 根据配置决定保留或清理失败 staging；
5. 不修改任何源文件。

---

## 19. 确定性与可复现性

项目必须满足：

- frame ID 使用固定排序；
- label 使用配置固定顺序；
- NumPy 规则结果与 worker 数量无关；
- worker 返回结果由主线程按 frame ordinal 排序；
- CSV 输出顺序固定；
- JSON 使用稳定 key 排序；
- 保留 YOLO 行的文本内容不变化；
- 相同输入、配置和版本生成相同决策；
- manifest 记录所有影响结果的参数；
- 输入或配置指纹变化时不得误用旧输出。

---

## 20. 测试方案

### 20.1 配置测试

- 合法完整配置；
- 未知字段；
- 缺失字段；
- 非法相对路径；
- `a`、`b` 越界；
- minimum low teeth 越界；
- worker 参数非法；
- 输出目录与输入重叠；
- 非法 identity mode；
- class 映射不完整或重复。

### 20.2 Ratio reader 测试

- NPZ 正常加载；
- CSV 正常加载；
- NPZ 与 CSV 结果一致；
- frame ID 重复；
- shape 非 `[frames, 5]`；
- 负计数；
- reference 为零；
- ratio over one；
- 标签顺序与 manifest 不一致。

### 20.3 Legacy resolver 测试

- 五个框全部存在；
- 中间一个斗齿缺失；
- 多个斗齿缺失；
- 所有斗齿缺失；
- 实际行数少于推导数量；
- 实际行数多于推导数量；
- 某行 class ID 不为 configured source class。

### 20.4 Class ID resolver 测试

- class ID 为 `0～4`；
- class ID 为 `1～5`；
- 行顺序打乱；
- 单帧只存在部分类别；
- 未知 class；
- 重复 class；
- 配置映射缺失。

### 20.5 规则测试

- `ratio < a`；
- `ratio == a`；
- `ratio > a`；
- `ratio < b`；
- `ratio == b`；
- 低显露斗齿数量为 `0、1、2、3、4、5`；
- 恰好三个低于 `b` 时删除集合框；
- 一个比例无效时的各配置策略。

### 20.6 输出测试

- 保留原始 YOLO 文本；
- 部分行删除；
- 所有行删除后生成空文件；
- 集合框删除后生成空文件；
- 原始集合框不存在时不补造；
- image mode 为 none；
- hardlink required 成功；
- hardlink required 失败；
- staging 成功提交；
- staging 失败不提交；
- dry-run 不生成模块输出。

### 20.7 并发与集成测试

- worker 为 `1、4、8` 时结果一致；
- max in flight 不影响结果；
- fail-fast 正常终止；
- 报告统计与实际输出一致；
- 抽样验证正常；
- 源目录运行前后指纹不变；
- 完整端到端使用当前 1026 帧数据。

---

## 21. 性能基准与验收

### 21.1 测量阶段

必须分别记录：

- 配置加载耗时；
- preflight 耗时；
- NPZ 或 CSV 加载耗时；
- NumPy 规则计算耗时；
- 文件扫描耗时；
- YOLO 读取与过滤耗时；
- 图片链接耗时；
- 报告写入耗时；
- 抽样验证耗时；
- staging 提交耗时；
- 总耗时；
- frames per second。

### 21.2 基准组合

在同一远端机器、同一数据盘和同一数据集上比较：

```text
workers = 1
workers = 4
workers = 8
workers = 16
```

至少测试：

1. `counts_cache_npz + hardlink_required + sample verification`；
2. `counts_cache_npz + image none + no verification`；
3. `per_frame_csv + hardlink_required + full verification`；
4. 必要时测试不同 `max_in_flight`。

### 21.3 推荐验收目标

在当前约 1026 帧数据上：

- 不读取 semantic NPY；
- 不解码 PNG；
- fast-safe 模式不复制 PNG；
- 所有比例和阈值判断一次向量化完成；
- 不进行全量输出重读；
- warm-cache fast-safe 模式以约 `1000 frames/s` 为优化目标；
- 不同 worker 数量下输出决策必须完全一致；
- 性能优化不能降低数据契约校验和源数据安全性。

实际默认 worker 数量由远端数据盘基准结果决定，而不是仅根据 CPU 核心数决定。

---

## 22. 推荐运行档位

### 22.1 `fast_safe`

推荐默认生产配置：

```text
ratio input       = counts_cache_npz
workers           = 实测最优值，初始为 8
image mode        = hardlink_required
staging           = atomic_directory
verification      = sample
reporting         = full
```

兼顾速度、审计和安全。

### 22.2 `maximum_speed`

极限速度配置：

```text
ratio input       = counts_cache_npz
image mode        = none
verification      = none
reporting         = summary
```

适用于只需要快速生成过滤标签、下游直接复用源图片目录的场景。

### 22.3 `portable`

便携独立数据集配置：

```text
ratio input       = per_frame_csv
image mode        = copy
verification      = full
reporting         = full
```

最慢，但输出目录可以独立迁移。

---

## 23. 实施顺序

### 阶段 1：基础结构

1. 创建项目目录和 package；
2. 实现配置模型；
3. 实现核心数据模型；
4. 建立基础测试框架。

### 阶段 2：输入契约

1. 实现 manifest preflight；
2. 实现 NPZ reader；
3. 实现 CSV reader；
4. 实现单次文件索引；
5. 实现输入和配置指纹。

### 阶段 3：业务核心

1. 实现 YOLO reader；
2. 实现 legacy resolver；
3. 实现 class ID resolver；
4. 实现 NumPy 规则计算；
5. 完成单线程纯内存决策链。

### 阶段 4：安全输出

1. 实现 staging；
2. 实现单齿和集合输出；
3. 实现图片 hardlink；
4. 实现 empty label；
5. 实现报告；
6. 实现抽样验证；
7. 实现正式目录提交。

### 阶段 5：并发加速

1. 加入 ThreadPoolExecutor；
2. 加入 max in flight；
3. 保证确定性排序；
4. 比较 `1、4、8、16` worker；
5. 固化实测最快的默认配置。

### 阶段 6：端到端验收

1. 使用当前 output0727 数据；
2. legacy 模式完整运行；
3. 构造独立 class ID 测试数据；
4. 比较 NPZ 与 CSV 决策；
5. 验证源输出没有变化；
6. 验证报告和实际输出一致；
7. 记录最终性能基准。

---

## 24. 最终验收标准

### 24.1 功能验收

- 规则一正确使用 `ratio < a`；
- 规则二正确统计五个单斗齿；
- 恰好三个低于 `b` 时删除集合框；
- 不使用集合聚合比例代替规则二；
- legacy 全 class 0 数据正确解析；
- 独立 class ID 数据正确解析；
- 支持配置为 `0～4` 或 `1～5`；
- 不生成上游不存在的框；
- 不改变保留框的原始文本。

### 24.2 配置验收

- 所有业务参数来自 JSON；
- 命令行只接受配置文件路径；
- 未知配置字段会报错；
- resolved config 被写入 manifest；
- 配置指纹会影响输出复用判断。

### 24.3 安全验收

- 上游目录只读；
- 不硬链接 YOLO 文本；
- 不原地覆盖输入；
- 出错时不提交正式输出；
- 输出目录不与输入目录重叠；
- manifest 状态准确；
- 源输入运行前后保持不变。

### 24.4 性能验收

- 默认使用 NPZ 高速 reader；
- 使用 NumPy 向量化规则；
- 只扫描一次目录；
- 不读取 semantic NPY；
- 不解码 PNG；
- fast-safe 模式使用图片硬链接；
- 使用有界线程池；
- 报告集中写入；
- 默认仅抽样复核；
- 实际吞吐量达到远端基准设定目标。

### 24.5 质量验收

- 单元测试覆盖核心边界；
- NPZ 与 CSV 后端结果一致；
- 不同 worker 数量结果一致；
- 完整端到端测试通过；
- `README.md` 包含配置、运行和输出说明；
- 当前实现行为与本 v02 文档一致。

---

## 25. 结论

`260730_01ThresholdFilter` 将作为 `260724PostProcessChain` 与 `260727SemanticPixelRatio` 之后的独立过滤阶段。

最终方案同时满足：

- 单斗齿显露比例过滤；
- 五斗齿集合规则；
- 旧版全 class 0 顺序解析；
- 新版独立 class ID 解析；
- 完全配置驱动；
- 严格数据契约；
- 非破坏性输出；
- 可审计报告；
- NPZ 与 NumPy 向量化；
- 线程化小文件 I/O；
- 图片硬链接；
- staging 整体提交；
- 可测量、可调优的高性能实现。

实现阶段应严格按照本文档的模块边界、输入契约、错误策略和性能验收标准推进。
