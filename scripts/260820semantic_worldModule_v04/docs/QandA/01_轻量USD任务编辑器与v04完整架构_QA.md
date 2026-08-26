# Semantic World Module v04：轻量 USD 任务编辑器与完整架构问答

> 整理日期：2026-08-20  
> 内容范围：关于独立轻量 Omniverse Kit/USD 任务编辑器，以及 Semantic Capture Studio + Headless Runtime 的两轮完整问答。

---

## 第一轮：能否构建独立的轻量 USD 查看与采集任务编辑器

### 用户问题

能不能只使用Omniverse或者isaac读取usd的部分（我不是很深入了解它们的具体模块），交互时不需要启用isaac sim中比较重的部分，也不作为依托isaac sim gui才能启动的东西，而是做成一个新的类似轻量的usd查看器一样的东西，然后选择传感器，每个传感器对应的采集场景，要采集的图像种类，并且保存为可复用的一套内容，下次如果想做点修改就在这上面做点轻量修改就可以不需要整套重选。

### Codex 回答

可以，而且这是比“完整 Isaac Sim + 面板”更合适的方向。

核心思路是：

> 不把它做成 Isaac Sim 插件，而是做成一个独立的轻量 Omniverse Kit 应用，专门负责 USD 查看、传感器选择和采集任务编排。

Isaac Sim 本身也是构建在 Omniverse Kit 上的应用。Kit 允许通过 `.kit` 文件只加载需要的 Extension，因此可以构建自己的独立程序，而不加载 PhysX、仿真循环、Replicator Runtime、ROS、RTX Sensor Runtime 等重模块。[Omniverse 自定义应用说明](https://docs.omniverse.nvidia.com/dev-guide/latest/dev_guide/create/create.html)

## 推荐形态

可以把新工具命名为：

```text
Semantic Capture Studio
```

它是一个独立程序：

```text
semantic-capture-studio.bat
semantic-capture-studio.sh
```

不需要先打开 Isaac Sim，也不依赖 Isaac Sim GUI。

```text
┌──────── Semantic Capture Studio ────────┐
│ USD Viewport                            │
│ Stage Prim Tree                         │
│ Sensor List                             │
│ Variant Editor                          │
│ Modality Matrix                         │
│ Semantic Mapping                        │
│ Save / Load Capture Project             │
│ Validate / Submit Headless Job          │
└───────────────────┬─────────────────────┘
                    │ 保存 JobSpec
                    ▼
          Remote Headless Supervisor
                    │
                    ▼
             Isaac Sim Worker
```

Kit 官方的 Base Editor 本身就是一个只由核心 Extension 构成的轻量 USD/RTX 编辑器，包括 Viewport、Stage、Property Editor 和 Content Browser，可以直接作为这个工具的起点。[Kit Base Editor](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/106_0_highlights.html)

## 轻量查看器加载什么

建议只加载：

- OpenUSD Stage
- RTX 或基础 Hydra Viewport
- Stage Tree
- Property Editor
- Content Browser
- `omni.ui`
- 选择与高亮功能
- 自己的采集任务编辑 Extension
- 必要的 Camera/OmniSensor USD Schema

不加载：

- PhysX
- SimulationManager
- Isaac World
- Replicator 执行模块
- ROS 2 Bridge
- Articulation Runtime
- RTX LiDAR Runtime
- Path Tracing 正式采集链路
- Timeline 仿真循环

这样它仍然可以查看 USD 几何、层级、Camera、属性和世界变换，但不会启动完整仿真。

## 能在轻量工具里完成什么

### 1. 自动扫描 USD

打开 USD 后自动发现：

- `UsdGeom.Camera`
- 带鱼眼畸变 Schema 的 Camera
- OmniLidar、OmniRadar 等传感器 Prim
- articulation root
- joints
- 语义标签
- 灯光
- 可作为场景变体根节点的 Prim

对于 Isaac 传感器，可以只加载 `omni.usd.schema.omni_sensors` 等 Schema Extension，而不加载对应的运行时传感器。Isaac 6 的 RTX Sensor 本身也区分了 USD Authoring 和 Runtime Sensor 两层。[Isaac RTX Sensor 架构](https://docs.isaacsim.omniverse.nvidia.com/latest/py/source/extensions/isaacsim.sensors.experimental.rtx/docs/index.html)

### 2. 通过 Viewport 选择传感器

例如选中 Camera 后点击：

```text
添加为传感器
```

工具自动读取：

- Prim Path
- 相机模型
- 焦距和光圈
- 分辨率相关标定
- 畸变 Schema
- 世界变换
- 已应用的 API Schema

用户只需要设置：

- 采集频率
- 输出模态
- RenderGroup
- 输出名称

### 3. 可视化创建采集场景

用户在 Viewport 或 Stage Tree 中选择挖掘机，然后点击：

```text
从当前选择创建场景变体
```

自动生成：

```json
{
  "id": "excavator_only",
  "include_paths": [
    "/World/Excavator",
    "/World/Environment/DomeLight"
  ]
}
```

还可以在轻量 Viewport 中预览：

- full_scene
- excavator_only
- front_teeth_only

这里仅切换 USD Session Layer 的可见性，不执行 Path Tracing 采集。

### 4. 图像类型使用矩阵配置

界面可以做成矩阵：

| 场景 | Boom Camera RGB | 语义 | 深度 | Roof LiDAR 点云 |
|---|---:|---:|---:|---:|
| Full Scene | ✓ | ✓ |  | ✓ |
| Excavator Only |  | ✓ |  |  |
| Front Teeth Only |  | ✓ |  |  |

这会自动生成 `modalities_by_sensor`，不再手写 JSON。

## 可复用项目如何保存

建议不要只保存一个任务 JSON，而是保存成一个采集项目目录：

```text
excavator_capture.swproject/
├─ project.json
├─ capture_job.json
├─ authoring.usda
├─ semantic_mapping.json
├─ render_profiles/
│  └─ pathtracing_64spp.json
├─ previews/
└─ history/
   ├─ job_v001.json
   └─ job_v002.json
```

其中：

- `project.json`：项目名称、Stage 地址、最近编辑状态
- `capture_job.json`：可以直接交给 v03 Supervisor
- `authoring.usda`：传感器关系、场景选择等 USD 原生信息
- `semantic_mapping.json`：稳定语义 ID
- `history`：每次修改的配置版本

下次打开项目后，所有内容都会恢复：

- USD
- 传感器列表
- Prim 绑定
- 场景变体
- 图像模态
- 渲染配置
- 输出设置
- 轨迹
- 语义映射

用户只需要修改某个传感器、增加一个变体或调整输出模态，不需要重新选择整套内容。

## JSON 和 USD 应该如何分工

推荐使用混合模式：

### USD Authoring Layer

适合保存：

- 传感器与真实 Prim 的 Relationship
- 场景 include/exclude Prim
- 相机挂载关系
- Preview 可见性
- Stage 内部对象引用

### JSON JobSpec

适合保存：

- 帧数和频率
- 输出目录
- 采集模态
- Render Profile
- Worker 分段
- 超时和重试
- 轨迹文件
- 远端执行参数

正式运行时，工具把两者解析成一份不可变的 `capture_job.json`，交给 headless Supervisor。

## 轻量工具不能代替什么

不加载完整 Isaac Runtime 时，不能真正验证：

- RTX LiDAR 是否能产生点云
- Replicator Annotator 是否正常
- Path Tracing 最终图像
- PhysX articulation 是否可以初始化
- CSV 轨迹驱动后的实际姿态
- GPU 显存是否足够

因此需要两层验证：

1. 轻量静态验证  
   检查 Prim、Schema、标定、路径、模态和配置关系。

2. 远端 Headless 冒烟验证  
   启动完整 Isaac Worker，采集 1–20 帧并返回缩略图和诊断结果。

用户点击“验证任务”后，远端运行一次短 Worker，结果回传到轻量工具中。

## 两种实现路线

### 纯 OpenUSD + Qt

优点：

- 更小
- 可以不依赖 NVIDIA RTX
- 启动更快

缺点：

- Omniverse 材质和传感器 Schema 支持较弱
- Viewport、Stage Tree、属性面板都需要自己开发
- 与 Isaac Sensor 的结合较弱

### Omniverse Kit 独立应用

优点：

- 原生 USD Stage、Viewport、选择和属性系统
- 能加载必要的 Isaac/OmniSensor Schema
- 可以使用 Omniverse 材质和 RTX Viewport
- 容易扩展为 WebRTC 流式工具
- 不需要启动完整 Isaac Sim

缺点：

- 仍然需要 Kit Runtime
- 不是几十 MB 级别的小工具
- Viewport 仍会使用一定 GPU

综合来看，推荐使用 Omniverse Kit App Template，从 USD Explorer 或 Base Editor 裁剪，而不是使用纯 Qt 从头开发。

最终系统应拆成三个独立产品：

```text
Semantic Capture Studio
    轻量 USD 查看与任务编辑

Semantic Capture Supervisor
    无 GPU 或轻量 CPU 任务管理

Semantic Capture Worker
    完整 Isaac Sim Headless 正式采集
```

这个方案能够同时满足：

- 不依赖 Isaac Sim GUI
- 配置阶段轻量
- 可视化选择传感器和场景
- 配置可以重复使用和增量修改
- 正式采集保持 headless
- 继续保留 v03 的稳定性与断点续跑

本轮只完成了架构分析，没有修改代码。

---

## 第二轮：完整的核心目标、核心思路、层次架构、实现方案和使用流程

### 用户问题

请你给出完整的核心目标，核心思路，层次架构，实现方案和预期的使用流程

### Codex 回答

建议把下一阶段定义为：

> Semantic Capture Studio：独立轻量 USD 任务编辑器  
> Semantic Capture Runtime：沿用并升级 v03 的 headless 采集内核

它不是 Isaac Sim 插件，也不依赖 Isaac Sim GUI；只有正式采集 Worker 才启动完整 Isaac Sim Headless Runtime。

# 一、核心目标

## 1. 轻量化任务编辑

用户不需要打开完整 Isaac Sim，只启动一个独立的 USD 查看器，即可：

- 打开和查看 USD Stage
- 浏览 Prim 层级
- 选择 Camera、鱼眼相机、LiDAR
- 读取已有传感器标定
- 创建采集场景
- 选择每个场景需要的模态
- 配置轨迹、渲染和输出
- 保存可复用项目

## 2. 配置可视化

消除手工操作：

- 不手写 Prim Path
- 不手写场景白名单
- 不重复填写已有相机标定
- 不手动拼接 JSON
- 不通过日志猜测配置是否正确

## 3. 项目可复用

一套配置保存后，下次打开能够完整恢复：

- Stage
- 传感器绑定
- 场景变体
- 输出模态
- 语义映射
- 轨迹
- Render Profile
- 远端运行参数

用户只修改变化的部分，不重新选择整套内容。

## 4. 正式采集始终 Headless

轻量工具只负责“任务创作与管理”。

正式采集始终运行在：

```text
External Supervisor
    └─ Headless Isaac Sim Worker
```

关闭轻量工具、关闭本地电脑界面或断开网络，都不影响远端任务。

## 5. 保留 v03 的稳定性

继续保留：

- Worker 分段
- GPU 崩溃隔离
- 心跳检测
- 超时重启
- 原子帧事务
- 提交账本
- 配置指纹
- 断点续跑
- 稳定语义 ID
- 多传感器驱动插件

# 二、核心思路

整个系统分成“创作平面”和“执行平面”。

```text
创作平面
Semantic Capture Studio
轻量 USD 查看、选择、编辑、验证、保存
                   │
                   │ 编译不可变 JobSpec
                   ▼
执行控制平面
Job Runner / Supervisor
上传任务、启动、停止、续跑、状态监控
                   │
                   ▼
执行平面
Headless Isaac Worker
完整 Isaac Runtime、RTX、Replicator、PhysX
                   │
                   ▼
数据平面
Dataset、Ledger、Manifest、Heartbeat、Logs
```

关键原则是：

> 项目文件可以反复编辑，但提交后的采集任务是不可变快照。

因此，用户继续修改项目，不会影响正在运行的任务。

# 三、层次架构

## 第 1 层：轻量 Kit 应用层

建议基于 Omniverse Kit App Template，从 USD Explorer 或 Base Editor 裁剪。

它是一个独立程序：

```text
semantic-capture-studio.bat
semantic-capture-studio.sh
```

只加载：

- OpenUSD Stage
- Stage Tree
- Property Editor
- 基础或 RTX Viewport
- Content Browser
- `omni.ui`
- USD 选择系统
- 必要的 Camera/OmniSensor Schema
- 自己的 Semantic Capture Extension

不加载：

- PhysX
- SimulationManager
- Replicator 执行链路
- ROS 2
- Isaac World
- RTX Sensor Runtime
- 正式 Path Tracing 采集
- Timeline 仿真循环

Kit 允许通过 `.kit` 文件选择应用需要的 Extension，因此可以构建独立于 Isaac Sim GUI 的应用。[Omniverse Kit 应用开发](https://docs.omniverse.nvidia.com/dev-guide/latest/dev_guide/create/create.html)

## 第 2 层：USD Stage 适配层

负责读取 Stage，但不执行仿真。

主要能力：

- 打开本地 USD 或 `omniverse://` URI
- 遍历 Prim
- 读取 Prim 类型
- 获取世界变换
- 读取应用的 API Schema
- 识别 Camera、LiDAR、Radar
- 读取相机光学和畸变参数
- 读取语义标签
- 识别 articulation 和 joint
- 读取灯光和环境节点
- 检查缺失资源和失效路径

传感器发现结果统一转换成：

```text
DiscoveredSensor
├─ prim_path
├─ prim_type
├─ sensor_type
├─ calibration
├─ schemas
├─ transform
├─ supported_modalities
└─ validation_issues
```

## 第 3 层：项目领域模型

这是整个系统的核心数据模型。

```text
CaptureProject
├─ StageReference
├─ SensorBindings[]
├─ VariantSpecs[]
├─ SemanticMapping
├─ MotionSpec
├─ RenderPresets[]
├─ OutputSpec
├─ RuntimePolicy
├─ RunnerProfile
└─ RevisionHistory
```

### SensorBinding

保存：

- 逻辑传感器 ID
- USD Prim 绑定
- 传感器类型
- 校准策略
- 分辨率
- 频率
- RenderGroup
- 可选模态
- 输出目录

### VariantSpec

保存：

- 场景名称
- include paths
- 显式 visibility
- 需要保留的灯光
- 每个传感器的输出模态

### MotionSpec

保存：

- CSV 轨迹
- articulation Prim
- DOF 与 CSV 列映射
- 角度单位
- 根位姿列
- 插值方式

### RuntimePolicy

保存：

- Worker 分段长度
- 超时
- 最大重启次数
- Headless 命令
- 断点续跑策略

## 第 4 层：项目持久化层

建议使用项目目录，而不是单个大 JSON：

```text
excavator_capture.swproject/
├─ project.json
├─ capture_job.json
├─ authoring.usda
├─ semantic_mapping.json
├─ render_profiles/
│  ├─ pathtracing_64spp.json
│  └─ realtime_preview.json
├─ runner_profiles/
├─ previews/
└─ history/
   ├─ revision_001.json
   └─ revision_002.json
```

### project.json

保存编辑器状态：

- 项目名称
- Stage URI
- 当前 Revision
- 最近选择的传感器
- UI 布局
- 最近预览的场景

### authoring.usda

保存适合 USD 表达的关系：

- 传感器 Prim Relationship
- 场景 Prim Relationship
- include/exclude 路径
- 预览可见性
- 逻辑分组

它作为独立 Layer，不修改原始场景 USD。

### capture_job.json

这是最终交给 v03 Runtime 的执行配置。

它由 Studio 自动生成，不建议用户直接维护。

### history

每次保存产生 Revision，支持：

- 查看差异
- 回退配置
- 从旧版本复制传感器
- 从旧版本恢复场景变体

## 第 5 层：任务编译与验证层

把可编辑项目编译成不可变的 JobSpec。

```text
CaptureProject
      │
      ├─ 静态验证
      ├─ 路径解析
      ├─ Schema 检查
      ├─ 模态兼容检查
      ├─ 资源哈希
      └─ 远端路径映射
      ▼
Immutable JobSpec
```

验证分成三级。

### 一级：轻量静态验证

不启动 Isaac：

- Prim 是否存在
- Prim 类型是否正确
- Camera 是否有标定
- 场景路径是否重复或冲突
- 模态是否被传感器支持
- 频率是否对齐物理步
- CSV 列是否完整
- 输出路径是否合法

### 二级：远端 Runtime Preflight

启动短生命周期 Headless Worker，但不正式采集：

- Stage 能否在远端加载
- articulation 是否能初始化
- DOF 名称是否正确
- RTX Sensor 是否能创建
- Annotator 是否可用
- Path Tracing 设置能否回读
- GPU 和驱动是否正常

### 三级：冒烟采集

采集 1、20 或跨分段帧：

- 返回 RGB 缩略图
- 返回语义彩图
- 检查语义 ID
- 检查孤立场景
- 验证边界帧连续性
- 估算速度、磁盘和完成时间

## 第 6 层：任务提交与 Runner 层

定义统一接口：

```text
RunnerBackend
├─ LocalRunner
├─ SshRunner
└─ HttpRunner
```

### LocalRunner

在本机运行 Headless Isaac。

### SshRunner

适合当前云电脑：

- 使用 SSH 公钥连接
- 上传 Job Package
- 检查资源文件
- 启动远端 Supervisor
- 拉取状态和缩略图

项目中只保存 Runner Profile 名称，不保存密码或私钥。

### HttpRunner

后续可以增加轻量任务服务：

```text
POST   /jobs
POST   /jobs/{id}/start
POST   /jobs/{id}/stop
POST   /jobs/{id}/resume
GET    /jobs/{id}/status
GET    /jobs/{id}/preview
GET    /jobs/{id}/logs
```

UI 不需要直接理解远端进程。

## 第 7 层：Supervisor 层

沿用 v03 的外部 Supervisor。

职责：

- 读取不可变 JobSpec
- 生成分段计划
- 启动 Headless Worker
- 监控心跳
- 处理超时
- 终止卡死进程
- 自动重启
- 查询提交账本
- 跳过已完成帧
- 写入最终 Manifest

Supervisor 不加载 Isaac，不占用 RTX 渲染资源。

## 第 8 层：Headless Worker 层

这是唯一加载完整 Isaac Sim Runtime 的部分。

内部继续使用 v03 架构：

```text
Worker
├─ Stage Loader
├─ Render Profile
├─ World Controller
├─ Motion Driver
├─ Variant Controller
├─ Sensor Registry
├─ RenderGroup Manager
├─ Capture Coordinator
├─ Transaction Sink
└─ Commit Ledger
```

传感器仍然通过插件扩展：

```text
camera.pinhole
camera.fisheye_opencv
lidar.rtx.rotary
lidar.rtx.solid_state
radar.custom
```

Studio 只读取传感器描述信息；真正的运行时验证和采集在 Worker 中进行。

## 第 9 层：数据与可观测性层

标准输出结构：

```text
output/
├─ sensor_id/
│  ├─ full_scene/
│  │  └─ frame_00000000/
│  │     ├─ rgb.png
│  │     ├─ semantic_class_id.npy
│  │     ├─ semantic_color.png
│  │     └─ packet.json
│  └─ excavator_only/
└─ .v03/
   ├─ commits.jsonl
   ├─ manifest.json
   ├─ heartbeats/
   ├─ logs/
   └─ transactions/
```

Studio 的监控界面只读取状态文件和缩略图，不连接 Worker 内部对象。

# 四、核心界面设计

## 1. Project 面板

- 新建项目
- 打开项目
- 复制项目
- 保存 Revision
- 查看历史差异
- 设置本地/远端资源映射

## 2. Stage 面板

- USD Viewport
- Prim Tree
- 搜索和类型过滤
- Camera/LiDAR 专用过滤
- 语义标签过滤
- 显示选中 Prim 的路径和 Schema

## 3. Sensors 面板

```text
发现的传感器
✓ Boom Camera
✓ Front Fisheye
□ Roof LiDAR
```

选择传感器后显示：

- Prim Path
- 类型
- 标定
- 分辨率
- 频率
- 模态
- 健康状态
- Frustum 或扫描范围

## 4. Variants 面板

支持：

- 从当前 Viewport 选择创建变体
- 从 Prim 子树创建变体
- 添加必须保留的灯光
- 预览隔离结果
- 比较两个变体差异
- 复制变体

## 5. Modality Matrix

| 场景 | Camera RGB | Camera 语义 | Camera 深度 | LiDAR 点云 |
|---|---:|---:|---:|---:|
| Full Scene | ✓ | ✓ |  | ✓ |
| Excavator |  | ✓ |  |  |
| Front Teeth |  | ✓ |  |  |

## 6. Run 面板

- Validate
- Remote Preflight
- Capture 1 Frame
- Capture 20 Frames
- Start Production
- Stop
- Resume
- 查看 ETA
- 查看 GPU、磁盘、当前帧和 Worker

## 7. Results 面板

- RGB 缩略图
- 语义彩图
- RGB/语义叠加
- 点击像素查看 semantic ID
- 查看类别统计
- 检查缺帧
- 打开输出目录

# 五、预期使用流程

## 第一次创建项目

1. 启动 Semantic Capture Studio。
2. 新建 Capture Project。
3. 打开 USD Stage。
4. Studio 扫描 Camera、LiDAR、articulation 和语义 Prim。
5. 用户勾选需要使用的传感器。
6. Studio 自动读取 Camera/传感器参数。
7. 用户在 Viewport 选择挖掘机并创建 `excavator_only`。
8. 选择五个前齿并创建 `front_teeth_only`。
9. 在模态矩阵中配置每个场景输出。
10. 导入语义映射或使用映射编辑器生成稳定 ID。
11. 导入轨迹 CSV，完成关节列映射。
12. 选择 Path Tracing 预设。
13. 配置远端 Runner。
14. 执行静态验证。
15. 执行远端单帧和跨分段冒烟测试。
16. 测试通过后提交正式任务。
17. 关闭 Studio，远端继续 Headless 采集。
18. 下次打开 Studio 查看进度或结果。

## 下次修改项目

1. 打开原来的 `.swproject`。
2. Stage、传感器、变体和模态全部自动恢复。
3. 修改某个传感器频率或增加一个相机。
4. 保存为新 Revision。
5. Studio 只提示受影响内容。
6. 重新执行静态验证和短冒烟测试。
7. 生成新的 JobSpec。
8. 提交新任务。

不需要重新选择原有传感器和场景。

# 六、状态生命周期

```text
Draft
  ↓
Static Valid
  ↓
Remote Preflight Passed
  ↓
Smoke Test Passed
  ↓
Ready
  ↓
Running
  ├─ Paused
  ├─ Recovering
  ├─ Failed
  └─ Complete
```

每次正式提交都保存：

- 项目 Revision
- JobSpec
- Stage 哈希
- Render Profile 哈希
- Semantic Mapping 哈希
- 轨迹哈希
- Runtime 版本
- Isaac Sim 版本

确保以后可以复现。

# 七、推荐实施阶段

## 阶段一：核心数据模型

- 抽离纯 Python `semantic_capture_core`
- 定义 CaptureProject
- 定义项目文件格式
- 实现 Project → v03 JobSpec 编译
- 实现 Revision 和配置差异

## 阶段二：轻量 Studio MVP

- 独立 Kit App
- USD Viewport
- Stage Tree
- 传感器扫描
- Prim 选择器
- Sensor/Variant/Modality 编辑
- 保存和打开项目
- 导出 v03 配置

## 阶段三：远端工作流

- SSH Runner
- 远端资源检查
- Preflight
- 冒烟测试
- 正式启动
- 心跳和账本监控
- 日志查看

## 阶段四：结果与质量工具

- RGB/语义预览
- 语义 ID 查询
- 缺帧检查
- 类别统计
- 边界连续性检查
- 磁盘与时间估算

## 阶段五：高级扩展

- LiDAR/Radar 可视化
- 自定义传感器描述插件
- HTTP Job Service
- 多台云电脑调度
- Nucleus 资产路径
- WebRTC 远程 Studio

# 八、最终定位

最终不应把它理解成“v03 加一个 UI”，而应该是：

```text
Semantic Capture Studio
负责创作和管理

Semantic Capture Core
负责项目模型和配置编译

Semantic Capture Supervisor
负责稳定调度

Semantic Capture Worker
负责 Headless Isaac 采集
```

其中 v03 不需要推翻，而是成为底层可靠执行引擎。新的轻量 Studio 解决易用性、可视化选择和配置复用问题；正式采集继续保持完全 Headless。本轮仅完成方案设计，没有修改代码。
