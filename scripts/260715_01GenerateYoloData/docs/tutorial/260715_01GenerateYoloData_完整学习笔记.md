# 260715_01GenerateYoloData 完整学习笔记

> 学习目标：从零理解并掌握这个“Isaac Sim 语义 ID 图转 YOLO 检测标注”的小型数据工程项目。本文不只告诉你命令，还会解释数据语义、坐标公式、源码调用链、并发模型、可靠性设计、测试方法、限制和二次开发方向。

## 目录

1. [先用一句话认识项目](#1-先用一句话认识项目)
2. [需要先懂的三个概念](#2-需要先懂的三个概念)
3. [项目在整条数据流水线中的位置](#3-项目在整条数据流水线中的位置)
4. [目录与文件职责](#4-目录与文件职责)
5. [输入、配置和输出的数据契约](#5-输入配置和输出的数据契约)
6. [从零搭建运行环境](#6-从零搭建运行环境)
7. [第一次完整运行](#7-第一次完整运行)
8. [手算一遍 YOLO 边界框](#8-手算一遍-yolo-边界框)
9. [源码总览与调用链](#9-源码总览与调用链)
10. [配置加载与启动前校验](#10-配置加载与启动前校验)
11. [单帧转换算法逐句拆解](#11-单帧转换算法逐句拆解)
12. [批量并发、内存与可靠性设计](#12-批量并发内存与可靠性设计)
13. [测试代码怎么读、怎么跑](#13-测试代码怎么读怎么跑)
14. [断点续跑、覆盖和退出码](#14-断点续跑覆盖和退出码)
15. [常见故障与系统化排查](#15-常见故障与系统化排查)
16. [如何接入 YOLO 训练流程](#16-如何接入-yolo-训练流程)
17. [当前限制与二次开发路线](#17-当前限制与二次开发路线)
18. [循序渐进练习与答案](#18-循序渐进练习与答案)
19. [术语表与速查表](#19-术语表与速查表)
20. [本教程的实际验证记录](#20-本教程的实际验证记录)

---

## 1. 先用一句话认识项目

这个项目读取：

- 一批普通 RGB 图片；
- 与每张图片逐像素对齐的二维语义 ID 数组；
- 一份“语义名称 → 数值 ID”的 mapping；
- 一份“哪些语义名称属于哪个 YOLO 类别”的配置；

然后为目标语义像素计算最小外接矩形，输出 YOLO 目标检测格式的图片和 TXT 标签。

最核心的转换关系是：

~~~text
语义标签名
  ↓ semantic_mapping.json
语义数值 ID
  ↓ 在 semantic_id_*.npy 中找像素
目标像素集合
  ↓ 求 min/max
像素坐标边界框
  ↓ 除以图片宽高
YOLO 归一化边界框
~~~

### 1.1 它解决了什么问题

Isaac Sim 可以输出语义分割结果。语义分割告诉我们“每个像素是什么”，而 YOLO 检测训练通常需要“目标在哪个矩形框里”。本项目自动把前者转换成后者，避免人工逐张画框。

### 1.2 它没有做什么

当前项目不是完整的 YOLO 训练框架，也不是 Isaac Sim 采集脚本。它不负责：

- 启动 Isaac Sim 或生成相机图像；
- 切分 train、val、test；
- 生成 Ultralytics 的 <code>data.yaml</code>；
- 训练或评估模型；
- 把同一语义标签的多个连通实例自动拆成多个框；
- 输出分割多边形或实例掩码。

把它理解成一座“数据格式转换桥”最准确。

---

## 2. 需要先懂的三个概念

### 2.1 RGB 图片

RGB 图片就是训练时模型看到的输入，例如 <code>rgb_0000.png</code>。其逻辑尺寸写作：

~~~text
宽度 W × 高度 H
~~~

Pillow 读取图片尺寸时返回 <code>(W, H)</code>。

### 2.2 语义 ID 图

这里的语义图不是为了观看的彩色 PNG，而是 NumPy 的二维数组：

~~~text
shape = (H, W)
~~~

数组中的每一个整数都表示该像素所属的语义类别。例如：

~~~text
0 0 0 0 0
0 5 5 5 0
0 5 5 5 0
0 0 0 0 0
~~~

如果 mapping 规定 ID 5 对应 <code>tooth_1</code>，那么中间六个像素就是 <code>tooth_1</code>。

必须牢牢记住 NumPy 和图片坐标的顺序不同：

| 场景 | 顺序 |
|---|---|
| NumPy shape | <code>(高度 H, 宽度 W)</code> |
| NumPy 索引 | <code>array[y, x]</code> |
| Pillow image.size | <code>(宽度 W, 高度 H)</code> |
| 平面坐标 | <code>(x, y)</code> |

很多尺寸错误和框偏移都来自把这两组顺序弄反。

### 2.3 YOLO 检测标签

每张图片配一个同名 TXT。每行代表一个目标框：

~~~text
class_id x_center y_center width height
~~~

除 <code>class_id</code> 外，四个坐标都被图片宽高归一化到 0～1。例如：

~~~text
0 0.50000000 0.50000000 0.25000000 0.40000000
~~~

含义是：YOLO 类别 0，框中心位于图片正中央，框宽是图片宽度的 25%，框高是图片高度的 40%。

---

## 3. 项目在整条数据流水线中的位置

~~~mermaid
flowchart LR
    USD["USD 场景与语义标签"] --> CAPTURE["Isaac Sim 采集程序"]
    CAPTURE --> RGB["rgb/rgb_XXXX.png"]
    CAPTURE --> SEM["semantic_id/semantic_id_XXXX.npy"]
    CAPTURE --> MAP["semantic_mapping.json"]
    USER["人工编写 YOLO 类别配置"] --> CONFIG["yolo_classes.json"]
    RGB --> CONVERT["convert.py"]
    SEM --> CONVERT
    MAP --> CONVERT
    CONFIG --> CONVERT
    CONVERT --> IMAGES["输出图片"]
    CONVERT --> LABELS["YOLO TXT 标签"]
    CONVERT --> CLASSES["classes.txt"]
    IMAGES --> ORGANIZE["数据集切分与目录整理"]
    LABELS --> ORGANIZE
    CLASSES --> YAML["data.yaml"]
    ORGANIZE --> TRAIN["YOLO 训练"]
    YAML --> TRAIN
~~~

这里有三套容易混淆的“类别编号”：

| 编号体系 | 示例 | 由谁定义 | 用在哪里 |
|---|---:|---|---|
| semantic ID | 5 | <code>semantic_mapping.json</code> | NPY 像素值 |
| YOLO class ID | 0 | <code>yolo_classes.json</code> | 输出 TXT 第一列 |
| 运行时内部语义 ID | 可能变化 | Isaac Sim annotator | 上游采集程序内部 |

本项目只直接接触前两套。它通过标签名把 semantic ID 映射到 YOLO class ID，不能假设这两个编号相同。

例如：

~~~text
semantic ID 5  -> label tooth_1 -> YOLO class 0 tooth
semantic ID 6  -> label tooth_2 -> YOLO class 0 tooth
semantic ID 1  -> label arm     -> YOLO class 1 arm
~~~

因此，两个不同的 semantic ID 可以归入同一个 YOLO 类别。

---

## 4. 目录与文件职责

项目目录：

~~~text
260715_01GenerateYoloData/
├── convert.py
├── test_convert.py
├── yolo_classes.example.json
├── requirements.txt
├── README.md
└── docs/
    └── tutorial/
        ├── README.md
        └── 260715_01GenerateYoloData_完整学习笔记.md
~~~

### 4.1 文件职责表

| 文件 | 角色 | 初学时怎么读 |
|---|---|---|
| <code>README.md</code> | 使用说明 | 先快速浏览输入、命令和输出 |
| <code>requirements.txt</code> | Python 依赖 | 了解项目只直接依赖 NumPy 和 Pillow |
| <code>yolo_classes.example.json</code> | 类别配置模板 | 复制后按自己的 mapping 修改 |
| <code>convert.py</code> | 核心程序 | 按本文第 9～12 章分层阅读 |
| <code>test_convert.py</code> | 自动化测试 | 学习如何最小化构造 RGB、NPY 和 JSON |

### 4.2 代码规模

当前工作区版本大致为：

| 文件 | 行数 |
|---|---:|
| <code>convert.py</code> | 581 |
| <code>test_convert.py</code> | 172 |
| <code>README.md</code> | 126 |

这是一个“小而完整”的数据工程项目：输入校验、批处理、并发、原子写入、错误日志、断点续跑和测试都具备，很适合作为 Python 工程化学习样本。

---

## 5. 输入、配置和输出的数据契约

“数据契约”是指调用者必须满足的格式约定。如果契约被破坏，程序应尽早报错。

### 5.1 输入目录

RGB 和语义数组可以位于不同目录：

~~~text
dataset/
├── rgb/
│   ├── rgb_0000.png
│   └── rgb_0001.png
├── semantic_id/
│   ├── semantic_id_0000.npy
│   └── semantic_id_0001.npy
└── semantic_mapping.json
~~~

帧配对只看文件名中间部分：

~~~text
rgb_0000.png          ↔ semantic_id_0000.npy
rgb_cameraA_17.png    ↔ semantic_id_cameraA_17.npy
~~~

也就是说，帧号不强制只能是数字；只要前缀、后缀和中间字符串能精确配对即可。

程序只识别：

- RGB：小写前缀 <code>rgb_</code>，后缀严格为 <code>.png</code>；
- semantic：小写前缀 <code>semantic_id_</code>，后缀严格为 <code>.npy</code>。

在大小写敏感的文件系统上，<code>RGB_0000.png</code>、<code>rgb_0000.PNG</code> 都不会被识别。

### 5.2 RGB 与 NPY 的对应要求

对每一帧：

~~~text
NPY.shape == (RGB.height, RGB.width)
~~~

NPY 必须：

- 是二维数组；
- 不依赖 pickle 对象；
- 若 mapping 声明 <code>dataset_dtype</code>，其 dtype 必须精确一致；
- 像素值使用 mapping 中定义的 semantic ID。

读取 NPY 时采用：

~~~python
np.load(path, mmap_mode="r", allow_pickle=False)
~~~

<code>allow_pickle=False</code> 避免加载任意 Python 对象；<code>mmap_mode="r"</code> 让原始 NPY 可按只读内存映射方式访问。

### 5.3 semantic_mapping.json

本项目真正读取的字段只有 <code>classes</code> 和可选的 <code>dataset_dtype</code>。一个最小示例：

~~~json
{
  "dataset_dtype": "uint16",
  "classes": [
    {"id": 1, "label": "arm"},
    {"id": 5, "label": "tooth_1"},
    {"id": 6, "label": "tooth_2"}
  ]
}
~~~

每个 class 必须有：

- 非空字符串 <code>label</code>；
- 真正的整数 <code>id</code>，布尔值不算整数；
- 全文件中唯一的 label；
- 全文件中唯一的 id。

mapping 可以有更多上游字段，例如背景、颜色、USD 来源等；转换器会忽略它们。

本仓库上游语义采集项目生成的完整 mapping 通常还含有：

~~~json
{
  "schema_version": 1,
  "dataset_dtype": "uint16",
  "background": {"id": 0, "label": "BACKGROUND"},
  "unknown": {"id": 65535, "label": "UNLABELLED"},
  "classes": []
}
~~~

注意：当前转换器只在 <code>classes</code> 中查找可配置目标，不会从 <code>background</code> 或 <code>unknown</code> 节点中找标签。

### 5.4 yolo_classes.json

这份文件不是 Isaac Sim 自动生成的，而是由数据集设计者编写。项目提供了 <code>yolo_classes.example.json</code>：

~~~json
{
  "schema_version": 1,
  "targets": [
    {
      "yolo_id": 0,
      "yolo_name": "tooth",
      "semantic_labels": ["tooth_1", "tooth_2"]
    },
    {
      "yolo_id": 1,
      "yolo_name": "arm",
      "semantic_labels": ["arm"]
    }
  ]
}
~~~

校验规则：

1. 顶层必须是 JSON 对象。
2. <code>schema_version</code> 必须严格等于整数 1。
3. <code>targets</code> 必须是非空数组。
4. <code>yolo_id</code> 必须是非负整数。
5. 所有 <code>yolo_id</code> 必须从 0 开始连续。
6. <code>yolo_name</code> 必须是非空且不能重复。
7. <code>semantic_labels</code> 必须是非空数组。
8. 每个 semantic label 必须在 mapping 的 <code>classes</code> 中存在。
9. 同一个 semantic label 不能被重复分配。

目标在 JSON 中的书写顺序可以是 1、0，但加载完成后会按 <code>yolo_id</code> 排序。不过为了人读起来清楚，仍建议按 0、1、2 顺序书写。

#### “合并类别”不等于“合并边界框”

如果：

~~~json
{
  "yolo_id": 0,
  "yolo_name": "tooth",
  "semantic_labels": ["tooth_1", "tooth_2"]
}
~~~

那么 <code>tooth_1</code> 和 <code>tooth_2</code> 都输出 YOLO 类别 0，但程序会分别为两个 semantic label 求框，所以一帧中最多产生两行类别 0，而不是先把两种像素合成一个大框。

### 5.5 输出目录

成功后是扁平结构：

~~~text
yolo_output/
├── rgb_0000.png
├── rgb_0000.txt
├── rgb_0001.png
├── rgb_0001.txt
├── classes.txt
└── errors.jsonl
~~~

<code>errors.jsonl</code> 仅在至少一帧失败时存在。

图片不会被重新编码、旋转或缩放。程序优先创建硬链接；硬链接不可用时复制原文件。因此标签坐标始终对应原始图片尺寸。

<code>classes.txt</code> 的行号就是 YOLO ID：

~~~text
tooth
arm
~~~

即第 0 行是类别 0，第 1 行是类别 1。

---

## 6. 从零搭建运行环境

### 6.1 进入项目目录

Windows PowerShell：

~~~powershell
Set-Location "D:\learning\IntelligentDepartment\CodesSet\Self\260707IsaacSIm\scripts\260715_01GenerateYoloData"
~~~

### 6.2 检查 Python

~~~powershell
python --version
~~~

当前机器实际验证使用 Python 3.9.18。项目语法使用了：

- <code>from __future__ import annotations</code>；
- dataclass；
- pathlib；
- ProcessPoolExecutor；
- <code>Path.unlink(missing_ok=True)</code>。

因此推荐 Python 3.8 及以上，实际学习时优先使用较新的受支持版本。

### 6.3 建立虚拟环境

~~~powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
~~~

如果 PowerShell 因执行策略拒绝激活，可以直接调用虚拟环境解释器：

~~~powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe convert.py --help
~~~

Linux：

~~~bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
~~~

### 6.4 两个直接依赖

| 依赖 | 最低版本 | 用途 |
|---|---:|---|
| NumPy | 1.23 | 加载 NPY、筛选 ID、找目标坐标、计算框 |
| Pillow | 9.0 | 读取 PNG 的宽高并校验图片 |

本机验证版本是 NumPy 1.26.4 和 Pillow 10.2.0。

### 6.5 先看帮助

~~~powershell
python convert.py --help
~~~

若这一步能显示中文参数说明，说明 Python、依赖和脚本路径基本正确。

---

## 7. 第一次完整运行

### 7.1 第一步：确认输入帧能配对

PowerShell：

~~~powershell
Get-ChildItem "D:\your_dataset\rgb" -Filter "rgb_*.png"
Get-ChildItem "D:\your_dataset\semantic_id" -Filter "semantic_id_*.npy"
~~~

不要只比较数量。10 张 RGB 和 10 个 NPY 仍可能是不同帧号，转换器会精确比较帧 ID 集合。

### 7.2 第二步：查看 mapping 中有哪些标签

PowerShell：

~~~powershell
$mapping = Get-Content "D:\your_dataset\semantic_mapping.json" -Raw | ConvertFrom-Json
$mapping.classes | Select-Object id, label | Format-Table -AutoSize
~~~

或者使用 Python：

~~~python
import json
from pathlib import Path

path = Path(r"D:\your_dataset\semantic_mapping.json")
mapping = json.loads(path.read_text(encoding="utf-8-sig"))
for item in mapping["classes"]:
    print(item["id"], item["label"])
~~~

复制标签时必须精确匹配大小写和字符。项目不支持通配符，也不再隐式识别 <code>tooth_</code> 前缀。

### 7.3 第三步：创建自己的类别配置

不要直接依赖示例文件长期运行。复制一份并命名为数据集专属配置：

~~~powershell
Copy-Item ".\yolo_classes.example.json" ".\yolo_classes.my_dataset.json"
~~~

然后根据 mapping 修改：

~~~json
{
  "schema_version": 1,
  "targets": [
    {
      "yolo_id": 0,
      "yolo_name": "tooth",
      "semantic_labels": ["tooth_1", "tooth_2", "tooth_3", "tooth_4", "tooth_5"]
    },
    {
      "yolo_id": 1,
      "yolo_name": "arm",
      "semantic_labels": ["arm"]
    }
  ]
}
~~~

### 7.4 第四步：先用保守参数运行

第一次建议单进程、单个在途任务，错误输出最容易理解：

~~~powershell
python convert.py --rgb-dir "D:\your_dataset\rgb" --semantic-dir "D:\your_dataset\semantic_id" --mapping "D:\your_dataset\semantic_mapping.json" --class-config ".\yolo_classes.my_dataset.json" --output "D:\your_dataset_yolo" --workers 1 --max-in-flight 1 --min-pixels 10
~~~

确认成功后再增加并发：

~~~powershell
python convert.py --rgb-dir "D:\your_dataset\rgb" --semantic-dir "D:\your_dataset\semantic_id" --mapping "D:\your_dataset\semantic_mapping.json" --class-config ".\yolo_classes.my_dataset.json" --output "D:\your_dataset_yolo" --workers 8 --max-in-flight 16 --min-pixels 10
~~~

Linux 写法：

~~~bash
python3 convert.py \
  --rgb-dir /data/dataset/rgb \
  --semantic-dir /data/dataset/semantic_id \
  --mapping /data/dataset/semantic_mapping.json \
  --class-config ./yolo_classes.my_dataset.json \
  --output /data/dataset_yolo \
  --workers 8 \
  --max-in-flight 16 \
  --min-pixels 10
~~~

### 7.5 参数逐项解释

| 参数 | 必填 | 默认值 | 作用 |
|---|---:|---:|---|
| <code>--rgb-dir</code> | 是 | 无 | RGB 图片目录 |
| <code>--semantic-dir</code> | 是 | 无 | 二维 semantic NPY 目录 |
| <code>--mapping</code> | 是 | 无 | 语义标签到 ID 的 JSON |
| <code>--class-config</code> | 是 | 无 | 语义标签到 YOLO 类别的 JSON |
| <code>--output</code> | 是 | 无 | 输出目录 |
| <code>--workers</code> | 否 | <code>min(CPU 数, 8)</code> | 工作进程数 |
| <code>--max-in-flight</code> | 否 | <code>workers × 2</code> | 尚未消费的最大 Future 数 |
| <code>--min-pixels</code> | 否 | 10 | 单个 semantic label 至少多少像素才出框 |
| <code>--overwrite</code> | 否 | 关闭 | 是否重新生成已有 TXT |

三个数值参数都必须是正整数，所以 <code>0</code> 和负数会被 argparse 拒绝。

<code>--max-in-flight</code> 还必须大于等于 <code>--workers</code>，否则启动时报错。

### 7.6 读懂控制台摘要

典型输出：

~~~text
发现帧数：1000
成功帧数：980
跳过帧数：10
失败帧数：10
空标签帧数：35
生成 YOLO 框：4200
跳过小掩码：18
处理耗时：12.34 秒
平均速度：81.04 帧/秒
~~~

含义：

- 发现：配对成功并提交处理的总帧数；
- 成功：本次实际重新处理并写完标签的帧数；
- 跳过：标签已存在且未启用覆盖的帧数；
- 失败：单帧读取、尺寸、dtype 或写入失败；
- 空标签：成功处理但没有满足条件目标的负样本；
- 框：本次成功帧生成的标签行数；
- 小掩码：出现了目标像素，但数量小于阈值的 semantic label 数；
- 速度：成功、失败和跳过帧总数除以处理耗时。

注意：跳过帧不会重新统计原 TXT 里的框数和空标签状态，所以断点续跑后的本次统计不是整个输出目录的全量统计。

---

## 8. 手算一遍 YOLO 边界框

这一章是整个教程最值得亲手完成的一章。只会运行命令并不足以判断标签是否正确。

### 8.1 构造一帧最小数据

假设 RGB 图片宽 6、高 4，因此 semantic 数组 shape 为 <code>(4, 6)</code>：

~~~text
       x=0  1  2  3  4  5
y=0    [2, 0, 0, 0, 0, 0]
y=1    [0, 0, 1, 1, 1, 0]
y=2    [0, 0, 1, 1, 1, 0]
y=3    [0, 0, 0, 0, 0, 3]
~~~

mapping：

~~~text
1 -> tooth_1
2 -> tooth_2
3 -> arm
~~~

类别配置：

~~~text
YOLO 0 tooth <- tooth_1, tooth_2
YOLO 1 arm   <- arm
~~~

为了让 1 像素和 6 像素目标都生成框，这个示例必须使用 <code>--min-pixels 1</code>。如果使用默认值 10，三种标签都会因像素不足而被过滤，最终得到空 TXT。

### 8.2 找到 tooth_1 的像素边界

ID 1 的像素坐标：

~~~text
(x, y) = (2,1), (3,1), (4,1), (2,2), (3,2), (4,2)
~~~

最小坐标：

~~~text
left = min(x) = 2
top  = min(y) = 1
~~~

最大像素索引是 <code>x=4</code>、<code>y=2</code>。代码把右、下边界定义成开区间，所以：

~~~text
right  = max(x) + 1 = 5
bottom = max(y) + 1 = 3
~~~

为什么要加 1？像素 x=4 覆盖的是连续空间区间 <code>[4, 5)</code>。如果 right 直接等于 4，三列像素会被错误算成两列宽。

### 8.3 求像素框尺寸与中心

~~~text
box_width  = right - left = 5 - 2 = 3
box_height = bottom - top = 3 - 1 = 2

center_x_pixel = (left + right) / 2 = 3.5
center_y_pixel = (top + bottom) / 2 = 2.0
~~~

### 8.4 除以图片宽高

~~~text
x_center = 3.5 / 6 = 0.58333333
y_center = 2.0 / 4 = 0.50000000
width    = 3   / 6 = 0.50000000
height   = 2   / 4 = 0.50000000
~~~

输出：

~~~text
0 0.58333333 0.50000000 0.50000000 0.50000000
~~~

### 8.5 三种标签的最终结果

| semantic label | 像素数 | YOLO ID | 输出坐标 |
|---|---:|---:|---|
| tooth_1 | 6 | 0 | <code>0.58333333 0.50000000 0.50000000 0.50000000</code> |
| tooth_2 | 1 | 0 | <code>0.08333333 0.12500000 0.16666667 0.25000000</code> |
| arm | 1 | 1 | <code>0.91666667 0.87500000 0.16666667 0.25000000</code> |

标签文件完整内容：

~~~text
0 0.58333333 0.50000000 0.50000000 0.50000000
0 0.08333333 0.12500000 0.16666667 0.25000000
1 0.91666667 0.87500000 0.16666667 0.25000000
~~~

行顺序不是按空间位置，而是：

1. 按 <code>yolo_id</code> 从小到大；
2. 同一 YOLO 类别内按 <code>semantic_labels</code> 的配置顺序。

YOLO 训练通常不依赖一张图内标签行的顺序。

### 8.6 用反算检查一行标签

已知归一化值，可还原像素边界：

~~~text
center_x_pixel = x_center × W
center_y_pixel = y_center × H
box_width_px   = width × W
box_height_px  = height × H

left   = center_x_pixel - box_width_px / 2
right  = center_x_pixel + box_width_px / 2
top    = center_y_pixel - box_height_px / 2
bottom = center_y_pixel + box_height_px / 2
~~~

对 tooth_1：

~~~text
center_x_pixel = 0.58333333 × 6 ≈ 3.5
box_width_px   = 0.5 × 6 = 3
left           = 3.5 - 1.5 = 2
right          = 3.5 + 1.5 = 5
~~~

得到原来的半开区间 <code>[2, 5)</code>。

---

## 9. 源码总览与调用链

不要从第一行到最后一行机械阅读 581 行代码。先理解分层，再进入函数。

### 9.1 四层结构

| 层 | 主要函数或对象 | 职责 |
|---|---|---|
| 数据模型层 | <code>FrameTask</code>、<code>ResolvedYoloClass</code> | 在进程间传递明确、不可变的数据 |
| 配置与发现层 | <code>load_mapping</code>、<code>load_class_config</code>、<code>discover_frame_tasks</code> | 启动前把错误挡住 |
| 单帧算法层 | <code>process_frame</code> | NPY → 像素集合 → 边界框 → TXT |
| 调度与可靠性层 | <code>main</code>、<code>atomic_write_text</code>、<code>materialize_image</code> | 并发、统计、原子写入、错误日志 |

### 9.2 主调用链

~~~mermaid
flowchart TD
    ENTRY["if __name__ == main"] --> FREEZE["multiprocessing.freeze_support()"]
    FREEZE --> MAIN["main()"]
    MAIN --> ARGS["parse_args()"]
    ARGS --> PATHS["解析绝对路径与参数关系"]
    PATHS --> MAP["load_mapping()"]
    MAP --> CONFIG["load_class_config()"]
    CONFIG --> DISCOVER["discover_frame_tasks()"]
    DISCOVER --> MKDIR["创建输出目录与 classes.txt"]
    MKDIR --> POOL["ProcessPoolExecutor"]
    POOL --> INIT["每个进程 init_worker()"]
    INIT --> FRAME["process_frame(task)"]
    FRAME --> IMAGE["materialize_image()"]
    FRAME --> LABEL["atomic_write_text()"]
    FRAME --> RESULT["返回 result 字典"]
    RESULT --> CONSUME["consume_result()"]
    CONSUME --> STATS["更新统计或 errors.jsonl.tmp"]
    STATS --> FINAL["提交或删除错误日志，打印摘要，返回退出码"]
~~~

### 9.3 两个 dataclass

#### FrameTask

保存一帧任务：

~~~python
frame_id
semantic_path
rgb_path
output_dir
~~~

路径存成字符串而不是 Path，便于多进程序列化传输。<code>frozen=True</code> 表示实例创建后不可改，有利于避免并发任务被意外修改。

#### ResolvedYoloClass

保存已经完成解析的 YOLO 类别：

~~~python
yolo_id
yolo_name
semantic_labels
semantic_ids
~~~

例如：

~~~text
ResolvedYoloClass(
    yolo_id=0,
    yolo_name="tooth",
    semantic_labels=("tooth_1", "tooth_2"),
    semantic_ids=(5, 6)
)
~~~

主进程提前完成“名称 → ID”的解析，工作进程就不必重复读取 JSON。

### 9.4 进程级全局变量

模块中有：

~~~python
_TARGET_CLASSES
_MIN_PIXELS
_OVERWRITE
_EXPECTED_DTYPE
~~~

它们由每个工作进程启动时的 <code>init_worker</code> 初始化。这样每个 <code>FrameTask</code> 不用重复携带相同配置，减少任务序列化开销。

这些全局变量属于各自进程，不是多个进程共同写的一份共享内存，所以不会发生普通线程式的数据竞争。

---

## 10. 配置加载与启动前校验

### 10.1 positive_int

argparse 默认只会把字符串转整数，但 <code>positive_int</code> 进一步确保：

~~~text
value > 0
~~~

用于 <code>workers</code>、<code>max-in-flight</code> 和 <code>min-pixels</code>。

### 10.2 parse_args

默认工作进程数：

~~~python
min(os.cpu_count() or 1, 8)
~~~

这表示：

- 能获取 CPU 逻辑核心数时，最多默认用 8；
- 获取失败时回退为 1；
- 用户仍可显式指定大于 8 的值。

默认值限制到 8 是保守策略，避免一启动就为高分辨率数组创建过多进程。

### 10.3 load_mapping

工作步骤：

1. 用 <code>utf-8-sig</code> 打开 JSON，兼容普通 UTF-8 和带 BOM 的 UTF-8。
2. 验证顶层是对象。
3. 提取 <code>classes</code> 数组。
4. 逐项校验 label 和 id。
5. 同时构造 <code>label_to_id</code> 与 <code>id_to_label</code>，借后者检查重复 ID。
6. 检查 classes 非空。
7. 若有 <code>dataset_dtype</code>，用 <code>np.dtype</code> 验证名字合法。
8. 返回 <code>(label_to_id, expected_dtype)</code>。

为什么要显式排除 bool：

~~~python
isinstance(True, int) == True
~~~

Python 的 bool 是 int 子类。如果只检查 <code>isinstance(id, int)</code>，JSON 中的 <code>true</code> 会被误当成 ID 1。

当前加载器不强制 mapping 自身的 <code>schema_version</code>。它采用“只验证自己真正依赖的字段”的兼容策略。

### 10.4 load_class_config

这个函数把用户配置与 mapping 做一次连接，类似数据库中的 join：

~~~text
semantic_labels 中的名称
        JOIN
mapping.classes.label
        ↓
semantic ID
~~~

中间的两个字典很重要：

- <code>targets_by_id</code>：检查 YOLO ID 唯一并最终排序；
- <code>used_semantic_labels</code>：保证一个语义标签只能分到一个 YOLO 类别。

最后：

~~~python
expected_ids = list(range(len(raw_targets)))
actual_ids = sorted(targets_by_id)
~~~

只有两者完全相等才通过。例如 targets 有 3 个元素，合法 ID 只能是 <code>[0, 1, 2]</code>。

连续编号的意义：

- 保证 <code>classes.txt</code> 每一行都有确定 ID；
- 避免训练配置有空洞；
- 防止用户以为只写 ID 5 就能自动创建前五类。

### 10.5 discover_frame_tasks

函数分两遍扫描目录：

1. semantic 文件构造成 <code>frame_id → path</code>；
2. RGB 文件构造成 <code>frame_id → path</code>。

然后计算集合差：

~~~text
semantic 帧集合 - RGB 帧集合 = 缺少 RGB
RGB 帧集合 - semantic 帧集合 = 缺少 NPY
~~~

只要任一集合非空，就在创建输出目录之前整体失败。

这是“fail fast”设计：数据配对问题属于数据集级错误，不应该一边转换一边留下半套输出。

函数最终按 frame ID 的字符串字典序排序。例如：

~~~text
1, 10, 2
~~~

会按字符串顺序而不是数值顺序处理。建议统一使用零填充：

~~~text
0001, 0002, 0010
~~~

排序只影响处理和提交顺序，不影响配对正确性。

### 10.6 main 中的路径安全检查

输出目录不能：

- 等于 RGB 目录；
- 位于 RGB 目录内部；
- 包含 RGB 目录；
- 等于 semantic 目录；
- 位于 semantic 目录内部；
- 包含 semantic 目录。

这样能防止输出图片再次被扫描成输入，或因复用同一目录造成污染。

mapping 和 class config 可以在其他位置；代码只对两个批量数据目录实施这种互不包含检查。

---

## 11. 单帧转换算法逐句拆解

<code>process_frame</code> 是项目的算法核心。

### 11.1 第一步：决定跳过还是处理

标签路径由 RGB 文件名派生：

~~~text
rgb_0000.png -> rgb_0000.txt
~~~

若 TXT 已存在且未设置 <code>--overwrite</code>：

1. 确保输出图片存在；
2. 返回 <code>status="skipped"</code>；
3. 不读取 NPY；
4. 不校验这一帧的尺寸和 dtype；
5. 不统计旧标签中的框。

这是断点续跑速度快的原因，也是使用旧输出时必须谨慎的原因。

### 11.2 第二步：安全加载 semantic NPY

~~~python
semantic = np.load(
    semantic_path,
    mmap_mode="r",
    allow_pickle=False
)
~~~

随后检查：

- <code>semantic.ndim == 2</code>；
- 实际 dtype 是否等于 mapping 声明；
- <code>semantic.shape == (image_height, image_width)</code>。

图片只通过 Pillow 打开以读取尺寸，<code>with</code> 块结束后文件句柄立即关闭。

### 11.3 第三步：一次找出所有目标像素

先把所有配置目标的 semantic ID 展平：

~~~text
(tooth_1 id, tooth_2 id, arm id, ...)
~~~

然后：

~~~python
target_mask = np.isin(semantic, target_semantic_ids)
all_y, all_x = np.nonzero(target_mask)
semantic_ids = semantic[all_y, all_x]
~~~

得到三个对齐的一维数组：

| 数组 | 内容 |
|---|---|
| <code>all_y</code> | 每个目标像素的 y |
| <code>all_x</code> | 每个目标像素的 x |
| <code>semantic_ids</code> | 该目标像素的 semantic ID |

这比针对每个类别重复对整幅 H×W 数组调用 <code>nonzero</code> 更集中，但仍会创建一个 H×W 布尔 <code>target_mask</code>。

### 11.4 第四步：逐 semantic label 求框

外层按 YOLO 类别，内层按该类配置的 semantic label：

~~~python
selected = semantic_ids == semantic_id
pixel_count = np.count_nonzero(selected)
~~~

三种情况：

| 像素数 | 行为 |
|---:|---|
| 0 | 这一帧没有该标签，直接继续 |
| 1 到 <code>min_pixels - 1</code> | 记一次 small mask，不生成框 |
| 大于等于 <code>min_pixels</code> | 计算最小外接矩形 |

注意，<code>small_masks</code> 统计的是“被过滤的标签掩码数”，不是被过滤像素总数。

### 11.5 第五步：计算半开边界

~~~python
left = x_values.min()
right = x_values.max() + 1
top = y_values.min()
bottom = y_values.max() + 1
~~~

得到半开矩形：

~~~text
[left, right) × [top, bottom)
~~~

它能正确表示单像素框：若目标只有 <code>(x=5, y=3)</code>，

~~~text
left=5, right=6, width=1
top=3, bottom=4, height=1
~~~

### 11.6 第六步：归一化与防御性检查

坐标公式：

~~~text
x_center = (left + right) / 2 / image_width
y_center = (top + bottom) / 2 / image_height
width    = (right - left) / image_width
height   = (bottom - top) / image_height
~~~

写出前还检查：

- 四个值都是有限数，不是 NaN 或无穷；
- 中心在闭区间 0～1；
- 宽高在区间 <code>(0, 1]</code>。

正常二维整数索引本来就应满足这些条件。保留检查可以防止未来修改算法后悄悄写出坏标签。

### 11.7 第七步：格式化

每个浮点数固定保留 8 位小数：

~~~python
f"{value:.8f}"
~~~

优点：

- 输出稳定、便于 diff；
- 精度足以覆盖常见图像尺寸；
- 不受 Python 默认科学计数法影响。

### 11.8 第八步：先物化图片，再原子写标签

顺序是：

1. <code>materialize_image</code>；
2. <code>atomic_write_text</code>。

如果图片阶段失败，就不会出现一个看似完整的新 TXT。标签成功写出时，图片通常已经就位。

### 11.9 第九步：把帧内异常变成结果

<code>process_frame</code> 捕获所有普通异常，并返回：

~~~json
{
  "status": "error",
  "frame_id": "0000",
  "semantic_path": "...",
  "rgb_path": "...",
  "message": "ValueError: 尺寸不一致...",
  "boxes": 0,
  "empty": false,
  "small_masks": 0
}
~~~

这样一帧坏数据不会杀掉整个批次。主进程可以继续消费其余帧，并把错误写入 JSON Lines。

### 11.10 最重要的算法边界

同一个 semantic label 在图中如果出现两个互不相连区域：

~~~text
###........###
###........###
~~~

当前算法对这个 label 的所有像素统一求 min/max，会得到横跨中间空白区域的一个大框。

这可能有两种解释：

- 如果 semantic label 代表唯一对象，遮挡导致区域断开，合成一个框可能正确；
- 如果同一 label 被多个对象复用，合成一个框通常错误，需要实例 ID 或连通域拆分。

---

## 12. 批量并发、内存与可靠性设计

### 12.1 为什么用进程池

每帧包含 NumPy 筛选、nonzero、比较和 min/max。使用 <code>ProcessPoolExecutor</code> 可以让多帧在多个 Python 进程中处理。

NumPy 的一些运算会释放 GIL，但进程池还能隔离每帧状态，并在 Windows 和 Linux 上提供一致的任务模型。

### 12.2 bounded in-flight 的含义

朴素写法可能一次把百万帧全部 <code>submit</code> 到 executor，产生大量 Future 和排队对象。本项目维护 <code>pending</code> 字典：

~~~text
提交任务
  ↓
pending 数量达到 max_in_flight
  ↓
wait(..., FIRST_COMPLETED)
  ↓
消费至少一个结果并从 pending 删除
  ↓
继续提交
~~~

因此尚未消费的 Future 数量不会长期超过配置值。

需要准确区分两件事：

- <code>discover_frame_tasks</code> 会先把所有轻量的 FrameTask 保存在一个 tuple 中；
- 真正的 NPY 数据不会一次全部加载，只有工作进程正在处理的少量帧会读取数组。

所以它控制的是“大数组处理并发”和 Future 数量，不是流式扫描到连任务元数据都不保存。

### 12.3 max-in-flight 与 workers

若：

~~~text
workers = 8
max_in_flight = 16
~~~

最多 8 个进程同时执行，另有少量任务排队或等待主进程消费。把 max-in-flight 设得远大于 workers 通常不会显著增加吞吐，只会增加排队状态。

推荐起点：

| 数据规模与机器 | workers | max-in-flight |
|---|---:|---:|
| 排错 | 1 | 1 |
| 低内存或超高分辨率 | 2 | 4 |
| 普通 8 核机器 | 4～8 | workers × 2 |
| 机械硬盘、I/O 已饱和 | 2～4 | workers × 2 |

实际最优值要用同一批数据测量，不能只看 CPU 核数。

### 12.4 单帧大致内存组成

即使 NPY 使用内存映射，处理时仍可能产生：

- H×W 的布尔 <code>target_mask</code>；
- 长度为目标像素数的 <code>all_x</code> 和 <code>all_y</code>；
- 长度为目标像素数的 <code>semantic_ids</code>；
- 每个 semantic label 临时创建的布尔 <code>selected</code>；
- Pillow 解码图片元数据时的少量开销。

因此“mmap”不等于“几乎不占内存”。目标像素很密、分辨率很高、workers 很大时，峰值内存仍会明显上升。

### 12.5 Windows 多进程入口

文件末尾的：

~~~python
if __name__ == "__main__":
    multiprocessing.freeze_support()
~~~

非常关键。Windows 工作进程会重新导入模块；如果进程池创建不在 main 保护下，可能递归创建子进程。

<code>freeze_support()</code> 还改善程序被打包成可执行文件时的多进程兼容性。

### 12.6 原子写标签

<code>atomic_write_text</code>：

1. 在目标目录创建带进程 ID 的临时文件；
2. 写入文本；
3. flush Python 缓冲区；
4. <code>os.fsync</code> 请求把内容同步到底层存储；
5. 用 <code>os.replace</code> 原子替换目标；
6. finally 中清理残余临时文件。

流程：

~~~text
rgb_0000.txt.12345.tmp
        ↓ 完整写入并 fsync
os.replace
        ↓
rgb_0000.txt
~~~

程序中断时，旧标签要么保持不变，要么新标签已经完整替换；不会把半行内容当成最终 TXT。

“原子”依赖临时文件和目标在同一目录、同一文件系统。本实现正是这样创建临时文件的。

### 12.7 图片硬链接与复制回退

<code>materialize_image</code>：

1. 如果目标图片已存在，立即返回；
2. 尝试 <code>os.link</code> 创建硬链接临时文件；
3. 若硬链接失败，使用 <code>shutil.copy2</code>；
4. 原子替换成最终文件名；
5. 清理临时文件。

硬链接的特点：

- 不重复占用文件数据空间；
- 必须在同一文件系统/卷；
- 源和输出是同一个底层文件内容；
- 删除一个目录项通常不会删除另一个目录项指向的数据；
- 修改其中一处文件内容会影响另一处看到的内容。

所以生成数据集后，不要原地编辑硬链接图片。若需要独立副本，应显式复制或让输入输出跨卷触发复制回退。

### 12.8 错误日志的提交

处理时先写 <code>errors.jsonl.tmp</code>。结束后：

- 有失败：原子改名为 <code>errors.jsonl</code>；
- 无失败：删除临时文件，并保证旧 <code>errors.jsonl</code> 已被清理。

JSONL 是“一行一个 JSON 对象”，适合边处理边追加，也便于脚本逐行解析：

~~~python
import json
from pathlib import Path

for line in Path("errors.jsonl").read_text(encoding="utf-8").splitlines():
    error = json.loads(line)
    print(error["frame_id"], error["message"])
~~~

---

## 13. 测试代码怎么读、怎么跑

### 13.1 为什么先读测试

测试代码展示了最小可运行输入，比直接面对真实的几千帧数据更容易理解：

- 用 <code>TemporaryDirectory</code> 隔离测试文件；
- 用 NumPy 创建二维 ID 数组；
- 用 Pillow 创建指定尺寸 RGB；
- 用 json 模块生成 mapping 和类别配置；
- 既直接调用函数，也通过 subprocess 测试 CLI。

### 13.2 测试夹具 setUp

每个测试开始前创建：

~~~text
temporary_root/
├── rgb/
├── semantic_id/
├── output/
└── semantic_mapping.json
~~~

固定 mapping：

~~~text
1 -> tooth_1
2 -> tooth_2
3 -> arm
dtype = uint16
~~~

每个测试结束后临时目录自动清理，不污染仓库。

### 13.3 五个现有测试

#### test_split_directories_and_dynamic_classes

验证：

- RGB 和 semantic 可以位于不同目录；
- 一个 YOLO 类别可接收多个 semantic label；
- 多类别 ID 正确写入；
- 图片被物化到输出目录。

它把 <code>min_pixels</code> 设为 1，所以 1 像素目标也会生成框。

#### test_missing_mapping_label_is_rejected

配置中使用 <code>not_in_mapping</code>，确认加载类别配置时立即抛出 ValueError。

这证明标签错误发生在创建批处理任务之前，而不是处理到某一帧才发现。

#### test_cli_end_to_end

不直接调用 <code>main</code>，而是通过当前 Python 解释器启动 <code>convert.py</code>，验证：

- 命令行参数解析；
- Windows 子进程编码；
- 进程池；
- 返回码；
- <code>classes.txt</code>；
- YOLO TXT。

这是最接近用户真实运行方式的测试。

#### test_yolo_ids_must_be_contiguous

只配置 ID 1，没有 ID 0，确认被拒绝。

#### test_unpaired_frames_are_rejected_before_processing

只创建 NPY，不创建 RGB，确认帧发现阶段报“缺少 RGB”。

### 13.4 运行测试

进入项目目录后：

~~~powershell
python -m unittest -v
~~~

期望看到：

~~~text
Ran 5 tests
OK
~~~

为什么推荐 <code>python -m unittest</code> 而不是直接输入 <code>unittest</code>：

- 明确使用当前虚拟环境的 Python；
- unittest 是标准库，不需要额外安装 pytest；
- 项目测试文件有标准的 unittest 入口。

也可以只运行一个测试：

~~~powershell
python -m unittest -v test_convert.ConvertTests.test_cli_end_to_end
~~~

### 13.5 现有测试尚未覆盖什么

测试通过说明已覆盖功能正常路径和几个关键校验，但不等于所有边界都已验证。值得补充：

- 精确断言四个坐标值；
- 默认 <code>min_pixels=10</code> 的边界：9、10、11 像素；
- 空标签文件；
- dtype 不一致；
- NPY 非二维；
- NPY 与 RGB 尺寸不一致；
- <code>--overwrite</code>；
- 已有 TXT 的跳过行为；
- 图片硬链接失败后的复制回退；
- 单帧错误产生 <code>errors.jsonl</code> 和退出码 1；
- 键盘中断和残余临时文件；
- 多帧并发输出；
- 重复 label、重复 ID、重复 yolo_name；
- 输出目录与输入目录互相包含。

测试覆盖是“风险地图”，不是只追求数量。坐标数学、覆盖行为和失败日志最值得优先补。

---

## 14. 断点续跑、覆盖和退出码

### 14.1 默认断点续跑

判断依据只有：

~~~text
输出目录中对应 TXT 是否存在
~~~

默认情况下：

| TXT | 图片 | 行为 |
|---|---|---|
| 不存在 | 不存在 | 正常处理，放图片，写 TXT |
| 不存在 | 已存在 | 正常处理，不替换图片，写 TXT |
| 已存在 | 不存在 | 跳过计算，补图片 |
| 已存在 | 已存在 | 整帧跳过 |

空 TXT 也是合法的完整负样本，因此“文件大小为 0”不会触发重算。

### 14.2 --overwrite 做了什么

启用后会重新读取 NPY 并替换 TXT，但要注意：

- <code>classes.txt</code> 每次运行都会重写；
- TXT 会重写；
- 已存在的输出 PNG 不会重写；
- 旧的、已不再配对的额外 TXT/PNG 不会自动删除。

所以若输入图片内容改变但文件名不变，单纯使用 <code>--overwrite</code> 仍可能保留旧输出图片。最稳妥的方法是换一个全新输出目录。

### 14.3 更换类别配置时的危险组合

假设第一次：

~~~text
YOLO 0 = tooth
YOLO 1 = arm
~~~

第二次复用输出目录，但改成：

~~~text
YOLO 0 = arm
YOLO 1 = tooth
~~~

程序会立刻重写 <code>classes.txt</code>，却默认跳过已有 TXT。这样旧 TXT 的类别 0 仍表示 tooth，而新 classes 第 0 行变成 arm，数据集语义被静默破坏。

因此：

> 只要 mapping、类别配置、min-pixels 或输入内容发生变化，优先使用新的输出目录；若确认图片不变且需要复用目录，至少使用 --overwrite，并检查是否有陈旧的额外文件。

### 14.4 退出码

| 退出码 | 来源 | 含义 |
|---:|---|---|
| 0 | <code>main</code> | 全部新处理帧成功，或只有跳过帧 |
| 1 | <code>main</code> | 至少一帧失败，详见 errors.jsonl |
| 2 | 顶层异常处理 | 启动、参数关系、配置、目录、帧配对等批次级错误 |
| 130 | KeyboardInterrupt | 用户按 Ctrl+C 中断 |

argparse 自身遇到缺参或非法正整数时通常也使用退出码 2，并打印 usage。

### 14.5 Ctrl+C 后能否继续

已通过原子替换完成的 TXT 仍然有效。重新运行时会跳过它们。

但中断时可能存在：

- 尚未完成的图片或标签临时文件；
- <code>errors.jsonl.tmp</code>；
- 已提交但尚未消费的工作进程。

下一次运行会清理它准备使用的同名临时路径；带旧进程 ID 的极端残余临时文件可能需要人工检查。不要把 <code>*.tmp</code> 当成正式标注。

---

## 15. 常见故障与系统化排查

排查顺序建议固定为：

~~~text
路径存在性
  ↓
文件命名与帧配对
  ↓
JSON 结构和标签名称
  ↓
NPY 维度、dtype、尺寸
  ↓
min-pixels 和目标 ID
  ↓
输出目录旧文件
  ↓
并发、权限、磁盘
~~~

### 15.1 “RGB 目录不存在”或“semantic 目录不存在”

常见原因：

- PowerShell 相对路径基于错误当前目录；
- 路径含空格却没加双引号；
- 在 Windows 命令里使用了 Linux 路径；
- 把 mapping 文件路径误传给目录参数。

检查：

~~~powershell
Test-Path "D:\your_dataset\rgb" -PathType Container
Test-Path "D:\your_dataset\semantic_id" -PathType Container
~~~

### 15.2 “缺少 RGB 的帧”或“缺少 semantic NPY 的帧”

先列出中间帧 ID，而不是只看数量：

~~~python
from pathlib import Path

rgb_dir = Path(r"D:\your_dataset\rgb")
sem_dir = Path(r"D:\your_dataset\semantic_id")

rgb_ids = {
    p.name[len("rgb_"):-len(".png")]
    for p in rgb_dir.glob("rgb_*.png")
}
sem_ids = {
    p.name[len("semantic_id_"):-len(".npy")]
    for p in sem_dir.glob("semantic_id_*.npy")
}

print("缺 RGB:", sorted(sem_ids - rgb_ids))
print("缺 NPY:", sorted(rgb_ids - sem_ids))
~~~

还要检查后缀大小写。Python 的 glob 在不同平台可能表现不同，而项目源码使用严格的字符串 <code>endswith</code>。

### 15.3 “语义标签不在 mapping 中”

说明类别配置中的名字与 mapping 的 <code>classes[].label</code> 不完全一致。

可能是：

- <code>tooth_01</code> 和 <code>tooth_1</code> 混淆；
- 大小写不同；
- 标签前后有不可见字符；
- 用了上一次采集的 mapping；
- 目标写在 mapping 的 background/unknown 而不是 classes。

程序会对首尾普通空白调用 <code>strip</code>，但不会自动统一大小写或编号格式。

### 15.4 “dtype=uint32，mapping 声明为 uint16”

mapping 声明了期望 dtype，NPY 实际 dtype 不同。

检查：

~~~python
import numpy as np

arr = np.load(r"D:\your_dataset\semantic_id\semantic_id_0000.npy",
              mmap_mode="r", allow_pickle=False)
print(arr.shape, arr.ndim, arr.dtype)
~~~

不要为了让转换器通过就盲目修改 mapping。先确认上游采集是否用了正确 dtype，以及数值范围能否安全转成 uint16。

### 15.5 “尺寸不一致”

错误信息中的顺序：

~~~text
NPY shape=(H, W)
RGB size=(W, H)
~~~

若恰好反过来，可能是上游保存 semantic 时错误转置。也可能 RGB 后处理缩放过，而 NPY 没同步缩放。

不要只在此脚本里随意 resize 掩码。语义 ID 图若确需缩放，必须使用最近邻插值，否则会生成不存在的新类别值。

### 15.6 运行成功但 TXT 是空的

空 TXT 可以是正常负样本。依次检查：

1. 目标 semantic ID 是否真的出现在 NPY；
2. 出现像素数是否小于 <code>min-pixels</code>；
3. 类别配置是否选中了想要的标签；
4. 输出是否是旧的跳过文件；
5. NPY 是否属于同一版 mapping。

快速查看 ID 和像素数：

~~~python
from collections import Counter
import numpy as np

arr = np.load(r"D:\your_dataset\semantic_id\semantic_id_0000.npy",
              mmap_mode="r", allow_pickle=False)
ids, counts = np.unique(arr, return_counts=True)
print(dict(zip(ids.tolist(), counts.tolist())))
~~~

### 15.7 框异常地覆盖很大区域

最常见原因是同一个 semantic label 在多个不相连对象上复用。当前代码会把该 label 全部像素合成一个最小外接矩形。

可视化检查方法：

- 读取 RGB；
- 反算 TXT 坐标；
- 用 Pillow 或 OpenCV 画框；
- 同时把 semantic ID 的二值掩码画成透明叠加。

如果框包住多个独立物体，需要上游提供实例级 ID，或扩展连通域分析。

### 15.8 修改配置后结果没有变化

已有 TXT 被默认跳过。使用新输出目录最安全；否则：

~~~powershell
python convert.py ... --overwrite
~~~

并确认输出 PNG 是否也需要更新，因为 overwrite 不替换已有图片。

### 15.9 部分失败但终端继续运行

这是设计行为。单帧异常写入 <code>errors.jsonl</code>，其余帧继续。结束时退出码为 1。

PowerShell 获取上一条命令退出码：

~~~powershell
$LASTEXITCODE
~~~

自动化流水线不要只搜索“转换完成”文字，要判断退出码。

### 15.10 中文乱码

Windows 上源码会重新配置 stdout 和 stderr 为 UTF-8。若外层终端仍乱码，可尝试：

~~~powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
python convert.py --help
~~~

若把输出重定向到旧式工具，还需确认该工具按 UTF-8 解码。

### 15.11 PermissionError 或硬链接失败

硬链接失败会自动回退到复制，通常不会直接导致整帧失败。若复制也失败，检查：

- 输出目录写权限；
- 源文件读取权限；
- 磁盘空间；
- 防病毒或同步软件占用；
- 路径长度；
- 网络盘/特殊文件系统行为。

### 15.12 内存高或速度反而变慢

不要第一反应把 workers 调更大。尝试：

1. 降到 workers 1，记录基线；
2. 测 2、4、8；
3. 同时观察 CPU、磁盘吞吐和内存；
4. 保持 max-in-flight 约为 workers 的 2 倍；
5. 使用本地 SSD 而不是网络盘；
6. 若目标像素很密，关注 all_x/all_y 数组开销。

---

## 16. 如何接入 YOLO 训练流程

### 16.1 当前输出为何还不是典型 Ultralytics 数据集

当前是扁平目录，图片和标签放在一起。现代 YOLO 工具常用：

~~~text
dataset_yolo/
├── images/
│   ├── train/
│   └── val/
├── labels/
│   ├── train/
│   └── val/
└── data.yaml
~~~

因此转换完成后通常还需要“切分与整理”步骤。

### 16.2 配对切分的原则

切分单位必须是帧对：

~~~text
rgb_0000.png + rgb_0000.txt
~~~

绝不能单独随机图片和 TXT，否则配对会破坏。

还应避免数据泄漏。如果连续帧高度相似，不建议逐帧完全随机切分；更合理的是按：

- 仿真场景；
- 采集回合；
- 相机轨迹；
- 时间区段；
- 随机种子；

进行分组切分，让验证集真正检验泛化。

### 16.3 data.yaml 示例

假设整理后类别为 tooth、arm：

~~~yaml
path: D:/dataset_yolo
train: images/train
val: images/val

names:
  0: tooth
  1: arm
~~~

YAML 中的 names 顺序必须与：

- <code>classes.txt</code>；
- 类别配置中的 <code>yolo_id</code>；
- 所有 TXT 第一列；

完全一致。

### 16.4 空 TXT 要不要保留

要。没有目标的图片是合法负样本，能帮助模型学习背景，减少误检。

但负样本比例也需要控制。若 99% 图片都是空标签，训练会严重失衡。转换摘要中的“空标签帧数”可作为第一步监控，完整比例还要把跳过帧重新统计进去。

### 16.5 训练前的质量检查

至少完成：

1. 随机抽样画框；
2. 确认 class ID 没越界；
3. 所有非空行恰有 5 列；
4. 四个坐标满足范围；
5. 图片与 TXT 基名一一对应；
6. 统计每类框数量；
7. 统计空标签比例；
8. 检查异常大框、极小框；
9. 检查 train 与 val 是否有近重复帧；
10. 固化 mapping、class config、切分清单和转换参数。

<code>classes.txt</code> 只表示名称，不记录 mapping 版本、min-pixels 和输入来源。正式实验应额外保存一份数据集 manifest。

---

## 17. 当前限制与二次开发路线

### 17.1 能力边界总表

| 主题 | 当前行为 | 影响 |
|---|---|---|
| 实例拆分 | 不拆连通域 | 同 label 多实例会合成大框 |
| 类别匹配 | 精确字符串 | 安全可控，但无通配符 |
| 类别合并 | 多 label 可映射同 YOLO 类 | 每个 label 仍分别出框 |
| 图片处理 | 不缩放、不重编码 | 坐标稳定，输出尺寸不可统一 |
| 输出结构 | 图片与 TXT 扁平混放 | 训练前需整理 |
| 数据切分 | 无 | 需单独实现 |
| YAML | 无 | 需单独创建 |
| 断点依据 | TXT 是否存在 | 快，但不校验旧标签版本 |
| 图片覆盖 | 从不覆盖已有图片 | 输入更新时可能保留旧图 |
| 配置追踪 | 仅 classes.txt | 无完整可复现 manifest |
| 帧发现 | 全部 FrameTask 先放 tuple | 海量帧时仍有元数据内存 |
| 排序 | 字符串字典序 | 非零填充数字顺序不直观 |
| 框类型 | 轴对齐矩形 | 不支持旋转框、分割多边形 |

### 17.2 路线一：增加可视化质检工具

这是最推荐的第一个扩展，因为任何算法优化都要先看得见。

输入：

- 输出 RGB；
- YOLO TXT；
- classes.txt。

输出：

- 带彩色矩形和类别名的预览图；
- 可选的异常统计。

核心反算：

~~~text
left   = (x_center - width / 2) × W
right  = (x_center + width / 2) × W
top    = (y_center - height / 2) × H
bottom = (y_center + height / 2) × H
~~~

建议为可视化工具写独立脚本，不要让转换核心承担交互显示职责。

### 17.3 路线二：按连通域拆框

思路：

1. 为单个 semantic ID 得到二值 mask；
2. 做 4 邻域或 8 邻域连通域标记；
3. 对每个连通区域分别计算像素数与边界框；
4. 每个区域应用 min-pixels；
5. 输出多行相同 YOLO class ID。

需要先决定：

- 4 连通还是 8 连通；
- 小碎片阈值；
- 被遮挡成两块的同一实例是否应合并；
- 是否已有更可靠的实例分割 ID。

如果上游能输出实例 ID，优先用实例 ID；语义连通域只是图像空间启发式方法。

### 17.4 路线三：生成完整训练目录与 YAML

可以增加独立的后处理脚本：

~~~text
convert.py
  ↓ 扁平、完整、一一配对输出
split_dataset.py
  ↓ 固定随机种子、按组切分
images/train, labels/train, images/val, labels/val
  ↓
data.yaml + split_manifest.json
~~~

分开脚本的好处是转换和数据集策略解耦。同一份转换结果可以尝试不同切分方案。

### 17.5 路线四：增加数据集 manifest

建议记录：

~~~json
{
  "converter": "260715_01GenerateYoloData",
  "mapping_sha256": "...",
  "class_config_sha256": "...",
  "min_pixels": 10,
  "frame_count": 1000,
  "created_at": "...",
  "source_rgb_dir": "...",
  "source_semantic_dir": "..."
}
~~~

断点续跑前比较 manifest；配置或输入指纹改变就拒绝混用旧输出，能消除 classes.txt 与旧 TXT 不一致的风险。

### 17.6 路线五：真正的流式帧发现

当前 <code>discover_frame_tasks</code> 返回 tuple，所有路径元数据先进入内存。若帧数达到百万级，可改成：

1. 先建立较小一侧的 frame 索引，或从 manifest 读取帧清单；
2. 校验配对；
3. 返回 iterator；
4. 主循环有界提交。

但不要为省少量元数据内存牺牲“处理前发现全部配对错误”的保障。可先生成经过校验的帧 manifest，再流式读取 manifest。

### 17.7 路线六：提升错误可诊断性

可为 errors.jsonl 增加：

- 异常阶段：load_npy、validate_shape、compute_box、write_image、write_label；
- NPY shape 和 dtype；
- RGB size；
- 处理进程 ID；
- 可选 traceback；
- 配置和 mapping 指纹。

生产环境中要避免把敏感的绝对路径无条件发送到外部日志系统。

### 17.8 扩展时应保持的设计原则

- 启动前验证数据集级错误；
- 单帧错误不拖垮全批；
- 最终标签原子写入；
- 任务提交有界；
- 配置明确，不依赖隐式命名猜测；
- 输出应可复现；
- 新行为必须配对应测试；
- 算法变化不要静默复用旧结果。

---

## 18. 循序渐进练习与答案

### 练习 1：判断 shape

RGB 尺寸是 1280×720。NPY 的合法 shape 是什么？

<details>
<summary>答案</summary>

<code>(720, 1280)</code>。NumPy 顺序是高度、宽度。

</details>

### 练习 2：单像素框

图片宽 10、高 8，目标只有像素 <code>(x=0, y=0)</code>。使用 min-pixels 1，求 YOLO 坐标。

<details>
<summary>答案</summary>

边界是 left=0、right=1、top=0、bottom=1。

~~~text
x_center = 0.5 / 10 = 0.05
y_center = 0.5 / 8  = 0.0625
width    = 1 / 10   = 0.1
height   = 1 / 8    = 0.125
~~~

</details>

### 练习 3：阈值边界

<code>min-pixels=10</code> 时，一个 semantic label 有 9、10、11 个像素，分别发生什么？

<details>
<summary>答案</summary>

9 被过滤并使 small_masks 加 1；10 和 11 都生成框。判断条件是 <code>pixel_count &lt; min_pixels</code>。

</details>

### 练习 4：类别合并

tooth_1 和 tooth_2 都映射为 YOLO 0。如果一帧两者都出现，会生成几行？

<details>
<summary>答案</summary>

通常两行，每个 semantic label 一行，前提是各自像素数都达到阈值。它们的 class ID 都是 0。

</details>

### 练习 5：为什么 ID 不能从 1 开始

只有两个类别，配置为 yolo_id 1 和 2，程序为什么拒绝？

<details>
<summary>答案</summary>

两个 target 要求实际 ID 精确为 <code>[0, 1]</code>。从 0 连续编号保证 classes.txt 的第 N 行与 ID N 一致。

</details>

### 练习 6：断点续跑统计

输出目录已有 90 帧 TXT，新运行处理 10 帧，每帧 2 个框。最终控制台“生成 YOLO 框”是多少？

<details>
<summary>答案</summary>

20，不是完整数据集的 200。90 个跳过帧不会重新读取旧标签统计框。

</details>

### 练习 7：找出潜在污染

先用配置 A 生成标签，再改配置 B，不加 overwrite 复用输出目录。为什么危险？

<details>
<summary>答案</summary>

classes.txt 会按 B 重写，旧 TXT 却被跳过并仍使用 A 的 ID 语义，造成类名与标签不一致。

</details>

### 练习 8：设计一个新测试

为“尺寸不一致”写测试时，最小安排是什么？

<details>
<summary>答案</summary>

创建例如 shape=(4,6) 的 uint16 NPY，创建尺寸 (7,4) 的 RGB，加载配置、发现任务、初始化 worker，调用 process_frame，断言返回 status 为 error 且 message 含“尺寸不一致”。也可通过 CLI 断言退出码 1 和 errors.jsonl。

</details>

### 练习 9：性能推理

workers 从 4 增加到 16 后速度下降，最可能说明什么？

<details>
<summary>答案</summary>

不一定是代码错误。可能是磁盘 I/O 饱和、内存带宽竞争、每进程临时数组导致内存压力、进程调度开销超过收益。应测量 1、2、4、8 的基线并观察 CPU、磁盘和内存。

</details>

### 练习 10：二次开发决策

同一 semantic label 被多个相同物体复用。应优先连通域拆分还是实例 ID？

<details>
<summary>答案</summary>

优先让上游提供稳定实例 ID。连通域会把被遮挡成两块的同一物体误拆，也可能把接触的两个物体误合并，只适合作为没有实例信息时的近似方案。

</details>

---

## 19. 术语表与速查表

### 19.1 术语

| 术语 | 本项目中的含义 |
|---|---|
| frame | 同一个帧 ID 的一张 RGB 与一个 NPY |
| semantic label | 人类可读语义名，如 tooth_1 |
| semantic ID | NPY 中存储的整数类别值 |
| YOLO class | 训练任务希望模型预测的类别 |
| mapping | semantic label 与 semantic ID 的稳定对应表 |
| mask | 满足某个条件的一组像素，通常是布尔数组 |
| bounding box | 包围目标像素的轴对齐最小矩形 |
| normalize | 将像素坐标除以图片宽高变到 0～1 |
| negative sample | 图片中没有配置目标，TXT 为空 |
| hard link | 多个文件名指向同一底层文件数据 |
| atomic replace | 最终文件只以完整旧版或完整新版出现 |
| worker | 进程池中实际处理帧的子进程 |
| Future | 代表尚未完成或已完成异步任务的对象 |
| in-flight | 已提交但主进程尚未消费完的任务 |
| JSONL | 每行一个独立 JSON 对象的日志格式 |

### 19.2 命令速查

安装：

~~~powershell
python -m pip install -r requirements.txt
~~~

帮助：

~~~powershell
python convert.py --help
~~~

测试：

~~~powershell
python -m unittest -v
~~~

保守试跑：

~~~powershell
python convert.py --rgb-dir "D:\data\rgb" --semantic-dir "D:\data\semantic_id" --mapping "D:\data\semantic_mapping.json" --class-config ".\yolo_classes.json" --output "D:\data_yolo" --workers 1 --max-in-flight 1 --min-pixels 10
~~~

覆盖标签：

~~~powershell
python convert.py ... --overwrite
~~~

查看退出码：

~~~powershell
$LASTEXITCODE
~~~

查看错误：

~~~powershell
Get-Content "D:\data_yolo\errors.jsonl"
~~~

### 19.3 源码阅读速查

| 想理解的问题 | 首先看 |
|---|---|
| 参数从哪里来 | <code>parse_args</code> |
| mapping 为什么报错 | <code>load_mapping</code> |
| class config 为什么报错 | <code>load_class_config</code> |
| 两类文件如何配对 | <code>discover_frame_tasks</code> |
| 框怎么算 | <code>process_frame</code> |
| 标签如何安全写 | <code>atomic_write_text</code> |
| 图片为何没复制占空间 | <code>materialize_image</code> |
| 如何限制排队任务 | <code>main</code> 中 pending 与 wait |
| 错误如何汇总 | <code>consume_result</code> 与 <code>write_error</code> |
| Windows 多进程为何正常 | main 保护与 <code>freeze_support</code> |

### 19.4 运行前十项清单

- [ ] RGB 和 NPY 帧 ID 完全配对。
- [ ] NPY 是二维 <code>(H, W)</code>。
- [ ] RGB 是 <code>(W, H)</code> 且尺寸对应。
- [ ] NPY dtype 与 mapping 一致。
- [ ] 类别配置中的标签全部存在于 mapping classes。
- [ ] yolo_id 从 0 连续编号。
- [ ] min-pixels 符合目标大小，不会误删小目标。
- [ ] 输出目录不与输入目录相同或互相包含。
- [ ] 配置变化时使用新输出目录或明确 overwrite。
- [ ] 先 workers 1 小规模试跑并可视化抽检。

---

## 20. 本教程的实际验证记录

教程不是只根据代码静态推测。2026-07-21 在当前工作区完成了以下验证。

### 20.1 环境

~~~text
Python 3.9.18
NumPy 1.26.4
Pillow 10.2.0
Windows PowerShell
~~~

### 20.2 自动化测试

执行：

~~~powershell
python -m unittest -v
~~~

结果：

~~~text
Ran 5 tests
OK
~~~

五项测试全部通过。

### 20.3 仓库真实采集帧

还读取了上游语义采集项目中的一帧真实样例：

~~~text
RGB size = (640, 360)
NPY shape = (360, 640)
NPY dtype = uint16
~~~

临时配置：

~~~text
YOLO 0 forklift <- body, lift
YOLO 1 room     <- SimpleRoom
min-pixels = 10
workers = 1
max-in-flight = 1
~~~

实际转换结果：

~~~text
发现帧数：1
成功帧数：1
失败帧数：0
生成 YOLO 框：3
~~~

标签：

~~~text
0 0.48671875 0.45972222 0.25468750 0.91944444
0 0.80703125 0.46388889 0.38593750 0.92777778
1 0.49687500 0.95833333 0.86562500 0.08333333
~~~

这同时验证了：

- 独立 RGB 与 semantic 目录；
- uint16 mapping dtype；
- 640×360 尺寸对应；
- 多个 semantic label 映射到一个 YOLO class；
- 多 YOLO 类别；
- 进程池 CLI 端到端；
- 图片和标签输出；
- 类别名称顺序。

临时验证目录在测试结束后已自动清理，没有把样例输出写入项目目录。

---

## 结语：建议你的实际学习动作

按下面顺序亲手做一遍，比只读文档有效：

1. 运行 <code>python -m unittest -v</code>。
2. 在纸上重算第 8 章的 6×4 示例。
3. 打开 <code>test_convert.py</code>，找到示例数组如何被构造。
4. 打开 <code>convert.py</code>，从 <code>main</code> 顺着调用链进入 <code>process_frame</code>。
5. 用自己的一帧数据、workers 1 和全新输出目录试跑。
6. 把输出框画回 RGB，检查像素边界。
7. 修改 min-pixels，对比空标签和小掩码统计。
8. 修改 class config，并用新输出目录观察 classes.txt 与 TXT 第一列。
9. 主动制造一次尺寸错误，阅读 errors.jsonl 和退出码。
10. 最后再增加 workers，测量真实吞吐。

当你能解释“为什么右边界要加 1”“为什么更换配置不能默认复用旧输出”“为什么多个 semantic label 同属一类仍产生多行”时，就已经真正掌握了这个项目，而不只是会复制命令。

