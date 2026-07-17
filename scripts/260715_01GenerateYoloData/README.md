# 语义 ID 转 YOLO tooth 标注

将 Isaac Sim 批量输出的 RGB 图片和 `semantic_id_*.npy` 转换为单类别 YOLO 检测数据。脚本只处理 mapping 中名称以 `tooth_` 开头的语义 ID，所有框统一输出为类别 `0 tooth`，不处理 `lack`。

## 输入要求

输入目录中的文件按帧号配对：

```text
rgb_0000.png
semantic_id_0000.npy
rgb_0001.png
semantic_id_0001.npy
semantic_mapping.json
```

要求：

- RGB 文件名必须是 `rgb_<帧号>.png`。
- 语义文件名必须是 `semantic_id_<相同帧号>.npy`。
- NPY 是二维语义 ID 数组，形状为 `(图片高度, 图片宽度)`。
- mapping 的 `classes` 中至少存在一个名称以 `tooth_` 开头的类别。

## 安装

```powershell
python -m pip install -r requirements.txt
```

## 运行

```powershell
python convert.py `
  --input "D:\learning\IntelligentDepartment\CodesSet\Self\260707IsaacSIm\Materials\rgb_semantic" `
  --output "D:\learning\IntelligentDepartment\CodesSet\Self\260707IsaacSIm\Materials\yolo_tooth" `
  --workers 4
```

常用参数：

| 参数 | 说明 |
|---|---|
| `--workers` | 并行进程数，默认不超过 8 |
| `--max-in-flight` | 等待中的最大任务数，默认是 workers 的 2 倍 |
| `--min-pixels` | 单颗 tooth 至少需要的语义像素数，默认 10 |
| `--overwrite` | 覆盖已经存在的 TXT；默认跳过，实现断点续跑 |

任务采用有界提交：不会一次加载全部 NPY，内存占用主要取决于 `workers` 和 `max-in-flight`，而不是数据集总帧数。

## 输出

```text
yolo_tooth/
├── rgb_0000.png
├── rgb_0000.txt
├── rgb_0001.png
├── rgb_0001.txt
├── classes.txt
└── errors.jsonl       # 仅在存在失败帧时生成
```

图片优先通过硬链接放入输出目录；如果硬链接不可用，自动回退为复制。图片不会旋转、缩放或重新编码。

`classes.txt` 内容为：

```text
tooth
```

每个 TXT 中一行表示一个 tooth：

```text
0 x_center y_center width height
```

后四个数均除以图片宽高，范围为 0～1。

## 处理规则

1. 启动时只读取一次 `semantic_mapping.json`。
2. 自动提取所有 `tooth_*` 语义 ID，不写死具体 ID 数值。
3. 使用该语义 ID 的全部像素计算最小外接矩形。
4. 像素数低于 `--min-pixels` 的掩码不生成框。
5. 当前帧没有可见 tooth 时生成空 TXT，这是合法的 YOLO 负样本。
6. 标签通过临时文件和原子重命名写入，程序中断不会留下半个有效 TXT。
7. 已存在的标签默认跳过；需要重新生成时使用 `--overwrite`。

单帧失败不会终止整个批次，错误会写入 `errors.jsonl`，程序结束时返回非零状态码。
