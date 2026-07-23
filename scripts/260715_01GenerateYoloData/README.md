# 语义 ID 转可配置 YOLO 标注

将 Isaac Sim 批量输出的 RGB 图片和 `semantic_id_*.npy` 转换为 YOLO 检测数据。RGB、semantic NPY、mapping 和 YOLO 类别配置分别传入；脚本不再硬编码 `tooth_` 或 YOLO 类别 `0`。

## 输入要求

输入数据可以保持独立目录：

```text
dataset/
├── rgb/
│   ├── rgb_0000.png
│   └── rgb_0001.png
├── semantic_id/
│   ├── semantic_id_0000.npy
│   └── semantic_id_0001.npy
└── semantic_mapping.json
```

要求：

- RGB 文件名必须是 `rgb_<帧号>.png`。
- semantic 文件名必须是 `semantic_id_<相同帧号>.npy`。
- RGB 和 semantic 帧号必须完全配对；脚本在创建输出目录前检查。
- NPY 必须是二维语义 ID 数组，形状为 `(图片高度, 图片宽度)`。
- mapping 的 `classes` 必须提供唯一的 `id` 和 `label`。
- 输出目录不能与 RGB、semantic 目录相同或互相包含，避免污染输入数据。

## YOLO 类别配置

通过独立 JSON 文件指定需要标注的精确语义标签。参考 `yolo_classes.example.json`：

```json
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
```

规则：

- `yolo_id` 必须从 `0` 开始连续编号。
- `yolo_name` 会按 `yolo_id` 顺序写入 `classes.txt`。
- `semantic_labels` 使用 mapping 中的精确标签名称，不支持隐式前缀或通配符。
- 一个 semantic label 只能分配给一个 YOLO 类别。
- 多个 semantic label 可以合并为同一个 YOLO 类别，但每个 semantic label 分别生成一个框。

## 安装

```bash
python3 -m pip install -r requirements.txt
```

## 运行

```bash
python3 convert.py \
  --rgb-dir /path/to/dataset/rgb \
  --semantic-dir /path/to/dataset/semantic_id \
  --mapping /path/to/dataset/semantic_mapping.json \
  --class-config /path/to/yolo_classes.json \
  --output /path/to/yolo_output \
  --workers 8 \
  --max-in-flight 16 \
  --min-pixels 10
```

参数：

| 参数 | 必填 | 说明 |
|---|---:|---|
| `--rgb-dir` | 是 | `rgb_*.png` 文件夹 |
| `--semantic-dir` | 是 | `semantic_id_*.npy` 文件夹 |
| `--mapping` | 是 | semantic mapping JSON 完整路径 |
| `--class-config` | 是 | YOLO 类别配置 JSON 完整路径 |
| `--output` | 是 | YOLO 图片和标签输出目录 |
| `--workers` | 否 | 并行进程数，默认不超过 8 |
| `--max-in-flight` | 否 | 等待中的最大任务数，默认是 workers 的 2 倍，不能小于 workers |
| `--min-pixels` | 否 | 单个 semantic label 至少需要的像素数，默认 10 |
| `--overwrite` | 否 | 覆盖已经存在的 TXT；默认跳过，实现断点续跑 |

如果更换类别配置并复用同一个输出目录，必须使用 `--overwrite`，或者改用全新的输出目录，避免保留旧配置生成的标签。

## 输出

```text
yolo_output/
├── rgb_0000.png
├── rgb_0000.txt
├── rgb_0001.png
├── rgb_0001.txt
├── classes.txt
└── errors.jsonl       # 仅在存在失败帧时生成
```

图片优先通过硬链接放入输出目录；如果硬链接不可用，自动回退为复制。图片不会旋转、缩放或重新编码。

每个 TXT 中一行表示一个框：

```text
<yolo_id> x_center y_center width height
```

后四个数均除以图片宽高，范围为 0～1。每个 semantic label 在一帧中的全部像素生成一个最小外接矩形；当前不进行连通区域拆分。

## 处理规则

1. 启动时读取并验证 mapping、YOLO 类别配置和 RGB/semantic 帧配对。
2. semantic 数值 ID 从 mapping 动态解析，不在代码中硬编码标签名称或类别编号。
3. 像素数低于 `--min-pixels` 的掩码不生成框。
4. 当前帧没有任何目标时生成空 TXT，这是合法的 YOLO 负样本。
5. 标签通过临时文件和原子重命名写入，程序中断不会留下半个有效 TXT。
6. 已存在的标签默认跳过；需要重新生成时使用 `--overwrite`。

任务采用有界提交，不会一次加载全部 NPY；内存占用主要取决于 `workers` 和 `max-in-flight`。单帧处理失败不会终止整个批次，错误会写入 `errors.jsonl`，程序结束时返回非零状态码。
