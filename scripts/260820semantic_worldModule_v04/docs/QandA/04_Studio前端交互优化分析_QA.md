# Studio 前端交互优化分析问答

## 用户问题

我想做几个优化：

1. open project增加一个打开文件管理器进行可视化选择的办法
2. 每个相机sensor每个场景变体，可启用rgb图，深度图，senmantic id npy文件和semantic color图这四个选项，用勾选方式说明是否开启，每个相机sensor也更方便的选择启用哪些场景变体，
3. 场景变体的创建也不够简洁

现在我需要你从前端交互界面的使用者角度，提出一些改进，使得用起来更顺畅，使用时尽量少打字

先不要进行代码修改，先思考使用流程的可能改进思路，不要完全按照我之前提出的方案进行规划，我的想法并不成熟，在我的方案基础上进行多角度思考分析与互补拓展，必要时可以推翻

## 回答

我建议不要只在当前长滚动面板上增加几个按钮，而是把 UI 从“按内部模块罗列参数”重构成“按用户完成任务的顺序组织”。

当前 UI 最大的问题不是功能少，而是用户必须理解 `Prim Path`、插件 ID、Variant、Modality Matrix、Load/Apply 等内部概念，才能完成一次很普通的采集任务。

本轮只分析，不修改代码。

## 一、当前 UI 的主要问题

### 1. 操作顺序不够明确

当前界面按代码模块排列：

```text
Project
Stage
Sensors
Rigs
Variants
Render
Capture
Execution
Motion
Semantic
Modality Matrix
Run
```

但普通用户实际思考过程是：

```text
打开项目
→ 看场景
→ 选择传感器
→ 选择要采集的场景状态
→ 勾选输出类型
→ 设置帧数
→ 检查并运行
```

两种顺序并不一致。

### 2. 文本输入过多

目前需要手工输入：

- Project 路径；
- USD 路径；
- Output 路径；
- Sensor Plugin ID；
- Sensor ID；
- Prim Path；
- Include Paths；
- Variant ID；
- Modality 名称；
- 多个 JSON。

这会产生大量拼写错误，也让用户必须记住内部名称。

### 3. `Load row → 修改 → Apply row` 不直观

当前 Modality Matrix 一次只能编辑一个“传感器 × Variant”组合，用户必须：

1. 输入 Variant ID；
2. 输入 Sensor ID；
3. 点击 `Load row`；
4. 修改模态字符串；
5. 点击 `Apply row`。

当有三个相机、四个 Variant 时，这个流程会非常繁琐。

### 4. Variant 创建暴露了过多底层概念

用户真正想表达的是：

```text
只看挖掘机
只看前齿
隐藏环境
保留灯光
```

但当前需要手工理解和填写：

```text
Include paths
Protected paths
Prim Path
```

这不是最符合用户思维的交互方式。

### 5. 高级功能占据了主要界面

Rig、执行超时、Motion JSON、Semantic Options、插件参数等都很重要，但并不是每次创建项目都需要操作。

它们现在和最常用功能处于同一层级，导致界面显得很长、很重。

## 二、建议的整体交互架构

建议把当前单列滚动面板改成“六步任务导航”：

```text
┌───────────────────────────────────────────────────────┐
│ Semantic Capture Studio       [保存] [项目名称] [状态] │
├────────────────┬──────────────────────────────────────┤
│ 1 项目与场景    │                                      │
│ 2 选择传感器    │              当前步骤                │
│ 3 场景变体      │                                      │
│ 4 采集内容      │                                      │
│ 5 渲染与帧数    │                                      │
│ 6 检查并运行    │                                      │
│                │                                      │
│ ▸ 高级设置      │                                      │
└────────────────┴──────────────────────────────────────┘
```

每一步只显示当前需要的信息。

高级功能放入：

```text
高级设置
├─ Sensor Overrides
├─ Rigs / Sync Groups
├─ Motion / Trajectory
├─ Semantic Mapping
├─ Long-job Execution
└─ Plugin Details
```

这样普通采集不需要接触 JSON，但专家功能仍然保留。

## 三、项目打开方式的改进

你的第一点非常必要，但不建议只加一个普通文件选择按钮。

### 建议的项目入口

启动 Studio 后首先显示：

```text
新建项目
打开项目
最近使用
```

例如：

```text
┌─ Semantic Capture Studio ─────────────────────┐
│                                               │
│  [ 新建项目 ]       [ 打开项目… ]             │
│                                               │
│  最近项目                                     │
│  ○ my_capture.swproject                       │
│    combine_scene_05.usda · 昨天               │
│                                               │
│  ○ lidar_capture.swproject                    │
│    mine_scene.usd · 3天前                      │
└───────────────────────────────────────────────┘
```

### `打开项目…` 应该选择目录

因为 `.swproject` 实际上是一个工程目录，而不是单独文件，所以文件管理器应该：

- 选择 `.swproject` 目录；
- 自动识别其中的 `project.json`；
- 隐藏 `.revisions` 等内部文件；
- 显示项目名称、USD 路径、最后修改时间；
- 记住上一次打开的位置；
- 提供常用目录快捷入口。

例如：

```text
/root/gpufree-data/semantic/projects
/root/gpufree-data/semantic/IsaacSim_Asset
/root/gpufree-data/semantic/output
```

### 还应该一起改进的路径字段

不只 Project，以下字段都应增加可视化选择：

| 字段 | 建议选择器 |
|---|---|
| Project directory | `.swproject` 目录选择器 |
| USD path | `.usd/.usda/.usdc` 文件选择器 |
| Output root | 目录选择器 |
| CSV source | `.csv` 文件选择器 |
| Semantic mapping | `.json/.yaml` 文件选择器 |

因为项目整体运行在云电脑，所以这里打开的应该是云电脑 Linux 文件系统，而不是本地 Windows 文件系统。

## 四、Stage 与 Sensor 应合并为“选择传感器”

普通用户不应该先理解 Stage，再理解 Sensor Plugin。

建议打开 USD 后自动执行：

1. 加载 Stage；
2. 索引 Prim；
3. 自动发现所有兼容传感器；
4. 根据 USD Schema 自动判断类型；
5. 显示成可勾选列表。

### 建议界面

```text
选择传感器

搜索：[ Camera________________ ]  类型：[全部 ▼]

☑ Boom Camera
  类型：OpenCV Pinhole Camera
  Prim：/Excavator_Fangshan_03/boom_prim/Camera
  状态：可用
  [在视口中定位] [查看参数]

☐ Rear Camera
  类型：Pinhole Camera
  Prim：/Excavator_Fangshan_03/rear/Camera
  状态：可用

☐ Roof Lidar
  类型：RTX LiDAR
  Prim：/World/Sensors/Lidar
  状态：可用
```

用户只需要勾选，不需要手工输入：

```text
pinhole_camera
```

插件 ID 应由系统自动判断。

### Sensor ID 自动生成

选中传感器后自动生成：

```text
Boom Camera → boom_camera
```

Sensor ID 可以在高级或详情中修改，但不应要求用户第一次就填写。

### 参数读取方式

默认显示：

```text
参数来源：USD Stage
分辨率：1280 × 720
镜头模型：OpenCV Pinhole
内参：已读取
世界变换：已读取
```

只有点击：

```text
覆盖参数
```

才展开 Overrides。

这样能明确表达：系统默认使用 USD 中已有参数，不需要用户抄写。

## 五、不要把四个模态硬编码进传感器数据模型

你提出每个相机显示四个勾选项，这个方向在交互上正确，但不建议把它硬编码成“相机永远只有四种输出”。

未来可能继续增加：

- Surface Normal；
- Instance ID；
- Optical Flow；
- Bounding Box；
- Motion Vector；
- 相机标定；
- 新类型深度；
- 新插件自己的模态。

因此更合理的设计是：

- 普通模式显示四个最常用采集类别；
- 复选项由插件 Capability 自动生成；
- 其他模态放进“更多输出”；
- LiDAR 自动显示自己的点云选项。

### 相机普通模式

```text
☑ RGB
☑ Depth
☑ Semantic ID
☑ Semantic Color
[更多输出…]
```

### LiDAR 普通模式

```text
☑ Point Cloud
☐ PLY
[更多输出…]
```

这样既符合你当前需求，又不会破坏传感器插件化架构。

## 六、Depth 不能只写“深度图”

这里需要对你的方案做一点调整。

目前 Runtime 实际支持：

```text
depth_linear → 原始深度 NPY
depth_color  → 可视化深度 PNG
```

如果 UI 只显示一个 `Depth` 勾选框，用户不知道最后得到的是数据文件还是彩色预览。

建议采用一个主勾选框加轻量选项：

```text
☑ Depth    输出：[原始数据 + 彩色预览 ▼]
```

下拉选项：

```text
原始深度 NPY
彩色预览 PNG
原始数据 + 彩色预览
```

普通用户只做一次选择，不需要理解内部模态 ID。

后台映射为：

| UI 选择 | Runtime 模态 |
|---|---|
| 原始深度 | `depth_linear` |
| 彩色预览 | `depth_color` |
| 两者 | `depth_linear + depth_color` |

同样，Semantic ID 应明确标注：

```text
Semantic ID（NPY，训练数据）
Semantic Color（PNG，可视化）
```

避免用户误以为两者内容相同。

## 七、用可视化表格代替当前 Modality Matrix

建议把“传感器是否采集某个 Variant”和“输出哪些模态”合并成一个可视化采集计划。

### 推荐界面

选择传感器：

```text
传感器：[ Boom Camera ▼]
```

下面直接显示：

| 场景变体 | 启用 | RGB | Depth | Semantic ID | Semantic Color |
|---|---:|---:|---:|---:|---:|
| Full Scene | ☑ | ☑ | ☐ | ☑ | ☑ |
| Excavator Only | ☑ | ☑ | ☐ | ☑ | ☑ |
| Front Teeth Only | ☐ | ☐ | ☐ | ☐ | ☐ |

这样用户可以直接看到：

- 这个传感器启用了哪些 Variant；
- 每个 Variant 输出什么；
- 哪个组合没有启用。

不再需要输入：

```text
Variant ID
Sensor ID
rgb;semantic_id;semantic_color
```

也不再需要：

```text
Load row
Apply row
```

点击复选框后直接修改内存配置，项目顶部显示：

```text
● 有未保存修改
```

最后统一点击一次 `保存`。

### 批量预设

表格上方提供：

```text
[RGB + 语义]
[全部常用输出]
[仅语义]
[全部关闭]
[应用到所有相机]
```

例如点击 `RGB + 语义`，自动勾选：

```text
RGB
Semantic ID
Semantic Color
```

点击 `仅语义`，自动勾选：

```text
Semantic ID
Semantic Color
```

对于多个相机，这会大幅减少重复操作。

## 八、场景 Variant 应改为“场景变体生成器”

当前 `Variant ID + Include paths` 太接近底层实现。

建议点击：

```text
+ 新建场景变体
```

弹出一个创建向导。

### 第一步：选择创建方式

```text
● 只显示选中的对象
○ 隐藏选中的对象
○ 完整场景副本
○ 高级路径配置
```

普通用户大多数时候选择：

```text
只显示选中的对象
```

### 第二步：在 Stage 树中选择对象

```text
搜索：[ Excavator____________ ]

☑ /Excavator_Fangshan_03
  ☐ track_prim
  ☐ boom_prim
  ☐ arm_prim
  ☐ bucket_prim
```

也提供：

```text
[使用当前 Viewport/Stage 选中对象]
```

这样用户可以在 Viewport 中点挖掘机，再点击一次创建 Variant，不需要复制 Prim Path。

### 第三步：环境保留选项

```text
☑ 保留灯光
☐ 保留地面
☐ 保留天空
☑ 始终保留采集传感器
```

这一步很重要。当前手工 Include Paths 很容易把灯光一起隐藏，导致 Excavator Only 的 RGB 图发黑。

系统应自动把灯光加入 `protected_paths` 或等效配置。

### 第四步：自动命名

选择 `/Excavator_Fangshan_03` 后，自动建议：

```text
显示名称：Excavator Only
内部 ID：excavator_only
```

普通用户只需要确认，不必自己想合法 ID。

### Variant 列表

创建后显示成卡片：

```text
Full Scene
完整场景 · 系统默认
[预览]

Excavator Only
只显示：/Excavator_Fangshan_03
保留灯光：是
[预览] [复制] [编辑] [删除]
```

### 建议增加预览

点击 `预览` 后，只在 Studio Session Layer 中应用可见性，然后更新 Viewport。

用户可以在正式采集前直接看到：

- 是否只剩挖掘机；
- 灯光是否正常；
- 相机是否被错误隐藏；
- 前齿选择范围是否正确。

这是比仅依赖 Preflight 更直观的验证手段。

## 九、区分“Variant 存在”和“Sensor 使用该 Variant”

这两个概念目前容易混淆：

- Variant 存在：项目定义了一个场景状态；
- Sensor 使用：某个传感器是否需要在这个状态下采集。

建议在 Variant 页面只负责定义场景内容：

```text
Full Scene
Excavator Only
Front Teeth Only
```

在“采集内容”页面决定绑定关系：

```text
Boom Camera
├─ Full Scene          已启用
├─ Excavator Only      已启用
└─ Front Teeth Only    未启用
```

不要用“模态列表为空”暗中表示未启用。UI 应显示一个明确的：

```text
启用此场景变体
```

底层仍然可以把关闭状态映射为空模态列表，不一定立即修改 Schema，但前端概念必须清晰。

## 十、减少 Apply 按钮

当前几乎每个区域都有：

```text
Apply render profile
Apply capture schedule
Apply execution policy
Apply motion
Apply semantic profile
Apply row
Apply override
```

这会产生一个常见问题：用户修改了输入框，却忘记点击 Apply。

建议改为：

- 表单修改后立即更新编辑模型；
- 顶部显示“有未保存修改”；
- 只保留统一的 `保存`；
- 重要操作支持撤销；
- JSON 高级编辑器失去焦点时做校验。

推荐顶部状态：

```text
My Semantic Capture    ● 有未保存修改    [撤销] [保存]
```

`Apply` 只保留在特别危险或需要即时影响 Viewport 的操作，例如：

```text
预览 Variant
应用相机临时覆盖
```

## 十一、实时提示和防错

现在很多错误要等到 `Validate` 或 `Preflight` 才能发现。建议提前反馈。

### 传感器层

- 不兼容的模态直接禁用复选框；
- 相机 Prim 不存在时显示红色；
- 同一个 Prim 被重复添加时警告；
- 自动显示插件和镜头类型；
- Stage 参数读取失败时提示具体字段。

### Variant 层

- 没有选择任何对象时不允许创建；
- RGB 开启但灯光全部被隐藏时显示警告；
- Include path 不存在时立即标红；
- 传感器路径被隐藏时自动保护并说明。

### 采集层

实时显示：

```text
2 个传感器
3 个场景变体
5 个启用组合
100 帧
预计 500 个 Capture Group
预计 2,000 个文件
预计占用 18.4 GiB
```

这些信息可以随勾选即时更新，而不是等到最后才发现输出量过大。

## 十二、保存可复用预设

为了实现“下次只做轻量修改”，建议增加三类预设。

### 输出预设

```text
RGB + 语义
仅语义
RGB + 深度
全部常用输出
```

### Variant 预设

```text
完整场景
只显示当前选择
隐藏环境
只显示指定设备
```

### Render 预设

```text
快速检查
Realtime 正式采集
Path Tracing 低质量
Path Tracing 正式质量
```

用户选择预设后仍可微调。

预设应保存到项目中，也可以另存为全局模板，用于其他项目。

## 十三、建议的新使用流程

以你当前的大臂相机任务为例，理想流程应当是：

### 1. 打开项目

```text
打开项目…
→ 选择 my_capture.swproject
```

系统自动加载项目和 USD。

### 2. 选择传感器

系统自动发现：

```text
☑ Boom Camera
  /Excavator_Fangshan_03/boom_prim/Camera
  OpenCV Pinhole · 1280×720
```

用户只勾选一次。

### 3. 创建 Variant

项目已有：

```text
Full Scene
```

点击：

```text
+ 新建场景变体
→ 只显示选中对象
→ Stage 树勾选 Excavator_Fangshan_03
→ 保留灯光
→ 创建
```

自动得到：

```text
Excavator Only
```

### 4. 配置采集内容

选择 `Boom Camera` 后直接勾选：

| 场景 | 启用 | RGB | Depth | Semantic ID | Semantic Color |
|---|---:|---:|---:|---:|---:|
| Full Scene | ☑ | ☑ | ☐ | ☑ | ☑ |
| Excavator Only | ☑ | ☑ | ☐ | ☑ | ☑ |

### 5. 设置帧数

```text
快速检查
1 帧 · 320×180 · Realtime
```

### 6. 检查并运行

最终摘要：

```text
传感器：Boom Camera
场景：Full Scene、Excavator Only
输出：RGB、Semantic ID、Semantic Color
帧数：1
预计 Capture Group：2
状态：可以运行
```

点击：

```text
Run Headless
```

整个过程几乎不需要输入技术字符串。

## 十四、不建议的改法

以下改法短期简单，但不建议作为最终方向：

- 只给 `Open` 旁边增加文件按钮，其他路径仍手填；
- 在当前 Sensor 面板中直接堆四个固定复选框；
- 继续保留 `Load row/Apply row`，只是把字符串换成勾选框；
- Variant 仍要求用户手填 Include Paths；
- 所有插件都硬编码在 UI 中；
- 把普通配置和 JSON 高级配置继续放在同一层。

这些改动会稍微改善当前体验，但多相机、多 Variant 后仍然会重新变得复杂。

## 十五、推荐实施优先级

### 第一阶段：最高收益

- Project、USD、Output、CSV 文件选择器；
- 最近项目列表；
- Stage 打开后自动发现传感器；
- 传感器可视化选择表；
- “传感器 × Variant × 模态”复选框表格；
- 删除 `Load row/Apply row` 的基本交互；
- 模态预设和批量应用；
- Basic/Advanced 模式分离。

### 第二阶段：Variant 体验

- Stage 树选择器；
- 从当前选择创建 Variant；
- 自动生成 Variant ID；
- 保留灯光/地面等选项；
- Viewport Variant 预览；
- Variant 复制和模板。

### 第三阶段：项目复用与质量保障

- 输出、Variant、Render 预设；
- 最近项目和项目模板；
- 实时文件量、空间、Capture Group 估算；
- 内联校验；
- 最终 Review 页面；
- 更清晰的任务历史和输出浏览入口。

总结来说，核心改进不应只是“把文字输入换成勾选框”，而应形成下面这条用户链路：

```text
可视化打开项目
→ 自动发现 USD 传感器
→ 勾选需要使用的传感器
→ 从 Stage 选择对象生成 Variant
→ 在采集矩阵中勾选场景和输出
→ 选择渲染预设与帧数
→ 查看最终摘要
→ Headless 运行
```

底层仍然保持现有模块化插件、Variant、JobSpec 和 Headless Runtime 架构；变化主要集中在 Studio 的信息组织和交互方式。
