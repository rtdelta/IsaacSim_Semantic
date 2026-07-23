# `260714_01semantic_worldModule` 学习导航

> 文档对应代码状态：2026-07-20，输出清单 schema v3，四关节采用
> `articulation_direct_position` 控制。若代码继续演进，请先核对项目根目录的
> `README.md`、`simulation_orchestrator.py` 和 `run_config.json` 的 schema 版本。

## 先说结论：这个项目在做什么

这个项目把一台四自由度挖掘机放入 Isaac Sim 场景，按固定物理步长播放关节轨迹，
在指定时刻冻结世界，通过驾驶室相机同步采集 RGB 和语义分割图，并把“图像、语义、
相机姿态、关节命令、关节实际回读、渲染配置、输入文件哈希”组织成一份可验证的数据集。

它真正解决的不是“怎样保存一张图”，而是下面四个更难的问题：

1. 图像对应的物理时刻是否明确且可重复？
2. 语义类别 ID 是否跨运行稳定，而不是 Isaac 临时分配的 runtime ID？
3. 图像中的挖掘机姿态是否与保存的关节状态完全对应？
4. 数据生成结束后，能否证明配置已生效、文件完整且没有未知标签？

## 推荐学习顺序

### 第一遍：先建立全局认识

阅读 [Isaac_Sim语义世界模块完整学习笔记.md](./Isaac_Sim语义世界模块完整学习笔记.md)：

- 第 1～4 章：理解项目目标、术语、文件职责和完整运行链路。
- 第 5～9 章：理解固定时间步、Articulation、语义映射和 Writer。
- 第 10～13 章：学会运行、验证和排错。

第一遍不必逐行理解 Isaac API，只要能回答下面三个问题即可：

- 为什么采集前必须暂停 Timeline？
- 为什么要保存 `commanded_degrees` 和 `actual_degrees` 两份角度？
- 为什么不能直接把 `semantic_segmentation` 的 runtime ID 当作训练标签？

### 第二遍：在普通 Python 中做实验

阅读 [动手实验与二次开发指南.md](./动手实验与二次开发指南.md)，依次完成：

1. 运行 69 个单元测试；
2. 计算 60 Hz 物理、10 FPS 采集的帧时间；
3. 对 CSV 轨迹做线性插值；
4. 测试语义标签规范化与稳定 ID 重映射；
5. 读懂一帧 metadata 和一次 `run_config.json`；
6. 按检查表修改轨迹、相机、语义类别或渲染配置。

这些实验不要求启动 Isaac Sim，适合先把纯 Python 逻辑学扎实。

### 第三遍：进入 Isaac Sim 环境

在项目实际部署的 Linux/Isaac Sim 主机上：

1. 先做 1～3 帧静态采集；
2. 再做 2～5 帧动态采集；
3. 运行 `validate_semantic_output.py`；
4. 检查 `run_config.json`、`motion_state.jsonl` 和逐帧 metadata；
5. 最后才增加分辨率、帧数和 Path Tracing 质量。

## 两种运行环境不要混淆

| 环境 | 能做什么 | 不能直接做什么 |
|---|---|---|
| 当前 Windows + 普通 Python | 阅读代码；运行纯 Python 单元测试；研究轨迹、配置、语义映射、验证算法 | 默认不能导入 `isaacsim`、`omni.*`、`pxr` 并完成整条 GPU 采集 |
| 远端 Linux + Isaac Sim | 打开 USD、运行物理、创建 RenderProduct、执行 Replicator Writer、输出数据集 | 仍需保证项目中的绝对 USD 资产路径在该主机有效 |

默认启动脚本明确调用：

```bash
/root/isaacsim/python.sh simulation_orchestrator.py
```

默认 overlay 又引用 `/root/gpufree-data/...`，所以不能把“本地测试通过”误解为“本地
已经具备完整 Isaac 采集环境”。

## 最重要的源码阅读顺序

不要按文件名字母顺序阅读。建议按数据流阅读：

1. `simulation_orchestrator.py`：先看参数和 `main()`，建立主线。
2. `capture_timing.py`、`world_scheduler.py`：理解时间与冻结机制。
3. `joint_control_profile.py`、`articulation_stage_validator.py`：理解运动契约。
4. `articulation_adapter.py`、`excavator_joint_motion.py`：理解命令与回读。
5. `semantic_mapping.py`：理解稳定标签。
6. `capture_context.py`、`semantic_dataset_writer.py`：理解帧身份和落盘。
7. `semantic_capture_custom.py`：理解相机、RenderProduct 和 Replicator。
8. `render_profile.py`、`stage_preflight.py`：理解配置审计和运行前检查。
9. `validate_semantic_output.py`：从“结果必须满足什么”倒推设计意图。
10. `tests/`：用小例子验证自己的理解。

## 当前版本的关键事实

- 默认 renderer：`RealTimePathTracing`。
- 可选 renderer：`PathTracing`。
- 默认分辨率：1280×720。
- 默认物理频率：60 Hz。
- 默认采集频率：10 FPS，即每次采集间隔 6 个物理步。
- 默认帧 0000：数据集时间 `t=0`。
- 默认动态关节顺序：`cab, boom, small_arm, bucket`。
- 关节控制：一次批量写入 4 个 DOF 的位置，并把对应速度清零。
- 角度输入/记录单位：度；Isaac Articulation 调用前转换为弧度。
- 默认关节回读容差：0.05°。
- 默认语义数据类型：`uint16`。
- 背景 ID：0；未知类 ID：65535。
- 输出总清单：`run_config.json`，schema v3。
- 当前普通 Python 测试基线：69 个测试通过。

## 学完后的验收标准

如果你能独立完成以下任务，就已经真正掌握了这个项目：

- 用公式解释某个 `frame_id` 对应多少物理步和多少数据集时间；
- 画出“轨迹采样 → 关节命令 → 物理步 → 实际回读 → 冻结 → 相机采集”的顺序；
- 说明 Articulation 静态预检为什么禁止 Angular Drive；
- 根据语义 mapping 添加一个新类别并说明如何验证；
- 区分 `simulation_time`、`dataset_time`、`timeline_time` 和 `trajectory_time`；
- 从 `run_config.json` 判断一次运行是否可作为生产数据；
- 从某一帧 metadata 追溯它的 RGB、语义 ID、相机变换和关节状态；
- 修改配置后先做最小采集，再运行验证器，而不是直接生成大批数据。
