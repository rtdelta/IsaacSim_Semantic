# 挖掘机资产接口规范 v1.0

制定日期：2026-09-20。性质：本项目的新资产制作规范建议稿，不是 NVIDIA 或 ROS 的官方资产标准。现有资产不因本文自动改名、移动原点或改变角度。只有完成验收的具体资产版本，才能声明兼容。

配套文件：`asset_manifest.template.json` 为可复制的机器可读清单；`sensor_mount.template.json` 为单个安装槽记录模板，可填好后加入清单的 sensor_mounts 数组；`ACCEPTANCE.md` 为验收条目；`AGENT_HANDOFF.md` 为交付给制作人员或 agent 的任务模板。本轮提供规范和模板，没有实现自动 USD 校验器，也没有修改现有运行脚本去读取新清单。

## 1. 规范用语与适用范围

- **必须**：违反即不能声明对应 profile 合格；**建议**：偏离时说明理由；**可选**：声明有该能力才验收。
- 基础 profile：`five_body_four_joint_v1`，五个刚体、四个单自由度转动关节，适用于当前主要挖掘机采集链路。
- 运行 profile：`prescribed_motion` 为按角度/角速度规划、通过 Articulation 写状态；`dynamic_drive` 为力/力矩驱动且考虑动力学。二者必须分开声明和验证。
- 油缸独立伸缩、闭环连杆、履带滚动/履带节、多机器人协调属于扩展 profile；不能增加后仍声称当前四关节脚本直接兼容。
- 每个参数必须有单位、所属坐标系、数据来源和状态。未知填 `null` 并列入 unresolved；不能用 0、单位四元数、±180°或连续关节掩盖未知值。
- 清单中的 `null` 是待填写，不是可运行默认值。`release` 状态必须满足所有适用验收条目；未测能力写 `not_tested`，不写 `supported`。
- JSON 形状约定：translation_m 为 3 个有限数；quaternion_xyzw 为 4 个有限数且范数为 1；operating_limits_rad 为 [lower,upper]；刚体与关节键大小写固定。数值禁止 NaN/Infinity；数据来源字符串需指向文档版本、文件或测量记录。
- authoring_status 使用 draft/release/deprecated；dependency_mode 使用 self_contained/shared_tree；不适用的可选能力可为 null 或空数组，但必须在声明/验收中明确 not_applicable。缺失必需资料必须保持 draft。

## 2. 三种树必须区分

| 类型 | 决定什么 | 权威数据 |
| --- | --- | --- |
| USD Prim 层级 | 命名空间、变换继承、资产组合 | Prim 路径、xformOpOrder、Reference/Payload |
| 机构连接树 | 刚体之间如何绕关节运动 | physics:body0/body1、关节帧、axis、限位 |
| ROS TF 树 | 对外提供哪些坐标变换 | 明确选定的 frame、父子关系、采样时刻 |

不能根据 USD 节点缩进推断关节连接，也不能把 Joint Prim 自身的世界坐标当作销轴坐标。销轴由关节对两侧刚体的局部帧决定。[OpenUSD Physics](https://openusd.org/dev/api/usd_physics_page_front.html)

## 3. 文件交付与资产边界

```text
Excavator_<model_id>_v<major>.<minor>.<patch>/
├── Excavator.usda                  主入口，defaultPrim="Excavator"
├── asset_manifest.json             身份、坐标、接口、能力、兼容声明
├── geometry/                       Mesh、3DGS、纹理等真实依赖
├── materials/                      材质依赖（如有）
├── profiles/                       消费程序的配置/适配层（如有）
├── preview/preview.usda             地面、灯光、相机、PhysicsScene 等
├── validation/report.json           数值、截图/数据路径、运行版本
├── dependencies.sha256              依赖锁定与完整性清单
├── README.md                        打开、控制、限制、版本变更
└── CHANGELOG.md
```

1. 主资产不包含世界地面、PhysicsScene、灯光、观察相机、全局时钟、ROS 域、录制器、永久 Render Product、会自行运行的 OmniGraph 或时间线启动动作。
2. 主资产可通过 USD Reference/Payload 加载；在声明的 Isaac/扩展环境中，不依赖作者启动脚本来修正几何或关节才可用。运行控制脚本可以另附。
3. 包内文件引用必须用相对路径，大小写正确；共享资产依赖须列出相对解析位置、版本和 SHA-256。标明 `self_contained` 或 `shared_tree`，不能将后者称为单文件可移植。
4. 文件引用路径与 Prim 目标路径不同：`/Excavator/track_prim` 这样的资产内部 Prim 绝对路径是允许的，应通过组合正确映射；不能写死 `/World/某台挖掘机/...`。
5. 所有依赖必须可解析；不依赖某个人的绝对磁盘路径、隐式软链接、缓存或浮动网络 URL。
6. debug 坐标轴、URDF 对比模型、销轴球等放独立可关闭分支，默认不参与正式 RGB/语义/RTX 扫描。不能让对比几何成为第二套扫描车体。

## 4. USD 命名及标准结构

为兼容当前自动识别，五个刚体直接作为模型根的兄弟节点；本规范选择这一结构，并不表示 USD 只支持这种结构。

```text
/Excavator                          Xform，kind=component，资产级原点
├── track_prim                      底盘刚体 + 唯一 ArticulationRootAPI
│   ├── Visuals/{GS,Mesh}
│   ├── Collisions                  可选
│   └── Sensors                     可选安装槽
├── cab_prim                        上车/驾驶室刚体
│   ├── Visuals/{GS,Mesh}
│   ├── Collisions
│   └── Sensors/<mount_id>/sensor    例如 lidar_rear_left/sensor
├── boom_prim                       大臂刚体
├── arm_prim                        小臂刚体
├── bucket_prim                     铲斗刚体，斗齿随铲斗
├── Joints
│   ├── swing                       track → cab
│   ├── boom                        cab → boom
│   ├── arm                         boom → arm
│   └── bucket                      arm → bucket
├── Looks
└── Debug                           可选，默认 inactive
```

- ASCII 名称，大小写敏感；角色名固定为 `track/cab/boom/arm/bucket` 和 `swing/boom/arm/bucket`，中文只用于显示说明。
- 清单内 Prim 路径相对 `/Excavator`；`.` 表示模型根，不携带实例场景前缀。
- `displayName` 不参与程序绑定。关节与刚体的身份由路径/角色和关系决定，不按 Stage 显示顺序绑定。
- 不额外在五个刚体外套一个 `Links` 层而仍声称旧发现器无修改兼容：当前发现器用连接刚体的公共祖先确定模型根。
- 主入口保持一个模型根、一个 articulation、五个非嵌套刚体。可渲染零件不再挂独立 RigidBodyAPI；装饰油缸不伪装成额外 DOF。
- 新资产的默认 `visualization` 选项必须是实际采集外观，例如 `3dgs` 或 `mesh`，不能默认进入透明叠加对比模式。选项不存在时写清单，不要求强造空 Mesh。

## 5. 单位、变换及原点

### 5.1 全局约定

| 项目 | 规范 |
| --- | --- |
| 长度、质量、时间 | m、kg、s；metersPerUnit=1、kilogramsPerUnit=1 |
| Stage 上方向 | upAxis="Z"，右手系 |
| 车体基准方向 | +X 为履带定义的前进方向，+Y 左，+Z 上；必须附基准姿态示意 |
| 清单中的角度、角速度 | rad、rad/s；字段名明确带单位 |
| USD RevoluteJoint 限位及 angular drive 角度属性 | degree；导入/导出边界显式转换 |
| 清单/ROS 四元数 | [x,y,z,w]，单位化 |
| Gf/USDA quat、当前实验 Articulation 位姿接口 | 按接口使用 wxyz；必须通过具名适配转换，不能直接传 ROS 数组 |
| 规范矩阵 | 列向量；`T_A_from_B` 将 B 坐标表示转换为 A 坐标表示 |

车体坐标约定参考 [ROS REP-103](https://raw.githubusercontent.com/ros-infrastructure/rep/master/rep-0103.rst)。传感器及关节帧可以有不同朝向，必须显式定义，不强迫各帧 +Z 都朝上。USD 限位角度单位见 [UsdPhysicsRevoluteJoint](https://openusd.org/dev/api/class_usd_physics_revolute_joint.html)。

`p_A = R_A_from_B * p_B + t_A_from_B`；`T_A_from_C = T_A_from_B * T_B_from_C`。
Gf 的矩阵按行向量使用，与上述矩阵往返须转置并验证；不能只转置旋转部分而漏掉平移。

正式姿态保存平移 + 四元数，GUI 中的 Euler 仅作输入显示。如果使用 roll/pitch/yaw，本规范定义列向量 `R=Rz(yaw) Ry(pitch) Rx(roll)`；不得只写“Isaac 默认旋转顺序”而省略 xformOpOrder/转换规则。

### 5.2 原点

- 新建标准 profile 建议采用 `ground_projected_swing_axis_v1`：基准姿态下，回转轴中心线与**明确定义的名义履带支承平面**相交的位置。支承平面是资产基准，不是运行中实时接地点、Mesh AABB 最低点或高斯中心最低点。
- 若采用扫描原始原点等其他基准，必须给出唯一 `origin_policy`、基准点定义、对应源坐标系以及数值变换，并作为声明过的 profile 偏离项；不能只写“模型中心”或“原点不变”。
- 模型根和 `track_prim` 在资产初始帧重合；模型根 T=0、Q=identity、Scale=1，整机摆放写到 combine 场景的实例根。
- 初始重合不意味着运行中模型容器会自动随 PhysX 底盘移动。实时 base 位姿必须从实际底盘状态及声明的参考偏移计算，不能一直读静止容器的初始 xform。
- `origin_revision` 必填；变更原点、轴向或角度零位属于接口破坏，必须换版本并提供 `T_new_from_old`，同时修正几何、关节局部帧、质心和外参。
- 不根据名字把 `cab_prim`、回转销轴、模型根和重心当成同一个点。

### 5.3 缩放

- 模型根、刚体、关节链祖先和传感器安装链必须保持单位缩放，不能有负缩放、剪切或非均匀缩放。
- 原始 Mesh/3DGS 单位换算及均匀几何倍率在独立注册变换或离线烘焙中完成；明确写 source_scale、源单位和应用位置，只应用一次。
- 关节锚点、安装外参、碰撞、质心和惯量必须对应最终米制尺寸，不能把几何放大后仍保留原 URDF 的臂长和锚点。
- 不把某个旧模型的 2.4 倍推广到新挖掘机。3DGS 变换必须同时影响中心和椭球尺度/朝向；不能只缩放高斯中心。

## 6. 关节契约

| 关节角色/名称 | body0 | body1 | 含义 |
| --- | --- | --- | --- |
| swing | track_prim | cab_prim | 回转 |
| boom | cab_prim | boom_prim | 大臂 |
| arm | boom_prim | arm_prim | 小臂 |
| bucket | arm_prim | bucket_prim | 铲斗 |

每个关节必须显式提供：类型、两侧刚体、localPos0/localRot0、localPos1/localRot1、axis、jointEnabled、是否参与 articulation、q=0 定义、正方向证据、限位类型及来源。

新标准关节的局部转轴统一编码为 +Z，物理轴方向通过两侧 joint frame 定义；如果保留第三方 X/Y 轴编码，列为 profile 偏离并完整记录。`physics:axis="Z"` 不表示世界 Z 轴。两侧关节帧在各自刚体内的语义见 [UsdPhysicsJoint](https://openusd.org/dev/api/class_usd_physics_joint.html)。

在列向量、body0 为父、body1 为子的约定下，制作时用下式表达并通过实际 +δ 测试核对符号：

```text
T_parent_from_child(q)
  = T_parent_from_joint0 * R_axis(q) * inverse(T_child_from_joint1)
```

- q=0 表示两关节帧的参考角度关系，不等于“截图里的姿态”“铲斗水平”或“文件刚打开时姿态”。
- 正方向使用右手规则；每关节必须保存一组 q 与 q+δ 的关节轴/子刚体位姿数值，不能仅写“顺时针”或“抬臂为正”。δ 建议 5°，但必须处于允许范围。
- 三类数据分开：`zero_definition`（零位定义）、`home_q_rad`（启动姿态）、`physical_limits`（结构限位）；应用任务的 `operating_limits_rad` 是第四项。
- `physical_limits.kind` 为 `bounded`、`continuous` 或 `unknown`。`continuous` 是确认可连续转动，不是未知限位；unknown 只允许草稿/明确未标定能力。
- 用于位置采集的工作限位必须有限、lower < upper、包含 home，且在已知物理限位内；软件范围不能声称是实机机械限位。
- 全部 body0/body1 必须各指向唯一刚体，形成严格四关节串联链，无分叉、环、悬空关系及隐式额外 DOF。
- 发布时，USD 中五刚体的初始变换、关节帧、home 数值和启用的驱动目标必须一致。禁止只填写 drive target 而未验证实际初始化角度。

## 7. 物理与控制边界

- 五个 link 必须有正确的 RigidBodyAPI。ArticulationRootAPI 在 `track_prim` 上唯一施加；把同名父 Xform 误当 root 不合格。
- `prescribed_motion` 使用非 kinematic 的 articulation 刚体，通过 Articulation 状态接口驱动；不要因为“按角度运动”就擅自把所有刚体设为 kinematicEnabled=true。
- 标准 prescribed 资产不带活动 angular drives；附带动力学配置时放独立 profile/layer。运动期间只能有一个权威写入者，不能同时由 drive、直接 DOF 写入及 USD xform 动画抢写。
- 基础资产不固定到 world。固定底盘的约束由预览或 combine 场景添加。需要“固定关节本身作为 articulation root”的旧消费者，应提供独立适配层，且组合后保持一个 articulation root。
- 质量、质心、惯量、碰撞和摩擦需声明 `placeholder/estimated/calibrated`。占位值可用于明确标注的 prescribed 采集，不构成动力学可靠性声明。
- 动力学 profile 额外要求正质量、物理可实现的正定惯量及主惯量三角关系、正确惯量参考系、碰撞与驱动测试；禁止将统一 mass=1/inertia=(1,1,1) 标为已标定。
- 刚体运动后视觉、碰撞、安装槽必须一致跟随；不得仅移动 GS 外观让真实 articulation 状态留在原处。

## 8. 外观、3DGS、碰撞和语义

- `Visuals/GS`、`Visuals/Mesh`、`Collisions` 分工明确。碰撞体不自动等于 RTX 的可扫描几何；关闭碰撞也不等于消除雷达遮挡。
- Mesh 和 GS 必须在同一 link 内配准，记录注册变换、有效尺寸和允许误差。除明确的 debug overlay 外，同一表面不重复放两套同时参与射线的几何。
- 同一刚体允许多个视觉子件；铲斗和斗齿必须以明确的刚性关系跟随，漏齿/漂浮件属于失败。油缸只做刚性外观时注明不表达真实伸缩或闭环。
- 可选语义使用稳定类别标识，例如 excavator、track、cab、boom、arm、bucket、tooth，并给出类别表、标注 Prim 和继承规则；渲染产出的数值 ID 由每次映射保存，不能视为永久类别 ID。
- 渲染配置如 Motion BVH、Multi-tick、per-sensor TLAS 属于运行兼容配置，记录准确版本和验证状态。不得把本次 3DGS 兼容性回退升级为所有资产永久禁用 BVH 的规则。

## 9. 安装槽、传感器和外参

- 安装槽必须处于实际承载刚体之下，例如 `cab_prim/Sensors/lidar_rear_left`；父槽 + sensor 子节点保持简单、可编辑，避免挂在不动的模型容器下。
- `mount_id` 表示位置/用途，`model_id` 表示型号，`sensor_instance_id` 表示具体实例。未来换型号可保留 mount_id；旧 `MyOS0_backleft/MyAiry_backleft` 名称不自动迁移。
- manifest 每个槽明确 `parent_body_role`、`mount_prim`、`sensor_prim`、`T_parent_from_mount`、`T_mount_from_sensor`、型号路径和哈希。
- 默认新雷达槽的发射节点与槽重合：`T_mount_from_sensor=I`。非零外参必须显式记录并验收，不靠看起来重合判断。
- 传感器几何外壳、安装原点、发射原点和逐射线偏移是不同概念。`rangeOffsetM` 不等于改变 USD 安装点，也不能用来跳过车壳代替精确排除外壳。
- 传感器 frame 原样表达数据输出坐标；模型的 FOV、发射方向/角度表、射线偏移、量程、回波、频率、强度/功率归一化另有版本化配置。MyAiry 的局部 +Z 半球只属于 MyAiry。
- 排除自身 Mesh 应限制到具体 housing 几何并验证其他车体仍能遮挡；语义后处理删除返回点不等于让射线穿透该几何重新扫描。

## 10. TF 与时间契约

- 资产可以不带 ROS 节点或现成 /tf，但必须足以确定运动学与传感器坐标关系。
- 发布器 profile 明确每条 TF 的 parent、child、跟随对象、原点、轴向及时间戳。每个 child 只有一个 parent。
- `base` 跟随底盘；`cab` 跟随驾驶室含回转。水平投影参考系必须声明与哪个原始 frame 同原点、航向如何提取、奇异时如何处理。
- 各关节完整 TF 链和“根参考系直接连全部雷达”的简化 TF 都可用，但必须标注选择。简化树里挂在大臂/驾驶室上的雷达边会随关节变化，不能错误发布为固定外参。
- 多实例发布须有 frame/topic 命名空间；资产的双 Payload 重定位通过，不等于当前 LidarVisualizer 支持同一进程自动控制多台机器人。
- `/clock`、点云 header、TF、关节和根姿态使用同一仿真时间域；wall time 只作运行耗时。记录 reset/segment 边界，不混用重置前后的时间。
- 清单须说明采样时刻代表瞬时测量、扫描起点或终点；不能把多 tick 扫描伪称单一位姿瞬时采样。

## 11. combine 场景与运行覆盖

资产层负责结构与标定；combine 层负责实例摆放、环境、安装传感器及显式任务起始姿态；Session 层负责临时调试/控制；输出清单记录实际生效值及来源。

Session 的临时外参不自动随普通 USD 保存持久化。生产采集需要快照 source/combine/session 有效参数和哈希。改变源资产后须重新加载并检查最终组合值；不能假设同名文件改了就一定覆盖了强层意见。

换雷达/重命名时，必须同步更新 relationship、graph target、Render Product 及对外身份映射；不允许同时运行保存于场景的旧雷达图和新运行脚本而重复采样。

## 12. 当前资产和程序的兼容说明

以下来自本地已保存源码及 2026-09-19 实测报告，不代表今天远端可能新增文件的完整审计。

| 对象 | 已知约定 | 对本规范的处理 |
| --- | --- | --- |
| Fangshan_05_origin03 | 五兄弟刚体，track_prim 上 articulation root，四关节名 swing/boom/arm/bucket | 可复用结构，不直接认证整个 v1 |
| origin03 原点 | 原 03 track 来源原点；不是实测接地/重心 | 作为 legacy 原点 profile；不能悄悄移到新推荐基准 |
| Fangshan 几何 | 2.4 倍来源扫描，URDF 轴/零位但臂长已不同 | 倍率仅本型号；禁止直接套原 URDF 平移参数 |
| 05 主资产/场景 | 主资产零位、对比 visualization、场景折臂 home 可不同；物理为占位值 | 发布新资产要分清默认 variant、home 与标定状态 |
| 当前 LidarVisualizer | 识别四关节串联；标准名或已有 legacy 名；单位米；按原生 DOF 读写 | 新规范选用标准名；manifest 尚未被它读取 |
| 当前 ROS swing_coordinate | 跟随 track/base，名称虽含 swing 但不跟随 cab 独立回转 | 保留为 legacy 显式定义；不能据名推断 cab frame |
| 当前 Joint Position Recorder 本地版本 | 默认固定基座、有限限位、无 angular drive，profile 有候选路径/名称 | 与移动底盘/continuous/带 drive 资产不自动兼容；须适配配置或组合层并实测 |
| Semantic World Module v04 本地版本 | 独立采集运行时和插件，motion 有自己的接口/配置 | 可共享资产，不能从“可打开”推断运动、传感器或时间契约已兼容 |

兼容表按精确代码/应用版本、场景/适配层和测试报告记录 `passed/failed/not_tested`。不能只写“支持 Isaac Sim”。现有规范化方案不自动迁移旧 MCAP 的原点、角度、TF 和话题。

## 13. 版本与发布规则

- `asset_id` 标识型号，`asset_version` 使用 major.minor.patch；`origin_revision`、`joint_convention_revision`、`sensor_mount_revision` 分别记录几何接口变更。
- 改原点/坐标轴/关节零位或符号、原生角度映射、公开路径或 TF 含义：major 升级并提供迁移关系。
- 增加不破坏接口的可选外观/安装槽：minor；纯文档或不影响几何行为的修复：patch。影响输出的参数变化必须更新依赖哈希和变更说明。
- 发布包必须有可重跑的构建/导出来源、精确依赖清单、验收证据及已知限制。人工修改和生成清单不一致时，不选一边猜测，先同步再验收。
- 三维模型可信度、运动学可信度、动力学可信度、RTX 可扫描性、ROS 链路兼容分别声明，不合并成含糊的“模型完整”。

## 14. 清单中可重复记录的格式

以下为字段形状说明，示例中的占位值不能原样发布。共享文件路径相对资产包根解析；所有外置记录文件也必须进入 dependencies。

`geometry.registration_records` 的每项至少包括：

```json
{
  "body_role": "boom",
  "representation": "mesh",
  "visual_prim": "boom_prim/Visuals/Mesh",
  "source_asset": "geometry/source_boom.usdc",
  "source_length_unit": "m",
  "source_unit_to_m": 1,
  "model_uniform_scale": 1,
  "T_body_from_scaled_source": {"translation_m": null, "quaternion_xyzw": null},
  "transform_application": "usd_registration_xform",
  "evidence_file": null
}
```

唯一规定的应用公式：`p_body = R * (source_unit_to_m * model_uniform_scale * p_raw) + t`。translation_m 已是最终米制，不再乘尺度；若源文件已烘焙，应将上述 scale 设为烘焙后适用的值并记录历史，不能再次乘旧倍率。representation 为 mesh/3dgs；每个实际存在的视觉表示都要有记录。transform_application 为 usd_registration_xform/baked，必须和真实 USD 意见一致。

`dependencies` 的每项：

```json
{"path":"geometry/source_boom.usdc","version":null,"sha256":null,"purpose":"source_geometry"}
```

发布时 sha256 为真实文件的 64 位十六进制摘要，文件版本未知可用内容摘要锁定，不能捏造版本；入口/主清单的发布哈希写外部 dependencies.sha256 或发布报告，避免 manifest 自哈希循环。shared_tree 允许显式的 ../ 依赖，但迁移时必须保留被声明的依赖树。

`ros_publication.frame_definitions_file` 指向的 JSON 示例形状：

```json
{
  "version":"declared_frame_contract_v1",
  "instance_namespace":"excavator_01",
  "edges":[
    {
      "parent":"world",
      "child":"excavator_01/base",
      "kind":"body_pose",
      "follows_body_role":"track",
      "T_body_from_frame":{"translation_m":[0,0,0],"quaternion_xyzw":[0,0,0,1]},
      "publication":"dynamic",
      "timestamp_source":"simulation_state_sample"
    }
  ]
}
```

每条真实边都必须列出。kind 为 body_pose/fixed_extrinsic/derived；body_pose 指定跟随刚体及固定偏移，fixed_extrinsic 指定 `T_parent_from_child`，derived 指定外置 `algorithm_id`、版本和参数，不能用一次快照矩阵冒充水平参考系算法。是否使用 tf_static 由相对位姿是否恒定决定，与当前物体是否暂时静止无关。此示例不改变现有 LidarVisualizer 的 legacy frame 命名。

`profile_deviations` 每项写 rule_id/actual/reason/evidence_file；`consumer_compatibility` 中 passed 项必须带 version_or_digest 与 evidence_file。adapter_file=null 表示确实不需要适配，而不是尚未调查。
