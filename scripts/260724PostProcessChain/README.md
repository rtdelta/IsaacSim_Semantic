# 260724PostProcessChain

一个独立、配置驱动的图像后处理流水线。项目不导入或调用旧的 `260715_01GenerateYoloData` 代码。

当前内置两个模块：

1. `semantic_yolo_boxes`：从 semantic ID 图生成指定标签的独立 YOLO 框；
2. `tooth_group_yolo`：消费上游像素框中间产物，生成斗齿集合 YOLO 框。

## 结构边界

```text
run_pipeline.py              程序入口
configs/                     总调度器配置
postprocess_chain/pipeline/  调度、依赖、帧级并行和模块接口
postprocess_chain/common/    多模块共享的数据模型、几何、I/O 和 YOLO 输出
postprocess_chain/modules/   相互隔离的业务模块及各自配置
tests/                       跨模块和端到端测试
```

依赖方向为：

```text
run_pipeline -> pipeline
modules -> pipeline.module_base + common
pipeline -> common
```

业务模块之间不直接导入。模块通过 `FrameArtifactStore` 和 `common.models` 中的数据类型通信。

## 准备配置

修改 `configs/orchestrator.json` 中的输入和输出路径。相对路径以该配置文件所在目录为基准。`configs/orchestrator.example.json` 保留为原始参考模板。

每个模块的业务参数位于模块自己的目录：

```text
postprocess_chain/modules/semantic_yolo_boxes/semantic_yolo_boxes.json
postprocess_chain/modules/tooth_group_yolo/tooth_group_yolo.json
```

总调度器配置只负责：

- RGB、semantic 和 mapping 输入；
- 输出根目录；
- workers、max_in_flight、overwrite；
- 模块启停、类型、配置路径和依赖关系。

## 运行

默认读取 `configs/orchestrator.json`：

```powershell
python run_pipeline.py
```

也可以只通过启动参数选择另一份总调度器配置：

```powershell
python run_pipeline.py --config configs\orchestrator.example.json
```

所有业务参数都来自 JSON，不通过命令行传输。

## 输出

```text
output_root/
├── manifest.json
├── summary.json
├── errors.jsonl                 仅在存在错误时生成
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

图片默认优先使用硬链接，失败时复制。每个模块拥有独立的 YOLO 类别文件和逐帧标签。

当斗齿集合模块无法获得两个端部框且使用 `exclude_frame` 时，该帧不会进入集合框输出目录，以免生成错误负样本。

## 断点续跑

- `overwrite=false` 时，已存在的模块标签不会重写；
- 即使模块一标签已存在，只要下游依赖其内存产物，模块一仍会执行计算；
- `manifest.json` 保存总配置、模块配置和 mapping 的联合指纹；
- 指纹变化时默认拒绝复用旧输出目录，需使用新目录或设置 `overwrite=true`。

## 测试

```powershell
python -m unittest discover -s . -p "test_*.py" -v
```
