# 260814_01Formatter 数据集格式化脚本实施方案

## 1. 文档信息

- 项目名称：`260814_01Formatter`
- 文档类型：实现前设计方案
- 目标位置：`scripts/260814_01Formatter`
- 配置方式：JSON 参数配置文件
- 执行方式：直接生成新的输出目录，不原地修改输入数据
- 当前状态：仅完成方案设计，尚未实现代码

## 2. 背景

`260731PostProcessChain_v02` 当前生成以下三组逐帧数据：

```text
dataset/
├── rgb/
│   └── rgb_<frame_id>.png
├── tooth_boxes/
│   ├── classes.txt
│   └── rgb_<frame_id>.txt
└── tooth_collision_model/
    ├── classes.txt
    └── rgb_<frame_id>.txt
```

格式化脚本需要把这三组文件整理为统一的发布命名格式，并将两类 YOLO 标注中的类别 ID 全部归一为 `0`。

当前 `output0813_01` 数据基线如下：

- RGB 文件：10190 个；
- 单斗齿标注文件：10190 个；
- 碰撞模型标注文件：10190 个；
- 原始帧号范围：`0000`～`10189`；
- 单斗齿有效标注行：22807 行，原类别为 `0`～`4`；
- 单斗齿空标注文件：5527 个；
- 碰撞模型有效标注行：4556 行，当前类别已经全部为 `0`；
- 碰撞模型空标注文件：5634 个；
- 三组逐帧文件的帧号集合完全一致。

## 3. 核心目标

### 3.1 文件统一命名

所有逐帧 RGB、单斗齿标注和碰撞模型标注统一命名为：

```text
<filename_prefix>_<zero_padded_frame_id>.<original_extension>
```

例如配置：

```text
filename_prefix = Sim_Fangshan_tooth_260813
```

则输出示例为：

```text
Sim_Fangshan_tooth_260813_00001.png
Sim_Fangshan_tooth_260813_00001.txt
```

同一帧在三个目录中的文件主名必须完全一致。

### 3.2 根据最大帧号自动补零

帧号必须统一左侧补 `0`，补零宽度根据输入数据中最大的数值帧号自动计算：

```text
padding_width = len(str(max(frame_id)))
```

这里的“最大帧数”在实现中明确解释为“扫描到的最大数值帧号”，而不是文件总数。这样即使输入存在帧号间断，也不会改变帧号本身的含义。

格式化规则为：

```text
normalized_frame_id = str(int(source_frame_id)).zfill(padding_width)
```

当前数据最大帧号为 `10189`，因此：

```text
padding_width = 5
```

对应结果：

```text
0000  → 00000
0001  → 00001
0117  → 00117
9999  → 09999
10000 → 10000
10189 → 10189
```

脚本只统一帧号宽度，不重新排序或连续重编号。若同时存在 `1` 和 `0001`，两者归一化后都会成为同一个帧号，脚本必须在写入前检测到该冲突并终止。

### 3.3 标注类别归一

单斗齿和碰撞模型目录内的每一条 YOLO 标注都改为类别 `0`。

原始标注：

```text
3 0.21132813 0.63472222 0.04140625 0.04444444
```

格式化后：

```text
0 0.21132813 0.63472222 0.04140625 0.04444444
```

处理规则：

- 只替换第一列类别 ID；
- 后四列坐标字符串原样保留；
- 不重新计算或重新格式化浮点数；
- 空标注文件继续保持为空；
- 每条非空标注必须严格为五列；
- 类别必须可解析为非负整数；
- 四个坐标必须是有限浮点数；
- 不合法的标注会导致本次格式化整体失败。

### 3.4 类别文件更新

`tooth_boxes/classes.txt` 从原来的五类：

```text
tooth_01
tooth_02
tooth_03
tooth_04
tooth_05
```

更新为配置指定的单一类别，默认建议：

```text
tooth
```

`tooth_collision_model/classes.txt` 保持一个类别，默认建议：

```text
tooth_collision_model
```

两个类别名称均由配置文件传入，但对应类别 ID 固定为 `0`。

### 3.5 保留分析报告

原后处理报告中的类别 `0`～`4` 表示五颗独立斗齿的分析结果，具有可追溯价值，因此不得改成统一类别。

下列内容保持原始语义：

```text
reports/tooth_features.csv
reports/tooth_decisions.csv
reports/collision_decisions.csv
reports/frame_summary.csv
reports/anomalies.csv
reports/summary.json
resolved_config.json
```

格式化后的数据集以新生成的 `formatter_manifest.json` 为准；原后处理 manifest 作为来源记录保留，不作为新文件命名的权威清单。

## 4. 处理范围

### 4.1 需要改名和转换的文件

```text
dataset/rgb/*
dataset/tooth_boxes/<frame label files>
dataset/tooth_collision_model/<frame label files>
```

### 4.2 不按帧改名的文件

```text
classes.txt
reports/*
manifest.json
resolved_config.json
```

`classes.txt` 不改文件名，但需要按第 3.4 节重写内容。

## 5. 项目结构

建议采用以下结构：

```text
260814_01Formatter/
├── run_formatter.py
├── formatter/
│   ├── __init__.py
│   ├── config.py
│   ├── models.py
│   ├── discovery.py
│   ├── naming.py
│   ├── label_transform.py
│   ├── materializer.py
│   ├── validator.py
│   ├── staging.py
│   └── manifest.py
├── configs/
│   └── example.json
├── docs/
│   └── ImplementPlan/
├── tests/
├── README.md
└── requirements.txt
```

项目优先只使用 Python 标准库，避免额外依赖和环境安装开销。

## 6. 配置文件设计

除 `--config` 外，不通过命令行传递业务参数。

配置示例：

```json
{
  "schema_version": 1,
  "input_root": "/root/gpufree-data/semantic/scripts/output/output0813_01/PostProcess0813_01",
  "output_root": "/root/gpufree-data/semantic/scripts/output/output0813_01/Formatted0813_01",
  "filename_prefix": "Sim_Fangshan_tooth_260813",
  "classes": {
    "tooth_class_name": "tooth",
    "collision_class_name": "tooth_collision_model"
  },
  "output": {
    "preserve_reports": true,
    "unchanged_file_mode": "hardlink_or_copy"
  },
  "performance": {
    "workers": 32,
    "max_in_flight": 512
  }
}
```

配置要求：

- `schema_version` 必须是受支持的版本；
- `input_root` 必须是现有后处理输出目录；
- `output_root` 必须与输入目录不同，并且二者不能互相嵌套；
- `output_root` 已存在时直接失败，不进行覆盖；
- `filename_prefix` 不能为空；
- 前缀不得包含 `/`、`\`、控制字符、`.` 或 `..` 路径段；
- 前缀末尾不允许带 `_`，避免生成双下划线；
- `workers` 和 `max_in_flight` 必须是正整数；
- 未知配置字段直接报错，防止配置拼写错误被静默忽略；
- 相对路径相对于配置文件所在目录解析。

启动方式：

```bash
python run_formatter.py --config configs/format_output0813_01.json
```

不提供独立 dry-run 模式。命令启动后直接执行，但正式输出目录只会在全部处理和验证成功后出现。

## 7. 输出目录设计

```text
Formatted0813_01/
├── dataset/
│   ├── rgb/
│   │   ├── Sim_Fangshan_tooth_260813_00000.png
│   │   ├── Sim_Fangshan_tooth_260813_00001.png
│   │   └── ...
│   ├── tooth_boxes/
│   │   ├── classes.txt
│   │   ├── Sim_Fangshan_tooth_260813_00000.txt
│   │   └── ...
│   └── tooth_collision_model/
│       ├── classes.txt
│       ├── Sim_Fangshan_tooth_260813_00000.txt
│       └── ...
├── reports/
├── source_manifest.json
├── formatter_manifest.json
└── rename_manifest.csv
```

`rename_manifest.csv` 建议包含：

```text
numeric_frame_id,source_frame_id,normalized_frame_id,source_rgb,output_rgb,source_tooth_label,output_tooth_label,source_collision_label,output_collision_label
```

## 8. 核心处理流程

### 8.1 配置加载

1. 读取 JSON；
2. 严格校验 schema；
3. 解析绝对路径；
4. 检查输入和输出不能相同；
5. 检查正式输出目录不存在。

### 8.2 帧发现和配对

使用 `os.scandir()` 扫描三个数据目录，降低大量文件场景下的目录遍历开销。

对每个逐帧文件：

1. 从文件主名最后一个 `_` 后提取帧号；
2. 要求帧号只包含十进制数字；
3. 转换为整数帧号；
4. 检查同一目录内是否存在数值重复帧号；
5. 验证 RGB、单斗齿标注、碰撞标注三组数值帧号完全一致。

### 8.3 自动补零宽度

完成三组帧发现后计算：

```text
max_frame_id = max(all_numeric_frame_ids)
padding_width = len(str(max_frame_id))
```

若数据集只有帧 `0`，宽度为 `1`，输出帧号为 `0`。

随后为每一帧生成：

```text
normalized_frame_id = f"{numeric_frame_id:0{padding_width}d}"
```

在创建任何输出文件前，必须确认所有目标主名唯一。

### 8.4 staging 构建

在输出目录旁创建：

```text
.<output_name>.staging-<uuid>
```

正式输出内容全部先生成到 staging 中。

### 8.5 RGB 高速物化

图片不需要改变内容，优先使用：

```python
os.link(source, destination)
```

硬链接只创建新的目录项，不复制图片数据。若输入和输出不在同一文件系统，自动回退到 `shutil.copy2()`。

图片处理不计算全量 SHA256，以避免额外读取大体积图片。硬链接模式通过 inode 和文件大小检查；复制模式通过文件数量和大小检查。

### 8.6 标注高速转换

使用 `ThreadPoolExecutor` 和有界任务队列并行处理小文件：

```text
workers = 32
max_in_flight = 512
```

每个标注任务在一次读取中完成：

1. 读取原文件；
2. 校验每条非空标注；
3. 将首列替换为 `0`；
4. 保留坐标字符串；
5. 写入新文件名；
6. 更新线程安全统计计数。

标注不会为了预检和转换被重复读取。

### 8.7 报告与元数据

不变文件优先硬链接，硬链接失败时复制。原 `manifest.json` 在新目录中保存为 `source_manifest.json`，避免与新格式化 manifest 混淆。

若原 metadata 中存在明确的逐帧文件路径引用，需要在实现阶段列入重写清单；分析数值和报告类别不得改变。

### 8.8 最终验证和提交

不执行独立 dry-run，但必须执行流水线内部验证：

- 三组输出帧号集合一致；
- 所有输出帧号宽度等于 `padding_width`；
- 每个文件名严格匹配 `<prefix>_<padded_frame_id>`；
- 输出扩展名与输入一致；
- 两类标注的所有类别均为 `0`；
- 坐标部分与输入字符串一致；
- 空标注文件数量不变；
- `classes.txt` 各只有一行；
- 报告和保留文件数量正确；
- 没有残留 `rgb_<frame_id>` 命名的逐帧文件。

验证成功后使用同一文件系统上的目录重命名，将 staging 原子提交为正式输出目录。失败时删除 staging，输入数据保持不变。

## 9. 性能方案

主要性能策略：

1. 使用 `os.scandir()`，避免重复目录遍历；
2. 三组文件先构建内存索引，再进行 O(n) 配对；
3. RGB 和不变报告采用硬链接；
4. 标注只读取一次；
5. 标注和文件物化使用线程池并发；
6. 使用有界 `max_in_flight`，避免一次提交数万个 Future；
7. 不读取图片像素，不进行图片解码；
8. 不对大文件执行默认全量哈希；
9. staging 内直接写新文件，避免逐文件临时替换开销；
10. 最终通过一次目录 rename 完成提交。

针对当前约 3 万个逐帧文件的规模，主要耗时应集中在目录操作和小标注文件读写，而不是 RGB 数据复制。

## 10. 异常处理

以下情况必须立即终止：

- 输入目录结构缺失；
- 三组文件数量或帧号集合不一致；
- 文件名没有合法数字帧号；
- 数值帧号归一化后重复；
- 目标文件名冲突；
- 标注不是五列；
- 类别或坐标无法解析；
- 坐标包含 `NaN` 或无穷值；
- 输出目录已存在；
- 硬链接和复制均失败；
- staging 最终验证失败。

异常信息必须包含文件路径、帧号和具体原因。脚本返回非零退出码，并清理本次 staging。

## 11. 测试方案

### 11.1 单元测试

- 从 `rgb_0001.png` 提取数值帧号 `1`；
- 最大帧号为 `999` 时使用三位宽度；
- 最大帧号为 `1000` 时使用四位宽度；
- 当前最大帧号 `10189` 时使用五位宽度；
- `0001` 和 `1` 同时存在时检测数值重复；
- 前缀合法性和非法路径字符；
- 非空 YOLO 行类别归零；
- 坐标字符串完全保持；
- 空标注保持为空；
- 非五列标注报错；
- `NaN` 和无穷坐标报错；
- 目标目录已存在时拒绝执行；
- 硬链接失败时回退复制。

### 11.2 集成测试

构造包含帧 `0`、`1`、`9999`、`10000` 的小型数据集，验证最大帧号为 `10000` 时输出：

```text
PREFIX_00000.png
PREFIX_00001.png
PREFIX_09999.png
PREFIX_10000.png
```

同时验证：

- 三组主名一致；
- 两类标注全部为类别 `0`；
- 报告内容不变；
- 原输入目录不变；
- 正式输出只在完成后出现。

### 11.3 当前真实数据验收

当前 `output0813_01` 格式化完成后必须满足：

- `padding_width = 5`；
- RGB 文件：10190 个；
- 单斗齿标注：10190 个；
- 碰撞模型标注：10190 个；
- 第一帧主名后缀为 `_00000`；
- 第 117 帧主名后缀为 `_00117`；
- 最后一帧主名后缀为 `_10189`；
- 单斗齿有效标注共 22807 行，类别全部为 `0`；
- 碰撞模型有效标注共 4556 行，类别全部为 `0`；
- 两类空标注数量分别保持 5527 和 5634；
- 所有坐标字符串与输入一致；
- 所有图片扩展名和文件大小保持一致；
- 原始报告内容不变。

## 12. 运行结果摘要

完成后终端应输出类似：

```text
status=completed
frames=10190
max_frame_id=10189
padding_width=5
images_linked=10190
images_copied=0
tooth_label_files=10190
collision_label_files=10190
label_lines_rewritten=27363
empty_tooth_labels=5527
empty_collision_labels=5634
elapsed_seconds=<value>
files_per_second=<value>
output_root=<resolved output path>
```

`formatter_manifest.json` 同步记录上述统计、配置快照、输入输出路径、运行时间和新旧文件名规则。

## 13. 实施顺序

1. 创建项目骨架和严格配置加载器；
2. 实现三目录帧发现与数值帧号配对；
3. 实现最大帧号位数计算和统一补零；
4. 实现目标名称规划和冲突检测；
5. 实现 YOLO 标注流式类别归零；
6. 实现 RGB/报告硬链接与复制回退；
7. 实现 staging、最终验证和原子提交；
8. 实现 rename manifest 与 formatter manifest；
9. 完成单元测试和小数据集集成测试；
10. 使用 `output0813_01` 执行真实数据验收和性能统计。

## 14. 非目标

本脚本不负责：

- 重新运行语义后处理；
- 重新计算或调整检测框；
- 修改 YOLO 坐标；
- 修改原始分析报告中的五斗齿类别；
- 重新排列或连续重编号帧；
- 修改输入目录；
- 合并单斗齿任务和碰撞模型任务；
- 训练或划分训练、验证、测试数据集。
