# 260814_01Formatter

高速整理 `260731PostProcessChain_v02` 输出的数据集：

- RGB、单斗齿标注和碰撞模型标注统一使用自定义前缀；
- 根据最大数值帧号自动确定补零宽度；
- 两类 YOLO 标注的类别 ID 全部归一为 `0`；
- 单斗齿 `classes.txt` 合并为单一类别；
- 原分析报告保持原始五斗齿类别；
- 图片和不变文件优先使用硬链接；
- 在 staging 中完成并验证后一次性提交新输出目录。

## 环境

Python 3.9 或更高版本，无第三方依赖。

## 配置

复制并修改：

```text
configs/example.json
```

核心配置示例：

```json
{
  "schema_version": 1,
  "input_root": "/path/to/PostProcess0813_01",
  "output_root": "/path/to/Formatted0813_01",
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

`input_root` 与 `output_root` 必须是互不嵌套的不同目录，且输出目录不能预先存在。

## 运行

```bash
python run_formatter.py --config configs/your_run.json
```

不提供 dry-run。脚本直接执行，但只有全部转换和校验成功后才会创建正式输出目录。失败时清理 staging，输入目录保持不变。

## 自动补零

```text
padding_width = len(str(max_numeric_frame_id))
```

例如最大帧号为 `10189` 时统一使用五位：

```text
0     → 00000
1     → 00001
117   → 00117
9999  → 09999
10000 → 10000
10189 → 10189
```

脚本不会重新编号。数值等价的源帧号（例如 `1` 和 `0001`）会被视为重复并导致执行失败。

## 输出

```text
Formatted0813_01/
├── dataset/
│   ├── rgb/
│   ├── tooth_boxes/
│   └── tooth_collision_model/
├── reports/
├── source_manifest.json
├── formatter_manifest.json
└── rename_manifest.csv
```

`rename_manifest.csv` 保存每一帧的新旧文件名映射；`formatter_manifest.json` 保存配置快照、帧号宽度、类别统计、处理速度和物化方式。

## 测试

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

详细设计见：

```text
docs/ImplementPlan/DatasetFormatter_ImplementationPlan_20260814.md
```
