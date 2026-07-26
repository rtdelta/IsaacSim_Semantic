# 03 输入数据契约与 YOLO 基础

本项目对输入很严格。大多数“算法没有输出”的问题，其实是文件命名、标签、数组类型或尺寸不符合契约。

## 1. 三类必需输入

总配置的 `inputs` 必须指向：

| 字段 | 内容 | 当前用途 |
| --- | --- | --- |
| `rgb_dir` | `rgb_<frame_id>.png` | 校验宽高，并物化到模块输出 |
| `semantic_dir` | `semantic_id_<frame_id>.npy` | 计算像素框 |
| `semantic_mapping` | JSON mapping | 把模块中的 label 解析为 ID |

注意：算法不读取 RGB 像素做检测。RGB 仍然必要，因为项目要校验 semantic 尺寸，并给每个 YOLO 数据集提供原图。

## 2. 帧命名与配对规则

只识别当前目录下的固定格式：

```text
rgb_<frame_id>.png
semantic_id_<frame_id>.npy
```

示例：

```text
rgb_0042.png            <-> semantic_id_0042.npy
rgb_cameraA_0042.png    <-> semantic_id_cameraA_0042.npy
```

`frame_id` 可以是任意非空字符串，但项目按字符串排序。为了得到直观的数值顺序，推荐固定宽度补零：

```text
0000, 0001, ..., 0010
```

不要使用：

```text
1, 2, 10
```

因为字符串顺序会是 `1, 10, 2`。

RGB 与 semantic 的 frame ID 集合必须完全相等。任何一侧多帧或少帧都会在处理前整体拒绝运行。无关后缀或前缀的文件会被忽略。

## 3. semantic 数组契约

每个 `.npy` 必须满足：

- 使用 `np.save` 可读的 NumPy 文件；
- 禁止依赖 pickle；
- 恰好二维，形状为 `(height, width)`；
- dtype 与 mapping 的 `dataset_dtype` 完全一致；
- 宽高与对应 RGB 图片一致。

例如 RGB 为 `1280 × 720`，semantic 应是：

```python
semantic.shape == (720, 1280)
```

不是 `(1280, 720)`，也不是 `(720, 1280, 1)`。

运行时 semantic 以 `mmap_mode="r"` 打开，有利于降低一次性内存复制，但数组仍会在 NumPy 筛选时产生临时数据。

## 4. semantic mapping

当前加载器真正使用的字段是：

```json
{
  "dataset_dtype": "uint16",
  "classes": [
    {"id": 5, "label": "tooth_1"},
    {"id": 6, "label": "tooth_2"}
  ]
}
```

规则：

- `classes` 必须是非空数组；
- 每个 `label` 是非空字符串，且不能重复；
- 每个 `id` 是整数且不能重复；
- `dataset_dtype` 如果存在，必须是有效 NumPy dtype；
- 当前模块配置中出现的 semantic label 必须存在于 mapping。

mapping 还可以含 `schema_version`、颜色、来源 USD、背景和 unknown 等上游元数据；当前加载器会忽略这些额外字段。

### 名称是严格匹配

以下是三个不同的 label：

```text
tooth_1
tooth_01
Tooth_1
```

项目不会自动补零、改大小写或做别名映射。模块配置与 mapping 必须逐字一致。

## 5. 像素框的定义

`PixelBox` 使用半开区间：

```text
[left, top, right, bottom)
```

也就是：

- `left`、`top` 属于框；
- `right`、`bottom` 是框外的第一个坐标；
- `width = right - left`；
- `height = bottom - top`。

如果目标像素最小 x 为 10、最大 x 为 14，则：

```text
left = 10
right = 14 + 1 = 15
width = 5
```

半开区间能避免常见的 `+1/-1` 混乱，并与 NumPy 切片保持一致：

```python
semantic[top:bottom, left:right]
```

## 6. 当前“单标签框”到底是什么

对某个 semantic ID，算法查找整张图上所有同 ID 像素，然后取：

```text
left   = min(x)
top    = min(y)
right  = max(x) + 1
bottom = max(y) + 1
```

这是“该 label 在整张图上的一个外包矩形”，不是实例检测，也不做连通域。

如果 `tooth_1` 的像素分成两块相距很远的区域，算法仍会输出一个同时包住两块的大框。若未来需要“一块一个框”，必须新增连通域/实例算法，不能只改配置。

`pixel_count` 是真实目标像素数量，不是框面积：

```text
pixel_count != width * height
```

模块用它过滤很小的 mask。

## 7. YOLO 检测格式

每一行：

```text
class_id x_center y_center width height
```

后四个值都除以图片宽高归一化到 `[0, 1]`。

对像素框 `[left, top, right, bottom)`：

```text
x_center = (left + right) / 2 / image_width
y_center = (top + bottom) / 2 / image_height
width    = (right - left) / image_width
height   = (bottom - top) / image_height
```

例：图片 `50 × 50`，框为 `[10, 12, 39, 40)`：

```text
x_center = 49 / 2 / 50 = 0.49
y_center = 52 / 2 / 50 = 0.52
width    = 29 / 50     = 0.58
height   = 28 / 50     = 0.56
```

输出：

```text
0 0.49000000 0.52000000 0.58000000 0.56000000
```

项目会验证：

- class ID 在 `classes.txt` 的范围内；
- detection 的 class name 与该 ID 对应名称一致；
- 框不超出图片；
- 中心和尺寸有限且在合法范围。

## 8. 三种“没有框”不是一回事

### 空标签

模块返回 `YoloAnnotationSet(())`。项目创建图片和一个 0 字节 `.txt`。在检测训练中通常表示“确认没有目标”的负样本。

### 排除帧

模块返回 `disposition="exclude"`。该帧不进入该模块的数据集。它表示“信息不足，不应该把它当作负样本”。

### 错误帧

加载、计算或写出抛异常。会记入 `errors.jsonl`，最终运行退出码为 `1`。它表示结果不完整或实现/数据有问题。

这三种状态的业务含义必须区分。斗齿集合默认在缺少端部时排除帧，就是为了避免把“端部看不全”误标为“没有斗齿集合”。

## 9. 快速检查一份数据

在项目根目录执行，替换路径：

```powershell
@'
import json
from pathlib import Path

import numpy as np
from PIL import Image

rgb = Path(r"tutorial_work/input/rgb/rgb_0000.png")
semantic_path = Path(r"tutorial_work/input/semantic_id/semantic_id_0000.npy")
mapping_path = Path(r"tutorial_work/input/semantic_mapping.json")

semantic = np.load(semantic_path, allow_pickle=False)
with Image.open(rgb) as image:
    print("RGB:", image.size)
print("semantic:", semantic.shape, semantic.dtype)
print("IDs:", np.unique(semantic).tolist())
mapping = json.loads(mapping_path.read_text(encoding="utf-8-sig"))
print("mapping:", {item["id"]: item["label"] for item in mapping["classes"]})
'@ | python -
```

重点核对：

- RGB `(width, height)` 与 semantic `(height, width)` 对应；
- dtype 一致；
- 实际出现的目标 ID 在 mapping 中；
- 模块配置需要的 label 在 mapping 中。

## 本章验收

1. 解释为什么 semantic 形状顺序与 Pillow 输出顺序相反。
2. 手算一个像素框的 YOLO 行。
3. 解释同一 label 两块分离像素为什么会得到一个大框。
4. 解释“空标签”和“排除帧”对训练集含义的区别。
5. 找出 `tooth_1` 与 `tooth_01` 混用会在哪个阶段失败。

---

上一篇：[02_环境准备与第一次完整运行.md](02_环境准备与第一次完整运行.md)  
下一篇：[04_配置文件完全手册.md](04_配置文件完全手册.md)
