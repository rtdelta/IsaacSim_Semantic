# 260731PostProcessChain_v02 统一后处理项目实现方案 v01

## 1. 文档信息

| 项目 | 内容 |
|---|---|
| 项目名称 | `260731PostProcessChain_v02` |
| 文档名称 | 统一后处理项目实现方案 |
| 文档版本 | `v01` |
| 文档日期 | 2026-07-31 |
| 目标 | 将 PostProcessChain、SemanticPixelRatio 和 ThresholdFilter 的逻辑整合为一个边界清晰、高速并行、配置驱动的统一后处理项目 |

本文档是新项目的实现基线。新项目不复用或直接导入三个旧项目的代码文件，只参考旧链路已经验证过的业务逻辑和输出结果。

---

## 2. 已确认的总体约束

### 2.1 不修改图像

统一项目必须遵守：

- 不旋转 RGB 图像；
- 不旋转 semantic ID 数组；
- 不缩放、裁剪或重新编码图像；
- 不执行相机位姿变换；
- 不转换到仿真坐标系或其他规范坐标系；
- 所有统计均基于输入图像原始像素坐标；
- 所有最终 YOLO 坐标均与原始 `full_scene RGB` 对齐。

实际相机旋转 90°只影响碰撞模型框中“长度轴”和“宽度轴”的业务解释，不触发任何图像或坐标变换。

### 2.2 主流水线与子模块分离

主流水线只负责：

- 配置加载；
- 输入预检；
- 帧发现和严格配对；
- 模块依赖顺序；
- 并发任务调度；
- 缓存复用判断；
- staging 输出和最终提交；
- 汇总所有模块结果。

所有业务计算放入职责单一的子模块。子模块不得自行重新扫描输入目录、重复读取同一帧数据或直接访问完整全局配置。

### 2.3 统一 JSON，但配置边界清晰

项目使用一个主 JSON 控制完整流程。JSON 顶层区分：

```text
pipeline   主流程行为
inputs     输入数据
targets    类别与语义契约
modules    各业务子模块配置
execution  并发与性能
cache      缓存与指纹
output     输出位置和文件策略
reporting  报告级别
```

主流水线只读取主流程配置；每个业务子模块只接收属于自己的强类型子配置。

### 2.4 最终 dataset 三目录并列

最终数据集中：

- RGB 只产出一份；
- 单齿框标签单独一个目录；
- 斗齿碰撞模型框标签单独一个目录；
- 两种标签目录均不重复存放 RGB。

---

## 3. 项目目标

统一项目需要完成：

1. 严格配对 full-scene RGB、full-scene semantic 和 excavator-only semantic；
2. 每帧只读取一次两套 semantic；
3. 一次提取五颗斗齿的像素数、轴对齐框和参考旋转几何；
4. 计算逐齿显露比例 `V`；
5. 计算逐齿填充与方向指标 `C、Theta`，并从最终 YOLO 源框计算 `HWR`；
6. 生成 full-scene 单齿候选框；
7. 使用 `a、c、d` 过滤单齿框；
8. 使用 `b` 和姿态多数规则判断斗齿碰撞模型框；
9. 使用 full-scene 和 excavator-only 的混合边界生成碰撞模型框；
10. 输出一份 RGB 和两套并列标签；
11. 输出完整特征、决策、异常和汇总报告；
12. 支持缓存，使调整阈值时不必重新读取 semantic；
13. 在不牺牲确定性和可审计性的前提下尽可能使用向量化和并行处理。

---

## 4. 非目标

新项目不负责：

- 启动 Isaac Sim；
- 修改 USD；
- 重新渲染场景；
- 修改 RGB 内容；
- 对图像执行旋转、缩放或裁剪；
- 计算相机外参或执行相机位姿变换；
- 自动猜测相机旋转方向；
- 自动选择正式业务阈值 `a、b、c、d`；
- 直接导入三个旧项目中的 Python 文件；
- 在单齿和碰撞模型标签目录中重复保存 RGB。

---

## 5. 核心输入

### 5.1 必要输入

```text
full_scene RGB 目录
full_scene semantic ID 目录
excavator_only semantic ID 目录
semantic_mapping.json
```

示例：

```text
input_root/
├── full_scene_rgb/
│   ├── rgb_0000.png
│   └── rgb_0001.png
├── full_scene_semantic/
│   ├── semantic_id_0000.npy
│   └── semantic_id_0001.npy
├── excavator_only_semantic/
│   ├── semantic_id_0000.npy
│   └── semantic_id_0001.npy
└── semantic_mapping.json
```

### 5.2 不要求 excavator-only RGB

`excavator_only RGB` 不是必要输入，因为：

- `C、Theta` 只依赖参考 semantic；`HWR` 来自 full-scene YOLO 源框；
- 最终数据集只使用 full-scene RGB；
- semantic 数组形状可以用于检查图像尺寸。

后续如果需要可视化调试，可以把 excavator-only RGB 作为可选输入，但不得使其成为核心流程依赖。

### 5.3 目标斗齿

系统固定处理五颗物理斗齿：

```text
class_id 0 -> teeth_01_front_3DGS
class_id 1 -> teeth_02_front_3DGS
class_id 2 -> teeth_03_front_3DGS
class_id 3 -> teeth_04_front_3DGS
class_id 4 -> teeth_05_front_3DGS
```

所有逐齿矩阵固定使用形状：

```text
[frames, 5]
```

不得因某帧只有四个或更少单齿候选框而缩减统计基数。

---

## 6. 核心输出

### 6.1 最终 dataset

```text
output_root/
└── dataset/
    ├── rgb/
    │   ├── rgb_0000.png
    │   └── rgb_0001.png
    ├── tooth_boxes/
    │   ├── classes.txt
    │   ├── rgb_0000.txt
    │   └── rgb_0001.txt
    └── tooth_collision_model/
        ├── classes.txt
        ├── rgb_0000.txt
        └── rgb_0001.txt
```

输出规则：

- `dataset/rgb` 只包含一份 full-scene RGB；
- `dataset/tooth_boxes` 只包含单齿 YOLO 标签；
- `dataset/tooth_collision_model` 只包含碰撞模型 YOLO 标签；
- 标签文件名必须与 RGB 文件名严格对应；
- 当某类框全部被删除时，根据 `keep_empty_label_files` 决定是否保留空标签；
- `classes.txt` 分别写入对应数据集的类别定义。

### 6.2 完整输出目录

```text
output_root/
├── manifest.json
├── resolved_config.json
├── cache/
│   ├── features_cache.npz
│   └── cache_manifest.json
├── reports/
│   ├── tooth_features.csv
│   ├── tooth_decisions.csv
│   ├── collision_decisions.csv
│   ├── frame_summary.csv
│   ├── anomalies.csv
│   └── summary.json
└── dataset/
    ├── rgb/
    ├── tooth_boxes/
    └── tooth_collision_model/
```

---

## 7. 总体架构

```text
MainPipeline
    |
    +-- Preflight
    +-- FrameDiscovery
    +-- FrameLoader
    +-- ParallelExecutor
    |
    +-- SemanticFeatureModule
    |       |
    |       +-- VisibilityRatioModule
    |       +-- PoseMetricModule
    |       +-- SingleToothBoxModule
    |
    +-- ThresholdRuleModule
    +-- CollisionBoxModule
    |
    +-- FeatureCache
    +-- DatasetWriter
    +-- Reporter
```

模块依赖关系：

```text
SemanticFeatureModule
    -> VisibilityRatioModule
    -> PoseMetricModule
    -> SingleToothBoxModule

VisibilityRatioModule
PoseMetricModule
SingleToothBoxModule
    -> ThresholdRuleModule

SemanticFeatureModule
ThresholdRuleModule
    -> CollisionBoxModule

ThresholdRuleModule
CollisionBoxModule
    -> DatasetWriter
    -> Reporter
```

---

## 8. 主流水线职责

`MainPipeline` 负责：

1. 读取统一 JSON；
2. 拒绝未知配置字段；
3. 将 JSON 拆分成强类型主配置和子模块配置；
4. 执行 Preflight；
5. 建立严格的帧任务索引；
6. 计算 Analysis 指纹；
7. 判断是否允许复用特征缓存；
8. 建立有界并发执行器；
9. 为每帧只加载一次 full/reference semantic；
10. 按依赖顺序调用子模块；
11. 将每帧小型结果写入预分配特征矩阵；
12. 批量向量化应用规则；
13. 在 staging 中写 dataset 和报告；
14. 抽样或完整验证输出；
15. 成功后原子提交正式输出目录。

主流水线不得包含具体业务公式。业务计算必须由子模块提供。

---

## 9. 帧任务和共享上下文

### 9.1 UnifiedFrameTask

```text
UnifiedFrameTask
├── ordinal
├── frame_id
├── full_rgb_path
├── full_semantic_path
└── reference_semantic_path
```

### 9.2 FrameContext

每个 worker 加载一帧后创建：

```text
FrameContext
├── task
├── full_semantic
├── reference_semantic
├── image_width
└── image_height
```

两套 semantic 只允许由 `FrameLoader` 加载一次。各子模块通过共享的 `FrameContext` 读取数组，不得自行重新执行 `np.load()`。

### 9.3 ArtifactStore

模块之间通过帧内 `ArtifactStore` 传递强类型结果，例如：

```text
semantic_features.full
semantic_features.reference
visibility_ratio.values
pose_metrics.values
single_tooth_boxes.candidates
threshold_rules.decisions
collision_box.result
```

ArtifactStore 只存在于当前帧任务内，不作为全局共享可变状态。

---

## 10. 子模块职责与契约

### 10.1 SemanticFeatureModule

输入：

```text
full_semantic
reference_semantic
五个目标 semantic ID
```

输出：

```text
W、R
full axis boxes
reference axis boxes
full geometry valid
reference geometry valid
reference target coordinates
```

职责：

- 一次性找出五颗斗齿目标像素；
- 统计逐齿像素数；
- 计算逐齿轴对齐半开像素框；
- 为 PoseMetricModule 提供参考轮廓坐标。

不负责：

- 阈值判断；
- 最终 YOLO 生成；
- 写文件；
- 读取 RGB 内容。

### 10.2 VisibilityRatioModule

输入：

```text
W、R
```

输出：

```text
V
ratio_status
```

规则：

```text
R > 0：
    V = W / R

R == 0：
    V = -1
    ratio_status = reference_missing
```

当 `V > 1` 时保留原始数值，并设置：

```text
ratio_status = ratio_over_one
```

`V=-1` 是哨兵值，不参与正常均值、中位数和分布统计。

### 10.3 PoseMetricModule

输入：

```text
excavator_only 中每颗斗齿的参考轮廓坐标
R
```

输出：

```text
C
Theta
reference_pose_status
```

定义：

```text
C = reference_pixels / oriented_box_area
Theta = long_side_angle
```

约束：

```text
Theta 位于 [0, 180)
```

无有效参考轮廓时：

```text
C = -1
Theta = NaN
reference_pose_status = reference_missing
```

本模块只计算填充比例和旋转方向，不旋转图像或 semantic。旋转框长短边比例不再参与过滤。

### 10.4 SingleToothBoxModule

输入：

```text
full axis boxes
W
minimum_pixels
```

输出：

```text
候选单齿框
source_box_exists
```

候选框存在条件：

```text
source_box_exists[f, i]
    = W[f, i] >= minimum_pixels
      且 full axis box 有效
```

本模块只生成候选框，不应用 `a、c、d`。该 full-scene 轴对齐框同时是最终 YOLO 源框和 `HWR` 的计算来源。

### 10.5 ThresholdRuleModule

输入：

```text
V、C、full axis boxes
source_box_exists
a、b、c、d
两个数量阈值
```

输出：

```text
single_keep
single_drop
occlusion_bad
pose_bad
occlusion_bad_count
pose_bad_count
collision_keep
collision_drop
reason_codes
height_width_ratios
```

高宽比 `HWR` 使用最终 YOLO 源框的像素尺寸计算。默认模式为 `x_over_y`：

```text
x_length = right - left
y_length = bottom - top

x_over_y: HWR = x_length / y_length
y_over_x: HWR = y_length / x_length
```

不得直接用 YOLO 归一化字段相除，因为 x、y 分别使用图像宽度和高度归一化。

单齿规则：

```text
single_keep[f, i]
    = source_box_exists[f, i]
      AND V[f, i] >= a
      AND C[f, i] >= c
      AND HWR[f, i] >= d
```

碰撞模型遮挡规则：

```text
occlusion_bad_count[f]
    = SUM(I(V[f, i] < b)), i = 1..5
```

碰撞模型姿态规则：

```text
pose_bad_count[f]
    = SUM(I(C[f, i] < c OR HWR[f, i] < d)), i = 1..5
```

碰撞模型最终规则：

```text
collision_keep[f]
    = occlusion_bad_count[f] < 3
      AND pose_bad_count[f] < 3
```

所有统计固定遍历五颗物理斗齿，不得以当前候选框数量为基数。

### 10.6 CollisionBoxModule

输入：

```text
full_scene 五齿轴对齐框
excavator_only 五齿轴对齐框
full/reference geometry valid
collision_keep
length_axis
```

输出：

```text
碰撞模型像素框
mixed_geometry_valid
geometry_reason
```

本模块不旋转图像、不转换坐标系，只在当前图像原始 `x/y` 坐标中选择边界来源。

当：

```text
length_axis = y
```

规则为：

```text
top、bottom  <- full_scene 五齿有效框并集
left、right  <- excavator_only 五齿有效框并集
```

当：

```text
length_axis = x
```

规则为：

```text
left、right <- full_scene 五齿有效框并集
top、bottom <- excavator_only 五齿有效框并集
```

生成后校验：

- `left >= 0`；
- `top >= 0`；
- `right > left`；
- `bottom > top`；
- `right <= image_width`；
- `bottom <= image_height`。

### 10.7 DatasetWriter

职责：

- 创建三个并列 dataset 子目录；
- full-scene RGB 每帧只输出一次；
- 写单齿 YOLO 标签；
- 写碰撞模型 YOLO 标签；
- 写两份 `classes.txt`；
- 根据配置保留或省略空标签；
- 使用 staging 和原子写入；
- 不参与业务判断。

### 10.8 Reporter

职责：

- 输出特征；
- 输出逐齿判断；
- 输出逐帧碰撞模型判断；
- 输出异常；
- 输出汇总；
- 写 manifest；
- 不修改规则结果。

---

## 11. 统一配置文件设计

```json
{
  "schema_version": 1,
  "pipeline": {
    "mode": "full",
    "strict_pairing": true,
    "on_frame_error": "fail_fast"
  },
  "inputs": {
    "full_scene": {
      "rgb_dir": "/data/full_scene_rgb",
      "semantic_dir": "/data/full_scene_semantic/semantic_id"
    },
    "excavator_only": {
      "semantic_dir": "/data/excavator_only_semantic/semantic_id"
    },
    "semantic_mapping": "/data/semantic_mapping.json"
  },
  "targets": {
    "teeth": [
      {
        "class_id": 0,
        "class_name": "tooth_01",
        "semantic_label": "teeth_01_front_3DGS"
      },
      {
        "class_id": 1,
        "class_name": "tooth_02",
        "semantic_label": "teeth_02_front_3DGS"
      },
      {
        "class_id": 2,
        "class_name": "tooth_03",
        "semantic_label": "teeth_03_front_3DGS"
      },
      {
        "class_id": 3,
        "class_name": "tooth_04",
        "semantic_label": "teeth_04_front_3DGS"
      },
      {
        "class_id": 4,
        "class_name": "tooth_05",
        "semantic_label": "teeth_05_front_3DGS"
      }
    ],
    "collision_model": {
      "class_id": 0,
      "class_name": "tooth_collision_model"
    }
  },
  "modules": {
    "semantic_features": {
      "enabled": true,
      "target_extraction": "single_target_scan"
    },
    "visibility_ratio": {
      "enabled": true,
      "zero_reference_value": -1,
      "ratio_over_one": "keep_and_flag"
    },
    "pose_metrics": {
      "enabled": true,
      "algorithm": "pixel_cell_min_area_rect_v1",
      "invalid_value": -1,
      "write_angle": true
    },
    "single_tooth_boxes": {
      "enabled": true,
      "minimum_pixels": 10
    },
    "threshold_rules": {
      "enabled": true,
      "single_tooth": {
        "minimum_visible_ratio_a": 0.2,
        "minimum_fill_ratio_c": 0.3,
        "height_width_axis_mode": "x_over_y",
        "minimum_height_width_ratio_d": 1.5
      },
      "collision_model": {
        "minimum_visible_ratio_b": 0.3,
        "drop_if_low_visibility_teeth_at_least": 3,
        "drop_if_bad_pose_teeth_at_least": 3
      }
    },
    "collision_box": {
      "enabled": true,
      "length_axis": "y",
      "length_source": "full_scene",
      "width_source": "excavator_only",
      "union_scope": "all_valid_teeth"
    }
  },
  "execution": {
    "backend": "numpy_opencv",
    "workers": 8,
    "max_in_flight": 32,
    "reader_threads": 4,
    "verification_level": "sample",
    "verification_sample_frames": 32
  },
  "cache": {
    "enabled": true,
    "reuse": true,
    "directory": "cache",
    "fingerprint_mode": "metadata",
    "on_mismatch": "rebuild"
  },
  "output": {
    "root": "../output/output0731_02",
    "overwrite": false,
    "image_mode": "hardlink_required",
    "keep_empty_label_files": true,
    "staging_mode": "atomic_directory"
  },
  "reporting": {
    "level": "full"
  }
}
```

示例中的 `a、b、c、d` 只用于展示格式，正式运行前必须使用标定后的值。

---

## 12. 配置参数说明

### 12.1 pipeline

| 参数 | 允许值 | 含义 |
|---|---|---|
| `mode` | `full`、`analyze_only`、`filter_only` | 完整运行、只生成特征缓存、只复用缓存过滤 |
| `strict_pairing` | `true` | 三类输入必须严格同帧 |
| `on_frame_error` | `fail_fast` | 任一帧读取或计算失败时终止正式运行 |

### 12.2 modules.semantic_features

| 参数 | 含义 |
|---|---|
| `enabled` | 是否启用目标特征提取；正式流程必须为 `true` |
| `target_extraction` | 目标像素提取算法版本 |

### 12.3 modules.visibility_ratio

| 参数 | 含义 |
|---|---|
| `zero_reference_value` | `R=0` 时的哨兵值，固定为 `-1` |
| `ratio_over_one` | 比例超过 1 时保留原值并报告 |

### 12.4 modules.pose_metrics

| 参数 | 含义 |
|---|---|
| `algorithm` | 旋转外接矩形算法版本 |
| `invalid_value` | 无有效参考轮廓时使用 `-1` |
| `write_angle` | 是否在报告中输出 `Theta` |

### 12.5 modules.single_tooth_boxes

| 参数 | 含义 |
|---|---|
| `minimum_pixels` | full-scene 中达到该像素数才建立候选单齿框 |

### 12.6 modules.threshold_rules

| 参数 | 含义 |
|---|---|
| `minimum_visible_ratio_a` | 单齿遮挡显露阈值 |
| `minimum_visible_ratio_b` | 碰撞模型逐齿遮挡阈值 |
| `minimum_fill_ratio_c` | 参考旋转框填充比例阈值 |
| `height_width_axis_mode` | 高宽方向：`x_over_y`（默认）或 `y_over_x` |
| `minimum_height_width_ratio_d` | 最终 YOLO 像素框的最低高宽比阈值 |
| `drop_if_low_visibility_teeth_at_least` | 低显露斗齿达到此数量时删除碰撞模型框 |
| `drop_if_bad_pose_teeth_at_least` | 姿态不合格斗齿达到此数量时删除碰撞模型框 |

约束：

```text
a、b、c 位于 [0, 1]
d >= 0
两个数量阈值位于 [1, 5]
```

### 12.7 modules.collision_box

| 参数 | 含义 |
|---|---|
| `length_axis` | 长度使用原始图像的 `x` 轴或 `y` 轴 |
| `length_source` | 固定为 `full_scene` |
| `width_source` | 固定为 `excavator_only` |
| `union_scope` | 固定使用所有有效斗齿的整体并集 |

### 12.8 execution

| 参数 | 含义 |
|---|---|
| `backend` | 初版为 `numpy_opencv` |
| `workers` | 帧级工作线程数 |
| `max_in_flight` | 同时提交但尚未完成的最大帧任务数 |
| `reader_threads` | 输入预取线程数 |
| `verification_level` | `none`、`sample` 或 `full` |
| `verification_sample_frames` | 抽样验证帧数 |

### 12.9 cache

| 参数 | 含义 |
|---|---|
| `enabled` | 是否保存特征缓存 |
| `reuse` | 指纹匹配时是否允许复用缓存 |
| `directory` | 缓存输出子目录 |
| `fingerprint_mode` | `metadata` 或 `content` |
| `on_mismatch` | 指纹不一致时重新构建缓存 |

### 12.10 output

| 参数 | 含义 |
|---|---|
| `root` | 整体输出根目录 |
| `overwrite` | 是否覆盖已有输出 |
| `image_mode` | `full/filter_only` 必须为 `hardlink_required`、`hardlink_or_copy` 或 `copy`；`none` 仅允许 `analyze_only` |
| `keep_empty_label_files` | 是否保留空标签文件 |
| `staging_mode` | 正式输出前先写 staging 目录 |

---

## 13. 数据模型

### 13.1 FrameFeatures

每帧最终形成：

```text
FrameFeatures
├── ordinal
├── frame_id
├── image_width
├── image_height
├── whole_counts[5]
├── reference_counts[5]
├── visibility_ratios[5]
├── ratio_statuses[5]
├── full_axis_boxes[5,4]
├── reference_axis_boxes[5,4]
├── full_geometry_valid[5]
├── reference_geometry_valid[5]
├── reference_fill_ratios[5]
├── reference_aspect_ratios[5]
├── reference_angles[5]
├── reference_pose_statuses[5]
└── source_box_exists[5]
```

### 13.2 FeatureMatrix

所有帧汇总为预分配矩阵：

```text
frame_ids                     [F]
image_widths                  [F]
image_heights                 [F]
whole_counts                  [F,5]
reference_counts              [F,5]
visibility_ratios             [F,5]
ratio_statuses                [F,5]
full_axis_boxes               [F,5,4]
reference_axis_boxes          [F,5,4]
full_geometry_valid           [F,5]
reference_geometry_valid      [F,5]
reference_fill_ratios         [F,5]
reference_aspect_ratios       [F,5]
reference_angles              [F,5]
reference_pose_statuses       [F,5]
source_box_exists             [F,5]
```

### 13.3 RuleMasks

```text
height_width_ratios           [F,5]
single_visibility_bad         [F,5]
single_fill_bad               [F,5]
single_height_width_bad       [F,5]
single_drop                   [F,5]
single_keep                   [F,5]
collision_visibility_bad      [F,5]
pose_bad                      [F,5]
occlusion_bad_count           [F]
pose_bad_count                [F]
collision_drop                [F]
collision_keep                [F]
```

规则掩码统一使用 NumPy 向量化计算。

---

## 14. 每帧数据计算链路

```text
1. FrameLoader 加载：
   - full semantic
   - reference semantic
   - full RGB 路径和尺寸

2. SemanticFeatureModule：
   - 一次提取五颗斗齿目标像素
   - 计算 W、R
   - 计算 full/reference axis boxes

3. PoseMetricModule：
   - 只在 reference 轮廓上计算 C、Theta

4. VisibilityRatioModule：
   - R > 0：V = W/R
   - R == 0：V = -1

5. SingleToothBoxModule：
   - W >= minimum_pixels 时建立候选单齿框

6. worker 返回小型 FrameFeatures：
   - 不返回 semantic 数组
   - 不返回完整 mask

7. 主线程按 ordinal 写入预分配 FeatureMatrix

8. ThresholdRuleModule 向量化计算：
   - single_keep
   - occlusion_bad_count
   - pose_bad_count
   - collision_keep

9. CollisionBoxModule 逐帧生成混合框：
   - 不旋转图像
   - 只按 length_axis 选择边界来源

10. DatasetWriter：
    - RGB 只链接一次
    - 分别写两个标签目录

11. Reporter：
    - 写特征、决定、异常和汇总
```

---

## 15. 高速计算方案

### 15.1 单次全图目标扫描

对于每张 semantic，不对整张图执行五次独立比较。推荐：

```python
target_mask = np.isin(semantic, target_ids)
ys, xs = np.nonzero(target_mask)
values = semantic[ys, xs]
```

然后只在目标像素集合中按五个 semantic ID 分组：

```text
selected = values == target_id
```

这样全图扫描一次，后续五次比较只发生在较小的目标像素集合上。

### 15.2 帧级并行

使用有界线程池：

```text
ThreadPoolExecutor
workers = 8
max_in_flight = 32
```

每个 worker 完整处理一帧：

```text
读取两套 semantic
-> 特征提取
-> 旋转几何
-> 返回 FrameFeatures
```

不在线程间传输完整 semantic 数组。

### 15.3 初版后端

初版使用：

```text
NumPy + OpenCV + 多线程
```

不优先迁移旧 PixelRatio 的独立 GPU 计数后端，原因是：

- 新项目为了 bbox 和旋转框本来就要遍历目标像素；
- 像素计数可以在同一次遍历中获得；
- 单独上传 GPU 计数会重复扫描和数据搬运；
- 旋转框仍主要由 CPU/OpenCV 计算。

完成 CPU 基准后，如果 Analysis 阶段仍明显不足，再设计统一的 GPU 特征提取后端，而不是只加速像素计数。

### 15.4 其他加速措施

- 启动时目录只扫描一次；
- 使用 `np.load(..., mmap_mode="r")`；
- 输入预取使用有界线程队列；
- FeatureMatrix 启动时预分配；
- 规则掩码使用 NumPy 向量化；
- full RGB 不解码，优先硬链接；
- RGB 每帧只执行一次文件物化；
- 标签文本先在内存生成，再并发写入；
- 报告由主线程集中写入；
- staging 完成后整体提交；
- 指纹匹配时完全跳过 semantic 读取。

### 15.5 基准测试

必须比较：

```text
workers = 1、4、8、16
reader_threads = 1、2、4、8
```

在真实数据盘上选择实际最快且稳定的配置，而不是根据 CPU 核心数直接推断。

---

## 16. 缓存设计

### 16.1 缓存是什么

第一次运行时，项目从两套 semantic 计算：

```text
W、R
full/reference axis boxes
C、Theta
source_box_exists
```

这些特征与 `a、b、c、d` 的具体值无关，可以保存到：

```text
cache/features_cache.npz
```

缓存：

- 不保存 RGB 副本；
- 不修改图像；
- 不保存完整 semantic mask；
- 只保存每帧五颗斗齿的数值和像素框；
- 可以通过配置关闭。

### 16.2 缓存的收益

第一次完整运行：

```text
读取 semantic
-> 计算特征
-> 保存缓存
-> 应用阈值
-> 写 dataset
```

只修改阈值后：

```text
读取 features_cache.npz
-> 应用新阈值
-> 写新 dataset
```

不需要重新读取大体积 semantic NPY。

### 16.3 三种运行模式

```text
full
    没有有效缓存时计算特征，并继续生成 dataset

analyze_only
    只计算特征、缓存和特征报告
    用于标定 a、b、c、d

filter_only
    必须存在匹配缓存
    不读取 semantic，只重新应用规则和写 dataset
```

---

## 17. 指纹设计

### 17.1 指纹是什么

指纹是根据输入数据和关键配置计算出的 SHA-256 字符串，用来判断缓存是否属于当前数据和当前算法。

它不是图像识别结果，也不会修改任何输入文件。

### 17.2 Analysis 指纹

Analysis 指纹包含：

- full/reference semantic 目录；
- 所有 frame ID；
- 文件名、大小和修改时间，或完整文件内容摘要；
- semantic mapping 内容；
- 五颗目标 semantic label 和 ID；
- `minimum_pixels`；
- 目标提取算法版本；
- 旋转框算法版本；
- 输入数组 shape 和 dtype。

Analysis 指纹不包含：

- `a、b、c、d`；
- `length_axis`；
- 输出目录；
- 报告级别。

因此只修改阈值时，缓存仍可复用。

### 17.3 Run 指纹

Run 指纹包含：

- Analysis 指纹；
- `a、b、c、d`；
- 两个数量阈值；
- `length_axis`；
- 输出类别契约；
- 影响最终标签内容的输出配置。

Run 指纹用于说明最终 dataset 是由哪份特征和哪套规则生成的。

### 17.4 修改与复用关系

| 修改内容 | Analysis 指纹 | Run 指纹 | 是否重新读取 semantic |
|---|---:|---:|---:|
| 修改 `a` | 不变 | 改变 | 否 |
| 修改 `d` | 不变 | 改变 | 否 |
| 修改 `length_axis` | 不变 | 改变 | 否 |
| 修改输出路径 | 不变 | 改变 | 否 |
| 修改 semantic 目录 | 改变 | 改变 | 是 |
| 修改 semantic mapping | 改变 | 改变 | 是 |
| 修改目标 label | 改变 | 改变 | 是 |
| 修改旋转框算法 | 改变 | 改变 | 是 |

### 17.5 指纹模式

```text
metadata
    使用相对路径、文件大小、mtime_ns 和 mapping 内容
    速度快，默认推荐

content
    读取所有输入文件并计算内容 SHA-256
    最严格，但首次计算较慢
```

### 17.6 缓存不匹配策略

当指纹不一致时：

```text
full 模式：
    自动重新构建缓存

analyze_only 模式：
    自动重新构建缓存

filter_only 模式：
    终止运行并报告缓存不匹配
```

禁止强制复用不匹配缓存。

---

## 18. Preflight 设计

正式执行前必须检查：

1. JSON schema 版本受支持；
2. 不存在未知字段；
3. 所有输入目录和 mapping 文件存在；
4. full RGB、full semantic、reference semantic frame ID 完全一致；
5. 不存在重复 frame ID；
6. 三类输入均非空；
7. semantic shape 与 RGB 尺寸一致；
8. full/reference semantic shape、dtype 一致；
9. semantic mapping 包含五个目标 label；
10. 五个 class ID 恰好为 `0～4`；
11. 五个 semantic label 不重复；
12. `a、b、c` 位于 `[0,1]`；
13. `d >= 1`；
14. 两个数量阈值位于 `[1,5]`；
15. `length_axis` 为 `x` 或 `y`；
16. `length_source` 为 `full_scene`；
17. `width_source` 为 `excavator_only`；
18. 输出目录与输入目录互不包含；
19. overwrite、cache reuse 和运行模式组合合法；
20. filter-only 的缓存存在且指纹匹配。

任何契约错误必须在创建正式 dataset 前终止。

---

## 19. 报告设计

### 19.1 tooth_features.csv

```text
frame_id
semantic_label
class_id
whole_pixels
reference_pixels
visible_ratio
ratio_status
full_box_left
full_box_top
full_box_right
full_box_bottom
reference_box_left
reference_box_top
reference_box_right
reference_box_bottom
fill_ratio
box_x_length
box_y_length
height_width_axis_mode
height_width_ratio
orientation_degrees
reference_pose_status
source_box_exists
```

### 19.2 tooth_decisions.csv

```text
frame_id
semantic_label
class_id
source_box_exists
visible_ratio
threshold_a
visibility_pass
fill_ratio
threshold_c
fill_pass
box_x_length
box_y_length
height_width_axis_mode
height_width_ratio
threshold_d
height_width_pass
action
reason_codes
```

### 19.3 collision_decisions.csv

```text
frame_id
occlusion_bad_count
pose_bad_count
threshold_b
occlusion_count_threshold
pose_count_threshold
length_axis
full_union_left
full_union_top
full_union_right
full_union_bottom
reference_union_left
reference_union_top
reference_union_right
reference_union_bottom
output_left
output_top
output_right
output_bottom
action
reason_codes
```

### 19.4 frame_summary.csv

```text
frame_id
image_width
image_height
single_source_count
single_keep_count
single_drop_count
occlusion_bad_count
pose_bad_count
collision_action
collision_reason
mixed_geometry_valid
```

### 19.5 reason_codes

原因码必须支持组合，例如：

```text
below_a
below_c
below_height_width_ratio
reference_missing
source_box_absent
occlusion_majority
pose_majority
mixed_geometry_invalid
ratio_over_one
```

组合原因使用稳定顺序，保证跨线程输出确定。

---

## 20. 原子输出与恢复

### 20.1 staging

正式输出先写到：

```text
.<output-name>.staging-<run-id>/
```

成功完成后：

1. 写最终报告；
2. 写 completed manifest；
3. 执行抽样或完整验证；
4. 将 staging 目录重命名为正式输出目录。

失败时不得留下貌似完成的正式 dataset。

### 20.2 Analysis 恢复

Analysis 阶段可以使用逐帧 ledger：

```text
ordinal
frame_id
feature arrays
completed_frames
analysis_fingerprint
```

中断后只有在 Analysis 指纹一致时才能继续。

### 20.3 Filter 阶段

Filter 阶段计算量小，失败后默认重新从特征缓存生成 staging，不需要复杂的逐帧恢复。

---

## 21. 推荐代码结构

```text
260731PostProcessChain_v02/
├── README.md
├── requirements.txt
├── run_pipeline.py
├── configs/
│   ├── example.json
│   └── output0731_02.json
├── docs/
│   ├── implement/
│   │   └── implement_v01.md
│   ├── architecture.md
│   ├── data_contract.md
│   ├── logic_v02.md
│   └── module_contracts.md
├── postprocess_chain_v02/
│   ├── __init__.py
│   ├── config.py
│   ├── models.py
│   ├── main_pipeline.py
│   ├── preflight.py
│   ├── frame_discovery.py
│   ├── frame_loader.py
│   ├── executor.py
│   ├── artifact_store.py
│   ├── modules/
│   │   ├── semantic_features/
│   │   │   ├── __init__.py
│   │   │   ├── config.py
│   │   │   ├── models.py
│   │   │   └── module.py
│   │   ├── visibility_ratio/
│   │   │   ├── __init__.py
│   │   │   ├── config.py
│   │   │   └── module.py
│   │   ├── pose_metrics/
│   │   │   ├── __init__.py
│   │   │   ├── config.py
│   │   │   └── module.py
│   │   ├── single_tooth_boxes/
│   │   │   ├── __init__.py
│   │   │   ├── config.py
│   │   │   └── module.py
│   │   ├── threshold_rules/
│   │   │   ├── __init__.py
│   │   │   ├── config.py
│   │   │   └── module.py
│   │   └── collision_box/
│   │       ├── __init__.py
│   │       ├── config.py
│   │       └── module.py
│   ├── cache/
│   │   ├── __init__.py
│   │   ├── feature_cache.py
│   │   ├── fingerprint.py
│   │   └── manifest.py
│   ├── output/
│   │   ├── __init__.py
│   │   ├── atomic_io.py
│   │   ├── dataset_writer.py
│   │   ├── reporter.py
│   │   └── staging.py
│   └── common/
│       ├── __init__.py
│       ├── semantic_mapping.py
│       ├── pixel_box.py
│       ├── oriented_box.py
│       └── yolo_format.py
└── tests/
    ├── __init__.py
    ├── helpers.py
    ├── test_config.py
    ├── test_preflight.py
    ├── test_semantic_features.py
    ├── test_visibility_ratio.py
    ├── test_pose_metrics.py
    ├── test_single_tooth_boxes.py
    ├── test_threshold_rules.py
    ├── test_collision_box.py
    ├── test_cache.py
    ├── test_pipeline_integration.py
    └── test_determinism.py
```

---

## 22. 测试方案

### 22.1 配置测试

- 未知字段必须拒绝；
- 五个 class ID 必须为 `0～4`；
- semantic label 必须唯一；
- 阈值范围必须严格验证；
- 非法 length_axis 必须拒绝；
- 路径嵌套必须拒绝；
- filter-only 缺少缓存必须拒绝。

### 22.2 特征测试

- 五颗斗齿均存在；
- 中间斗齿缺失；
- 单颗小于 minimum_pixels；
- `R=0`；
- `V>1`；
- 轴对齐框半开边界；
- 两种高宽方向模式的计算结果互为倒数；
- `C` 位于合理范围；
- 无有效参考轮廓返回 `-1`。

### 22.3 规则测试

- `V==a` 保留；
- `V==b` 不计为低显露；
- `C==c` 保留；
- `HWR==d` 保留；
- `x_over_y` 使用最终 YOLO 像素框的 x 长度除以 y 长度；
- `y_over_x` 的结果与 `x_over_y` 互为倒数；
- 四个候选框时统计基数仍为五；
- 三颗低显露删除碰撞模型框；
- 两颗低显露保留碰撞模型框；
- 三颗姿态不合格删除碰撞模型框；
- 全部无遮挡但全部收起时删除碰撞模型框。

### 22.4 碰撞框测试

- `length_axis=y` 时 top/bottom 来自 full；
- `length_axis=y` 时 left/right 来自 reference；
- `length_axis=x` 时 left/right 来自 full；
- `length_axis=x` 时 top/bottom 来自 reference；
- 中间斗齿超出端部时整体并集完整；
- 不发生任何图像或坐标旋转；
- 无效边界不输出错误框。

### 22.5 输出测试

- RGB 只出现在 `dataset/rgb`；
- RGB 每帧只物化一次；
- 两个标签目录中不含 PNG；
- 文件名严格对应；
- 空标签策略正确；
- classes.txt 正确；
- staging 失败不产生正式输出。

### 22.6 缓存测试

- 相同 Analysis 指纹复用缓存；
- 修改 `a` 后复用缓存；
- 修改 semantic 后拒绝缓存；
- 修改 mapping 后拒绝缓存；
- 修改旋转框算法后拒绝缓存；
- filter-only 指纹不匹配时终止；
- 缓存运行与无缓存完整运行结果一致。

### 22.7 并发确定性测试

比较：

```text
workers=1
workers=4
workers=8
```

要求：

- YOLO 标签逐字节一致；
- CSV 行顺序一致；
- JSON 内容一致，时间字段除外；
- 决策原因顺序一致；
- 汇总计数一致。

---

## 23. 实施阶段

### 阶段一：项目骨架和契约

实现：

- 新项目目录；
- 统一 JSON；
- 强类型配置；
- FrameTask、FrameContext、ArtifactStore；
- Preflight；
- manifest 基础结构。

验收：配置和输入契约测试全部通过。

### 阶段二：特征子模块

实现：

- SemanticFeatureModule；
- VisibilityRatioModule；
- PoseMetricModule；
- SingleToothBoxModule；
- FeatureMatrix。

验收：人工构造小图可以手算并完全匹配 W、R、V、框、C、HWR。

### 阶段三：规则和碰撞模型框

实现：

- ThresholdRuleModule；
- 五齿固定基数；
- CollisionBoxModule；
- `length_axis=x/y`；
- YOLO 格式化。

验收：所有边界和三齿多数测试通过。

### 阶段四：缓存和指纹

实现：

- features_cache.npz；
- cache manifest；
- Analysis 指纹；
- Run 指纹；
- full/analyze-only/filter-only；
- 指纹不匹配重建或拒绝。

验收：只修改阈值时不读取 semantic，结果与完整运行一致。

### 阶段五：输出和报告

实现：

- 三目录 dataset；
- RGB 单份硬链接；
- 决策报告；
- anomalies；
- summary；
- staging；
- 输出验证。

验收：目录结构、标签和报告满足契约。

### 阶段六：旧链路逻辑对照

旧项目只作为参考，选择固定小数据验证共同逻辑：

- 单齿轴对齐框；
- W/R 像素计数；
- 显露比例；
- a/b 规则边界；
- frame ID 顺序；
- class ID。

不导入旧项目代码，不依赖旧项目运行目录。

### 阶段七：性能和阈值标定

执行：

- workers 和 reader_threads 基准；
- Analysis 各阶段耗时统计；
- 峰值内存统计；
- 缓存复用耗时；
- C、HWR、Theta 分布报告；
- a、b、c、d 正式标定。

---

## 24. 验收标准

项目完成必须满足：

1. full/reference semantic 每帧各只读取一次；
2. 不旋转、不缩放、不裁剪、不修改任何图像；
3. 不进行相机位姿或坐标系变换；
4. 主流水线和子模块职责清晰；
5. 子模块不重复扫描目录或读取同一 semantic；
6. 所有统计固定以五颗斗齿为基数；
7. `R=0` 输出 `V=-1 + reference_missing`；
8. 单齿严格应用 `a、c、d`；
9. 碰撞模型严格应用遮挡多数和姿态多数；
10. 收起状态不输出碰撞模型框；
11. 碰撞模型长度来自 full、宽度来自 reference；
12. `length_axis` 只决定原图边界来源，不修改图像；
13. RGB 只输出一份；
14. 两个标签目录与 RGB 目录并列；
15. 缓存指纹匹配时可以完全跳过 semantic 读取；
16. 缓存指纹不匹配时不得静默复用；
17. 单线程和多线程输出确定一致；
18. 失败运行不留下貌似完整的正式 dataset；
19. 不直接复用或导入三个旧项目的代码文件；
20. 高宽比过滤使用的 full-scene 像素框与最终 YOLO 输出框完全一致；
21. 所有配置、输入、特征、规则和输出均可审计。

---

## 25. 最终执行链路摘要

```text
统一 JSON
    -> Preflight
    -> 严格发现并配对帧
    -> 检查 Analysis 缓存指纹
    -> 无有效缓存时并行读取两套 semantic
    -> 一次计算 W、R、轴对齐框、C、Theta
    -> 写入或复用 FeatureMatrix
    -> 从最终 YOLO 源框计算 HWR，并向量化应用 a、b、c、d
    -> 生成过滤后的单齿框
    -> 在原始图像坐标中生成混合碰撞模型框
    -> staging 写入一份 RGB 和两套标签
    -> 写报告和 manifest
    -> 验证
    -> 原子提交正式 output_root
```

该方案的核心原则为：

```text
一次输入发现
一次 semantic 读取
清晰子模块边界
统一配置
向量化规则
帧级并行
可复用特征缓存
RGB 单份输出
两套标签独立输出
不修改任何图像
```
