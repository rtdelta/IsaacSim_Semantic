# 260730_01ThresholdFilter

一个独立、配置驱动的高速 YOLO 可见性过滤器。项目组合
`260724PostProcessChain` 的 full-scene YOLO 输出和
`260727SemanticPixelRatio` 的逐斗齿像素计数，根据显露比例过滤单斗齿框
与斗齿集合框。

## 规则

单斗齿：

```text
pixel_ratio < a  → 删除已有框
pixel_ratio >= a → 保留已有框
```

斗齿集合：

```text
五个斗齿中至少三个满足 pixel_ratio < b → 删除已有集合框
```

集合规则使用五个单斗齿比例，不使用聚合集合比例。

## 身份解析模式

- `legacy_zero_class_order`
  - 当前所有单斗齿 class ID 为 `0`；
  - 根据配置顺序和 `whole_pixels >= source_min_pixels` 恢复缺失斗齿后的行身份。
- `class_id_map`
  - 通过配置的 `class_id → semantic_label` 映射直接识别；
  - 支持 `0～4`、`1～5` 或其他明确配置的非负整数编号。

## 性能路径

默认高速路径：

- 一次读取 `counts_cache.npz`；
- NumPy 批量计算所有过滤掩码；
- 单次目录扫描；
- 有界线程池处理小型 YOLO 文件；
- PNG 使用硬链接，不解码；
- staging 目录完成后整体提交；
- 报告由主线程集中写入；
- 默认抽样验证，不全量重读输出。

## 安装

```powershell
python -m pip install -r requirements.txt
```

## 配置

复制并修改：

```text
configs/example.json
```

示例中的阈值仅用于展示格式，正式运行前必须设置实际的 `a` 和 `b`。
所有业务、路径、解析模式、性能和输出参数均来自配置文件。

## 运行

```powershell
python run_filter.py --config configs\your_run.json
```

命令行只接受配置文件路径，不接受业务参数覆盖。

## 输出

```text
output_root/
├── manifest.json
├── summary.json
├── decisions.csv
├── frame_summary.csv
├── anomalies.csv
└── modules/
    ├── tooth_boxes/
    └── tooth_group/
```

当已有框全部被删除且 `keep_empty_label_files=true` 时，输出空 `.txt`。
上游不存在的框不会被重新生成。

## 测试

```powershell
python -m unittest discover -s . -p "test_*.py" -v
```

完整设计见：

```text
docs/implemtn_plan/implement_v02.md
```
