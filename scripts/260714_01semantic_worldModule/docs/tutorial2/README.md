# `semantic_worldModule` 从零学习指南

> 本套笔记仅根据当前项目的 Python 源码、JSON/USDA/CSV 配置和测试重新整理，没有参考 `README.md` 或 `docs` 下的旧教程。

## 1. 这个项目到底做什么

这个项目在 Isaac Sim 中打开一台带车载相机的挖掘机 USD 场景，用固定物理步长驱动四个关节，并在精确的仿真时刻冻结世界、采集 RGB 与语义分割图。它同时记录相机、关节和时间状态，最后用独立验证器检查“图像、标签、物理状态、渲染设置、时间戳”是否彼此一致。

它解决的不是“怎样截一张图”，而是数据集生产中的五个正确性问题：

1. 每张图是否对应确定的物理时刻；
2. 图像里的机械状态是否与元数据记录的关节状态相同；
3. Isaac Sim 本次运行分配的临时语义 ID，是否被转换成跨运行稳定的 ID；
4. 实际生效的渲染参数，是否与配置要求一致；
5. 输出文件是否齐全、可追溯、可自动验收。

默认运行参数的快照如下：

| 项目 | 默认值 |
|---|---|
| 场景 | `configs/Sim_Fangshan_07_capture_overlay.usda` |
| 相机 | `/root/Xform/operator_cab_mesh/Camera_01` |
| 关节 | `cab, boom, small_arm, bucket` |
| 物理频率 | 60 Hz |
| 采集频率 | 10 FPS |
| 每次采集间隔 | 6 个物理步 |
| 帧数 | 50 |
| 分辨率 | 1280×720 |
| 默认渲染器 | `RealTimePathTracing` |
| 输出 | `output/semantic_capture_v3` |
| 清单版本 | `run_config.json` schema v3 |

## 2. 推荐学习顺序

如果你完全没有 Isaac Sim 基础，按编号阅读即可：

| 阶段 | 文档 | 学完后的能力 |
|---|---|---|
| 入门 | [01_零基础概念.md](01_零基础概念.md) | 看懂 USD、Prim、Articulation、Replicator、语义 ID 等术语 |
| 总览 | [02_架构与完整运行流程.md](02_架构与完整运行流程.md) | 能从入口追踪一次采集的全生命周期 |
| 核心一 | [03_固定时间步与同步采集.md](03_固定时间步与同步采集.md) | 理解为什么每一帧能与物理状态严格对齐 |
| 核心二 | [04_四关节运动系统.md](04_四关节运动系统.md) | 理解轨迹插值、Articulation 绑定、命令与回读 |
| 核心三 | [05_语义相机与数据写出.md](05_语义相机与数据写出.md) | 理解稳定标签映射、Writer 和输出目录 |
| 实操 | [06_配置与运行实战.md](06_配置与运行实战.md) | 能测试、试跑、正式采集、验证和比较画质 |
| 保障 | [07_验证测试与排错.md](07_验证测试与排错.md) | 能根据清单和错误码定位问题 |
| 进阶 | [08_源码精读与二次开发.md](08_源码精读与二次开发.md) | 能安全扩展标签、轨迹、场景和调度逻辑 |
| 巩固 | [09_分阶段练习与参考答案.md](09_分阶段练习与参考答案.md) | 通过练习确认自己真正掌握数据流 |
| 查阅 | [10_速查表.md](10_速查表.md) | 快速查询命令、公式、文件和常见约束 |

建议先完整读到第 5 章，再运行第 6 章的命令。不要一开始就改 `simulation_orchestrator.py`：入口负责拼装所有模块，直接修改它很容易掩盖真正的边界和约束。

## 3. 项目地图

```text
260714_01semantic_worldModule/
├─ simulation_orchestrator.py       # 总入口与生命周期编排
├─ world_scheduler.py               # 固定物理步、Timeline、冻结/恢复
├─ capture_timing.py                # 纯数学：帧号 -> 物理步/数据集时间
├─ capture_context.py               # 不可变帧上下文、回执、线程安全账本
├─ semantic_capture_custom.py       # 相机、RenderProduct、逐帧采集
├─ semantic_dataset_writer.py       # Replicator Writer 与文件落盘
├─ semantic_mapping.py              # 临时语义 ID -> 稳定数据集 ID
├─ joint_control_profile.py         # 四关节控制契约配置
├─ articulation_stage_validator.py  # Articulation 的只读 USD 验证
├─ articulation_adapter.py          # Isaac Articulation 张量接口适配
├─ excavator_joint_motion.py        # CSV 轨迹、插值、命令、回读
├─ stage_preflight.py               # 场景、依赖、相机、语义预检
├─ render_profile.py                # 版本化渲染配置与生效值回读
├─ validate_semantic_output.py      # 完整数据集验收
├─ compare_render_quality.py        # 两张 RGB 的客观指标比较
├─ run_capture_remote.sh            # Linux/远端 Isaac Sim 启动包装
├─ configs/                         # 场景叠加层、语义/关节/渲染配置
├─ trajectories/                    # 四关节 CSV 轨迹
└─ tests/                           # 普通 Python 可运行的单元测试
```

这些文件可分为四层：

- **纯逻辑层**：`capture_timing.py`、`capture_context.py`、`semantic_mapping.py`、`joint_control_profile.py`、`render_profile.py`。大部分可在普通 Python 下测试。
- **USD 检查层**：`stage_preflight.py`、`articulation_stage_validator.py`。只读取 Stage，不修改资产。
- **Isaac 运行层**：`world_scheduler.py`、`articulation_adapter.py`、`excavator_joint_motion.py`、`semantic_capture_custom.py`、`semantic_dataset_writer.py`。
- **编排与验收层**：`simulation_orchestrator.py`、`validate_semantic_output.py`、`compare_render_quality.py`。

## 4. 一条最重要的主线

学习时始终追踪下面这条数据链：

```mermaid
flowchart LR
    A["CSV 轨迹"] --> B["物理步前：关节命令"]
    B --> C["Isaac 物理步"]
    C --> D["物理步后：关节回读"]
    D --> E["冻结 Timeline"]
    E --> F["CaptureContext"]
    F --> G["Replicator 渲染与标注"]
    G --> H["稳定语义 ID 重映射"]
    H --> I["RGB / NPY / PNG / JSON"]
    I --> J["独立验证器"]
```

项目的正确性来自顺序，而不是某个神奇 API：**先命令，后物理；先回读，后冻结；冻结后构造上下文；上下文先入账，再触发 Writer；写完后再验证世界没有前进。**

## 5. 学习时要区分的三类“成功”

1. **单元测试成功**：纯 Python 逻辑和模拟对象通过，不代表 GPU、USD 资产或 Isaac 集成一定可用。
2. **采集进程成功**：`run_config.json` 的 `status` 为 `complete`，代表运行完成，但仍应执行输出验证器。
3. **数据集验收成功**：`validate_semantic_output.py` 输出 `PASS`，才表示文件数、数据类型、标签、时间、关节状态和移动关系全部满足契约。

本机已对当前代码运行 `python -m pytest -q`，结果为 **69 passed**。这是一条可靠的学习起点，但不替代远端 Isaac Sim 的集成试跑。

## 6. 阅读源码的建议

- 看到 `simulation_time`、`timeline_time`、`dataset_time` 时不要混用，第三章会专门解释。
- 看到 `runtime_id` 与 `dataset_id` 时，记住前者只对本次 Isaac 运行有意义，后者才是训练数据标签。
- 看到 `target`、`commanded`、`actual` 时，分别理解为兼容字段、已提交命令、物理引擎回读值。
- 看到 `warmup` 与 `pre-roll` 时，前者是渲染历史预热，后者是物理预运行，它们属于不同时间域。
- 任何修改都应先问：是否破坏了“一个输出帧只有一个权威上下文”这一原则。

