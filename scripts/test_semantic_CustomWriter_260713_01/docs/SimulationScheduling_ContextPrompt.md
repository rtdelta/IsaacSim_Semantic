# Isaac Sim 语义采集与仿真调度项目上下文 Prompt

## 使用方式

将本文档完整提供给另一个 Codex/ChatGPT 窗口，使其快速理解当前项目、已有实现和最近关于仿真推进方式的讨论。在继续设计或修改代码之前，应先检查本文列出的实际文件，不要只依据概念描述猜测当前实现。

---

## 可直接交给另一个窗口的 Prompt

你正在协助我继续开发一个 Isaac Sim 自定义语义数据采集项目。请先完整理解以下背景，再回答问题或实施后续修改。

### 1. 项目目标

项目使用 Isaac Sim 加载一个包含机械臂、相机和语义标签的 USD Stage，通过 Replicator 采集：

1. RGB PNG。
2. Isaac Runtime Semantic ID NPY，仅用于调试和追溯。
3. 稳定的 Dataset Semantic ID NPY，作为正式语义标签数据。
4. 根据自定义 `semantic label -> dataset ID -> RGB color` mapping 生成的彩色语义 PNG。
5. 每帧 JSON metadata，包括 Runtime ID 映射、类别像素数和未知标签等信息。

这里不能直接把 Isaac Runtime Semantic ID 当作数据集类别 ID，因为 Runtime ID 可能随运行、Stage 或 Isaac Sim 版本发生变化。正式语义链路是：

```text
Isaac Runtime ID
  -> semantic annotator 的 idToLabels
  -> 规范化后的最终 semantic label
  -> semantic_mapping.json
  -> 稳定 Dataset Class ID
  -> semantic_id_XXXX.npy
  -> 自定义颜色 LUT
  -> semantic_color_XXXX.png
```

### 2. 多级语义标签规则

USD 父子层级继承后，`idToLabels` 中可能出现多个逗号分隔的标签，例如：

```json
{"class": "simpleroom,towelroom01wallside"}
```

项目约定：

```text
按逗号切分
-> 去除空白和空字符串
-> 只取最后一个非空标签
```

因此上例最终 mesh 标签为：

```text
towelroom01wallside
```

mapping 提取阶段和逐帧 Writer 重映射阶段必须使用完全相同的规范化规则，不能在两处采用不同解释。

### 3. 本地和远程位置

本地项目目录：

```text
D:\learning\IntelligentDepartment\CodesSet\Self\260707IsaacSIm\scripts\test_semantic_CustomWriter_260713_01
```

远程项目目录：

```text
/root/gpufree-data/wyb/test_semantic_CustomWriter_260713_01
```

远程 USD 的当前默认位置：

```text
/root/gpufree-data/wyb/Semantic_260709_01.usd
```

远程 SSH 连接信息：

```text
IP: 183.147.142.40
Port: 30745
User: root
Password: afemh7ch
```

SSH 命令：

```bash
ssh -p 30745 root@183.147.142.40
```

连接后若继续部署、测试或检查代码，应优先进入：

```bash
cd /root/gpufree-data/wyb/test_semantic_CustomWriter_260713_01
```

### 4. 当前主要文件及职责

```text
run_capture_remote.sh
    设置 HOME、TMPDIR、CUDA/OptiX Cache 等远程运行目录，
    使用 /root/isaacsim/python.sh 启动主脚本。

semantic_capture_custom.py
    解析命令行参数；启动 SimulationApp；加载 USD；检查 Camera 和语义标签；
    创建 RenderProduct、DiskBackend 和自定义 Writer；触发采集；最后释放资源。

semantic_dataset_writer.py
    实现 SemanticDatasetWriter；注册 rgb 和 semantic_segmentation annotator；
    将 Runtime ID 重映射为稳定 Dataset ID；生成自定义颜色 PNG；
    调度 RGB、NPY、PNG 和 JSON 写盘。

semantic_mapping.py
    负责标签规范化、mapping schema 校验、Runtime ID 到 Dataset ID 的映射、
    Dataset ID 到 RGB 的 LUT 颜色化。

extract_semantic_mapping.py
    从 USD Semantic Label 中提取类别并构造 semantic_mapping.json。

semantic_mapping.json
    冻结后的 Label、Dataset ID 和 RGB Color 配置。

validate_semantic_output.py
    独立验证 NPY 的 dtype、shape、ID 合法性，并根据 mapping 重建 PNG，
    与实际 PNG 做逐像素一致性比较。
```

### 5. 当前相机数据采集链路

```text
USD Stage
  -> Camera Prim
  -> RenderProduct（Camera + Resolution）
  -> RTX Renderer / Synthetic Data RenderVars
  -> RGB Annotator
  -> Semantic Segmentation Annotator（colorize=False）
  -> SemanticDatasetWriter.write(data)
  -> Runtime ID NPY
  -> idToLabels
  -> semantic_mapping.json
  -> Dataset ID NPY
  -> 自定义颜色 PNG
  -> DiskBackend
```

Camera 决定观察位置、方向和投影模型；RenderProduct 绑定 Camera 和输出分辨率；Renderer 根据场景、材质、灯光和可见性产生渲染数据；Annotator 从 RenderProduct 提取 RGB 或语义数据；Writer 负责语义重映射、颜色化、编号和写盘。

### 6. 当前多帧采集实现的关键事实

当前 `semantic_capture_custom.py` 的核心循环是：

```python
for _ in range(args.frames):
    rep.orchestrator.step(
        rt_subframes=args.rt_subframes,
        delta_time=0.0,
    )
```

这段逻辑能够连续写出多个编号的数据文件，但它不等于采集机械臂运动过程：

1. `rep.orchestrator.step()` 会触发当前 RenderProduct 的渲染、Annotator 计算和 Writer 写出。
2. `delta_time=0.0` 表示这次采集不主动推进仿真时间。
3. `rt_subframes` 是 RTX 渲染子帧数量，不是物理仿真步数。
4. 因此，若没有其他程序修改场景，当前多帧通常是同一个仿真时刻的重复观测。

不要把物理帧、传感器采集帧和 RTX 渲染子帧混为一谈：

```text
多个 Physics Step
  -> 到达一个传感器采样时刻
  -> 触发一个 Capture Frame
  -> 当前 Capture Frame 内可以使用多个 RTX Subframe
```

### 7. USD 内机械臂可以自主运动时，是否仍需推进仿真

结论：通常仍然需要推进仿真，只是不再需要采集脚本逐帧计算并下发机械臂控制命令。

“自主运动”和“仿真时间推进”是两个不同职责：

```text
机械臂控制逻辑
    决定机械臂应该如何运动。

仿真调度逻辑
    推进 Timeline、Physics、Controller、Action Graph 和 Script Behavior，
    使机械臂真正运动到下一个仿真时刻。
```

不同运动来源与时间推进关系如下：

| 运动来源 | 是否需要推进 | 原因 |
|---|---:|---|
| USD Time Samples/关键帧动画 | 需要 | Timeline 时间变化后才会求值到新姿态 |
| Articulation Controller | 需要 | 控制器和关节动力学依赖 Physics Step |
| OmniGraph/Action Graph | 需要 | Playback Tick 等执行节点依赖 Timeline Tick |
| Script Behavior | 需要 | 行为通常依赖应用更新或物理回调 |
| 重力、碰撞和关节动力学 | 需要 | 物理引擎必须执行时间步 |
| ROS 外部控制 | 通常需要 | Isaac Sim 仍需处理消息、控制和物理更新 |
| 外部进程直接写 Prim Transform | 视架构而定 | 外部进程可能负责状态变化，但渲染和采集仍需刷新 |

加载一个包含自主行为的 USD，并不自动保证 Timeline 已经播放，也不保证物理、Action Graph 或控制器正在获得 Tick。

### 8. 成熟架构应由谁推进仿真

结论：应由一个总调度器统一推进仿真状态，相机是传感器和观察者，不应该各自推进仿真时间。

成熟职责划分建议如下：

```text
Simulation Runner / 总调度器
├── 管理 SimulationApp、World/SimulationContext 和 Timeline
├── 维护唯一权威仿真时钟
├── 推进 Physics Step
├── 让机械臂控制器、动画和 Action Graph 执行
├── 判断哪些传感器在当前时刻需要采样
└── 统一触发相机、激光雷达和机器人状态记录

Camera Sensor / 相机模块
├── 管理 Camera Prim
├── 管理 RenderProduct
├── 管理分辨率和相机参数
├── 挂载或关联 Annotator/Writer
└── 在总调度器指定的仿真时刻采集，不拥有仿真时钟

Semantic Writer / 数据输出模块
├── 接收同一采集时刻的 Annotator 数据
├── Runtime ID -> Dataset ID
├── Dataset ID -> 自定义 RGB
└── 保存 NPY、PNG、RGB 和 metadata
```

整个程序只能有一个负责推进时间的权威组件。不能让每台相机分别调用一次会推进时间的 `step()`，否则会产生传感器时间错位。例如：

```text
错误：
Camera A 推进一次并采集 t=0.0167
Camera B 再推进一次并采集 t=0.0333

正确：
总调度器推进一次到 t=0.0167
  -> Camera A 采集
  -> Camera B 采集
  -> LiDAR 采集
  -> 记录机械臂状态
```

### 9. 推荐的仿真与采集时序

例如物理频率为 60 Hz、相机频率为 10 Hz：

```text
physics_dt = 1 / 60 s
capture_interval = 1 / 10 s
每采集一帧前推进 6 个物理时间步
```

推荐执行顺序：

```text
启动 SimulationApp
  -> 加载 USD 并等待完成
  -> 初始化 World/SimulationContext
  -> 创建全部 Camera 和 RenderProduct
  -> 创建并 attach Writer
  -> 启动 Timeline
  -> 执行必要的预热/稳定物理步
  -> 总调度器推进 Physics Step
  -> 更新机械臂、动画和行为图
  -> 判断当前仿真时间是否到达传感器采样点
  -> 到达采样点时触发全部同频相机
  -> Annotator 计算
  -> Writer 写出同一时间戳的数据
  -> 继续推进仿真
  -> 结束后等待异步写盘完成
  -> detach、destroy、close
```

建议把以下参数分开，不要只保留一个模糊的 `frames` 概念：

```text
physics_dt 或 simulation_hz
    决定物理仿真的时间分辨率。

capture_interval 或 capture_hz
    决定传感器隔多少仿真时间保存一次数据。

capture_frames 或 duration
    决定最终采集帧数或仿真持续时间。

rt_subframes
    决定单个采集时刻的 RTX 渲染子帧数，不用于推进物理。
```

### 10. Replicator Orchestrator 的正确定位

`rep.orchestrator.step()` 应由总调度器调用，不能由多个相机对象分别调用并各自推进时间。

可以考虑两种上层策略：

#### 策略 A：总调度器推进物理，Replicator 只采集当前状态

```text
World/SimulationContext 统一推进物理
  -> 到达采样时刻
  -> Replicator 以不额外推进时间的方式触发渲染和 Writer
```

该策略职责清晰，更适合机械臂、多传感器、不同采样频率和严格时间同步。实施时必须结合当前 Isaac Sim 版本验证 Timeline、World Step 和 Replicator Step 的具体配合，避免一次循环中意外推进两次。

#### 策略 B：由 Replicator Orchestrator 统一推进时间并采集

```text
总调度器
  -> 调用一次 Replicator Orchestrator
  -> 统一推进时间、渲染和写出
```

该策略适合较简单、以 Replicator 为中心的数据生成任务。即使采用此策略，Orchestrator 仍然是总调度器调用的统一入口，而不是每台相机各自拥有一个仿真步进循环。

### 11. 当前代码与成熟架构之间的关系

当前 `semantic_capture_custom.py` 是极简原型，同时承担：

```text
应用启动
+ Stage 加载
+ 参数检查
+ 相机和 RenderProduct 创建
+ Writer 创建
+ 采集调度
+ 生命周期关闭
```

单相机原型阶段这样组织可以工作。后续进入机械臂连续运动、多相机或多传感器采集时，建议按职责逐步拆分为：

```text
simulation_runner.py
    唯一仿真主循环、Timeline 和物理时间推进。

capture_scheduler.py
    不同传感器频率、采样时刻、统一 frame/time 标识和同步策略。

camera_sensor.py
    Camera、RenderProduct、相机参数和采集接口。

robot_controller.py
    若 USD 内已包含自主控制，可负责启动、监测和状态读取，
    不一定需要重新实现关节运动算法。

semantic_dataset_writer.py
    保留现有语义重映射、颜色化和写盘职责。
```

是否立即拆成多个文件应根据下一步需求决定，不要为了形式进行无关重构。无论是否拆文件，都必须在逻辑上保持单一仿真时钟和统一步进责任。

### 12. 后续继续工作时必须遵守的约束

1. 先读取实际代码，再判断 Isaac Sim 生命周期和 Replicator 调用方式。
2. 不要让 Camera 类或每个 RenderProduct 单独推进仿真。
3. 不要把 `rt_subframes` 当作物理步数。
4. 多相机同一逻辑帧必须先统一推进一次状态，再从同一状态采集全部相机。
5. metadata 后续应增加明确的 `simulation_time`、物理步号和采集帧号，不能只依赖文件序号表达时间。
6. 必须明确谁负责 Timeline `play/pause/stop`，不能假设打开 USD 后自主行为会自动运行。
7. 必须避免 World/SimulationContext 和 Replicator 在同一循环中重复推进时间。
8. 保留现有稳定 Dataset ID NPY 和自定义颜色 PNG 的算法，不要退回 Isaac 默认随机/运行时颜色映射。
9. 保留“继承多个 class 标签时只取最后一个标签”的规则。
10. 正式实现前，应确认机械臂运动究竟来自 USD 动画、Articulation Controller、Action Graph、Script Behavior 还是 ROS，因为不同来源的启动与 Tick 条件不同。

### 13. 建议优先阅读顺序

请按以下顺序检查项目：

```text
1. semantic_capture_custom.py
   确认当前 SimulationApp、Stage、RenderProduct 和 orchestrator.step 调用。

2. semantic_dataset_writer.py
   确认 Writer 注册的 Annotator、逐帧编号和写盘行为。

3. semantic_mapping.py
   确认标签规范化、Runtime ID 重映射和颜色 LUT。

4. semantic_mapping.json
   确认冻结的数据集类别和颜色定义。

5. run_capture_remote.sh
   确认远程 Isaac Python 与缓存环境。

6. USD Stage 中的机械臂驱动结构
   确认自主运动来源、Timeline/Physics 依赖和执行图入口。
```

### 14. 当前讨论形成的最终原则

```text
总调度器拥有仿真时间
机械臂控制系统产生运动意图
Physics/Timeline 把意图推进为新状态
相机在指定仿真时刻观察状态
RenderProduct 和 Annotator生成数据
Custom Writer 完成稳定语义转换和写盘
```

一句话总结：

> USD 中机械臂能够自主运动，只能免除采集脚本直接控制机械臂，不能免除统一推进 Timeline/Physics；成熟项目应由总调度器维护唯一仿真时钟并统一触发所有传感器，相机本身不负责推进仿真。

在接到下一项任务后，请先说明你确认到的机械臂运动来源和当前时间推进方式，再提出修改方案；除非用户明确要求实现，否则先不要改代码。
