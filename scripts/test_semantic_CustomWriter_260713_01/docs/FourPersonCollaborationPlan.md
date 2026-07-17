# 四人小组协作开发方案

## 1. 文档目标

本文面向“相机语义采集 + 激光雷达 + 机械臂运动 + 多传感器同步 + 数据集写出”项目，规划四人小组的职责分工、接口约定、开发流程、测试验收和集成节奏。

本方案的核心目标不是简单平均分配代码文件，而是通过稳定的公共契约，使四个垂直模块能够并行开发并顺利集成。

## 2. 推荐人员分工

建议按垂直功能模块分工：

| 成员 | 主责模块 | 主要交付 |
|---|---|---|
| A：集成负责人 | 启动、场景、SimulationRunner、统一时钟、调度 | 主循环、生命周期、公共上下文、端到端集成 |
| B：相机负责人 | 相机控制、RenderProduct、语义采集 | RGB、Semantic NPY、自定义 PNG、相机标定 |
| C：LiDAR 负责人 | LiDAR 创建、采样、坐标转换 | 点云、强度、语义 ID、LiDAR 位姿 |
| D：机械臂负责人 | Articulation、轨迹、状态机 | 关节控制、末端位姿、运动状态、任务流程 |

数据记录层由 A 主责公共接口，B、C、D 分别负责自己数据类型的 Writer 和验证逻辑。

每个核心模块还应指定一名非主责成员作为评审人，避免关键知识只掌握在一个人手中。

建议评审关系：

| 主责模块 | 主责人 | 建议评审人 |
|---|---|---|
| Runtime / SimulationRunner | A | D |
| Camera / Semantic | B | A |
| LiDAR | C | B |
| Robot / Task | D | A |
| DatasetRecorder | A | B、C、D 按数据类型共同评审 |

## 3. 开发前必须对齐的项目范围

### 3.1 第一版 MVP

建议第一版只包含：

```text
单相机
单 LiDAR
单机械臂
固定 USD 场景
预设关节轨迹
离线数据采集
Headless 运行
统一时间戳和数据目录
```

### 3.2 第一版暂不实现

建议明确排除：

- 多相机和多 LiDAR；
- 动态增删传感器；
- ROS 2 实时通信；
- 在线运动规划；
- 碰撞后的自动重规划；
- 完整 GUI 参数编辑器；
- 实时数据流服务；
- 多机器人协作；
- 闭环抓取策略。

如果第一版范围不冻结，四名成员很容易按不同目标设计，导致接口无法合并。

## 4. 统一运行环境

开发前必须记录并固定：

```text
Isaac Sim 版本
操作系统版本
NVIDIA 驱动版本
GPU 型号
Python 启动方式
项目根目录
USD 文件路径
Renderer
Headless 设置
Physics Hz
Render Hz
```

当前项目至少应明确：

```text
Isaac Sim：6.0.1
标准启动入口：/root/isaacsim/python.sh
项目目录：/root/gpufree-data/wyb/test_semantic_CustomWriter_260713_01
场景 USD：/root/gpufree-data/wyb/Semantic_260709_01.usd
```

所有成员应使用同一条标准启动命令和同一套环境配置。禁止每个人在业务代码中维护不同的绝对路径。

## 5. USD 场景基线管理

团队需要确定唯一的场景源文件和版本：

```text
USD 文件名
USD 文件校验和
默认 Camera prim path
LiDAR prim path
Robot prim path
End Effector prim path
传感器挂载 link
```

建议建立场景清单：

| 项目 | 示例内容 |
|---|---|
| Scene USD | `/root/gpufree-data/wyb/Semantic_260709_01.usd` |
| Camera | `/Camera` |
| LiDAR | 待团队冻结 |
| Robot | 待团队冻结 |
| End Effector | 待机械臂负责人确认 |
| Semantic schema | `semantic_mapping.json` |

USD 或 USDA 不适合多人同时编辑。建议指定一名场景资产维护者，其他成员通过变更申请修改。

任何 prim path 修改都必须同步更新：

- 场景配置；
- 接口文档；
- Smoke test；
- 相关模块负责人。

## 6. 必须提前冻结的技术契约

### 6.1 仿真步进所有权

团队必须统一确认：

> 只有 `SimulationRunner` 可以推进仿真时间。

Camera、LiDAR、Arm Controller 和 Writer 都不能各自调用仿真步进 API。

否则可能产生：

- 物理时间重复推进；
- 相机与 LiDAR 错帧；
- 机械臂状态与图像不对应；
- 一次业务循环中仿真前进两次；
- 不同传感器时间戳不可比较；
- Replicator 步进和 Physics 步进互相覆盖。

建议冻结统一单步顺序：

```text
更新任务状态
  -> 计算机械臂命令
  -> 应用控制命令
  -> 推进一个物理步
  -> 更新场景状态
  -> 判断传感器采样
  -> 采集 Camera / LiDAR
  -> 读取机器人状态
  -> 写入统一记录
```

### 6.2 时间和编号定义

团队需要统一以下字段的定义：

| 字段 | 定义 |
|---|---|
| `episode_id` | 一次完整运行编号 |
| `physics_step` | 全局物理步编号 |
| `simulation_time` | 当前仿真时间 |
| `frame_id` | 一次联合记录编号 |
| `sample_id` | 某个传感器自己的采样编号 |
| `sensor_timestamp` | 传感器数据对应的仿真时刻 |

禁止每个模块各自定义全局 `frame_id`。

例如：

```text
physics_step = 120
simulation_time = 1.0
camera_sample_id = 30
lidar_sample_id = 10
robot_state_id = 120
```

这些数据可以对应同一个仿真时刻，但编号含义不同。

### 6.3 坐标系和单位

必须形成书面约定：

```text
长度：米
角度：内部统一使用弧度
时间：秒
关节速度：rad/s
四元数顺序：明确 xyzw 或 wxyz
矩阵约定：明确行向量或列向量
点云默认坐标系：LiDAR local frame
相机外参方向：明确 sensor-to-world 或 world-to-sensor
```

同时记录 USD 的：

```text
upAxis
metersPerUnit
机器人基座坐标系
相机光学坐标系
LiDAR 坐标系
末端执行器坐标系
```

坐标约定发生变化时，必须作为公共接口变更处理，不能只在单个模块中静默修改。

### 6.4 公共数据对象

Camera、LiDAR 和 Robot State 应使用统一数据包外壳：

```text
episode_id
physics_step
simulation_time
sample_id
source_name
prim_path
world_pose
payload
calibration_version
```

各模块只定义自己的 `payload`：

```text
Camera payload：RGB、semantic ID、resolution
LiDAR payload：points、intensity、semantic ID
Robot payload：joint positions、velocities、end-effector pose
```

这样 `DatasetRecorder` 不需要了解每个传感器的内部实现。

### 6.5 模块生命周期接口

所有设备模块建议遵循统一生命周期：

```text
initialize
reset
update
should_capture
capture 或 read_state
shutdown
```

需要提前约定：

- 初始化失败如何报告；
- `update` 是否允许修改场景；
- `capture` 是否允许阻塞；
- 资源由谁 detach 和 destroy；
- shutdown 是否允许重复调用；
- 异步写盘由谁等待完成。

## 7. 配置文件协作规则

开发前应决定统一使用 JSON 或 YAML，并确定：

- 字段命名方式；
- 配置版本号；
- 必填字段；
- 默认值维护者；
- 不允许硬编码的参数；
- 配置校验失败时的处理方式；
- 配置向后兼容策略。

建议所有设备配置包含：

```text
config_version
enabled
prim_path
update_hz 或 capture_hz
```

建议配置文件职责：

| 配置文件 | 主责人 | 内容 |
|---|---|---|
| `simulation.json` | A | Physics Hz、Render Hz、时长、随机种子 |
| `scene.json` | A | USD、prim path、场景基线 |
| `camera.json` | B | 分辨率、采样率、相机控制参数 |
| `lidar.json` | C | 型号、扫描率、点云字段 |
| `robot.json` | D | Articulation、关节和控制参数 |
| `task.json` | D | 状态机、轨迹和采集阶段 |
| `recording.json` | A | 输出路径、格式、覆盖策略 |
| `semantic_mapping.json` | B | Dataset ID 与颜色映射 |

任何配置结构修改都需要同步通知读取该配置的模块负责人。

## 8. 输出数据契约

开发前应冻结目录结构：

```text
output/
├── run_manifest.json
├── semantic_mapping.json
├── calibration/
├── camera/
│   ├── rgb/
│   ├── semantic_id/
│   ├── semantic_color/
│   └── metadata/
├── lidar/
│   ├── points/
│   ├── intensity/
│   ├── semantic_id/
│   └── metadata/
├── robot/
│   ├── joint_state/
│   ├── commands/
│   └── end_effector_pose/
└── timeline/
    └── samples.jsonl
```

同时对齐：

- NPY 的 dtype 和 shape；
- PNG 的颜色通道顺序；
- 点云字段顺序；
- JSON 浮点精度；
- 文件编号位数；
- 文件命名规则；
- 是否允许覆盖旧输出；
- 不完整 episode 如何标识。

当前语义规则应继续固定为：

```text
多标签取最后一个非空标签
Dataset ID 使用 uint16
BACKGROUND ID 为 0
PNG 必须由 NPY 和 mapping 派生
未知标签按 strict mapping 策略处理
```

## 9. Git 协作规则

建议建立以下基本规则：

- `main` 始终保持可运行；
- 每人使用独立 feature branch；
- 共享接口修改必须单独提交；
- PR 必须由接口相关成员评审；
- 禁止直接覆盖其他成员模块；
- 禁止提交采集生成的 PNG、NPY 和运行日志；
- 大型 USD 使用外部资产目录或 Git LFS；
- `semantic_mapping.json` 和输入配置应纳入版本管理；
- 每个 PR 必须说明运行命令、输出变化和验证结果；
- 禁止在没有说明的情况下修改公共数据结构。

建议代码所有权：

```text
runtime/*         -> A 主审
scene/*           -> A 主审
sensors/camera/*  -> B 主审
sensors/lidar/*   -> C 主审
robots/*          -> D 主审
tasks/*           -> D 主审
recording/*       -> A 与对应数据负责人共同评审
validation/*      -> 对应模块负责人主审，集成负责人复审
```

建议分支命名：

```text
feature/runtime-runner
feature/camera-pipeline
feature/lidar-pipeline
feature/robot-controller
feature/dataset-recorder
fix/timeline-sync
```

## 10. Pull Request 要求

每个 PR 至少说明：

```text
改动目标
影响模块
是否修改公共接口
配置是否变化
数据格式是否变化
运行命令
测试结果
已知限制
回滚方式
```

涉及以下内容的 PR 必须由至少两人评审：

- SimulationRunner；
- 仿真时钟；
- 坐标系；
- 公共数据包；
- 输出目录；
- 配置 Schema；
- USD prim path；
- Semantic mapping 规则。

## 11. 模块测试与验收

### 11.1 相机模块

完成标准：

- RGB 非空且分辨率正确；
- Semantic NPY 为预期 dtype；
- PNG 和 `mapping(NPY)` 逐像素一致；
- 多标签最终标签解析正确；
- 未知标签策略正确；
- 相机位姿和标定元数据正确；
- Writer 能正确 detach 和 flush。

### 11.2 LiDAR 模块

完成标准：

- 点云数量和 shape 合理；
- 不包含异常 NaN 或 Inf；
- 点云字段含义明确；
- 坐标转换可以用简单场景验证；
- 静态场景连续帧结果稳定；
- LiDAR 位姿与安装 link 一致；
- 采样频率符合配置。

### 11.3 机械臂模块

完成标准：

- 能完成 Home 轨迹；
- 不超过关节限位；
- 命令值和实际反馈分别记录；
- 轨迹完成、超时和失败状态明确；
- 末端执行器位姿可以验证；
- 控制器不会自行推进仿真；
- reset 后状态可重复。

### 11.4 集成模块

完成标准：

- 只有一个模块推进仿真；
- Camera、LiDAR、Robot State 可以按仿真时间关联；
- 连续运行不会漏写或重复编号；
- 运行结束能够 flush 所有写盘任务；
- 异常退出仍能释放 Writer、Annotator 和 RenderProduct；
- 相同随机种子和配置能够复现实验；
- 输出 manifest 能描述完整运行环境。

## 12. Definition of Done

每个成员的任务只有同时满足以下条件才算完成：

```text
代码实现完成
公共接口没有未记录变更
配置示例已更新
模块级测试通过
Smoke test 通过
输出格式经过验证
文档已更新
PR 已完成评审
已知限制已记录
```

“能够启动”或“本机运行过一次”不能作为完成标准。

## 13. 推荐协作里程碑

### 13.1 里程碑 0：接口冻结

四人共同完成：

```text
配置 Schema
模块接口
仿真时间定义
坐标系约定
公共数据包
输出目录
MVP 验收标准
```

这一阶段不建议同时开始大规模实现。

### 13.2 里程碑 1：公共骨架

A 完成空的 Runner、Scheduler 和 Recorder。

B、C、D 使用模拟数据接入公共接口，验证并行模块可以被统一调度。

### 13.3 里程碑 2：模块并行开发

```text
B：接入真实 Camera 和 Semantic Pipeline
C：接入真实 LiDAR
D：接入真实机械臂和预设轨迹
A：维护集成场景、Runner 和公共接口
```

### 13.4 里程碑 3：静态集成

机械臂暂不移动，先验证：

- Camera 正常采集；
- LiDAR 正常采集；
- Robot State 正常记录；
- 三类数据具有统一时间关系；
- 输出目录和 manifest 正确。

### 13.5 里程碑 4：动态集成

加入机械臂运动，验证：

- 控制命令和状态反馈；
- Camera 与 LiDAR 采样时刻；
- 机械臂运动状态下的语义数据；
- 多频率调度；
- 传感器动态位姿。

### 13.6 里程碑 5：稳定性验证

进行：

- 多帧测试；
- 长时间测试；
- 重复运行测试；
- 异常退出测试；
- 输出覆盖保护测试；
- 未知标签测试；
- 轨迹超时测试；
- 传感器数据缺失测试。

## 14. 推荐沟通机制

建议每次短会只同步以下内容：

```text
昨天完成了什么
今天准备交付什么
是否修改公共接口
当前阻塞是什么
需要谁评审或配合
```

公共接口变更不能只通过口头通知，应写入文档或 ADR。

建议记录简短 Architecture Decision Record：

```text
决策背景
可选方案
最终选择
选择原因
影响模块
迁移要求
```

以下变化建议必须写 ADR：

- 主仿真步进 API 变更；
- Camera 或 LiDAR 采样模型变更；
- 坐标系变更；
- 数据格式变更；
- Semantic ID 规则变更；
- USD 资产组织方式变更。

## 15. 常见协作风险

需要重点避免：

- 多个成员分别实现自己的仿真主循环；
- 各模块使用不同时间单位；
- Camera 和 LiDAR 对 `frame_id` 的定义不同；
- 每个模块建立自己的输出目录规则；
- LiDAR 点云坐标系没有明确记录；
- 机械臂只保存命令值，没有保存实际反馈；
- 每个人复制一份配置并逐渐产生差异；
- USD prim path 修改后没有通知其他成员；
- Writer 同时承担控制、采集和保存；
- 临时修改公共接口但没有更新文档；
- 开发后期才进行第一次端到端合并；
- 把大型运行输出提交到 Git；
- 单人长期独占关键模块，没有备用维护者。

## 16. 建议配套文档

在正式并行实现前，建议共同维护：

```text
Architecture.md
DataContract.md
DevelopmentGuide.md
```

分别负责：

| 文档 | 内容 |
|---|---|
| `Architecture.md` | 模块职责、依赖关系、生命周期和主循环 |
| `DataContract.md` | 时间、坐标系、数据格式、dtype 和目录结构 |
| `DevelopmentGuide.md` | 环境、命令、Git、PR 和测试规则 |

此外可以继续保留本项目现有的：

- Custom Writer 实现方案；
- 多传感器与机械臂项目架构方案；
- Semantic mapping 和输出验证说明。

## 17. 最终原则

四人协作的关键不是尽量减少沟通，而是尽早固定必须共享的部分：

```text
统一场景
统一时间
统一坐标系
统一数据契约
统一配置入口
统一输出目录
统一验收标准
```

在这些内容冻结后，四名成员才能分别实现 Runtime、Camera、LiDAR 和 Robot 模块，并以较低成本完成集成。
