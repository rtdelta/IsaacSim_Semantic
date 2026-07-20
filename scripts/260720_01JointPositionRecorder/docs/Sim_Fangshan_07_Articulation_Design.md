# Sim_Fangshan_07 Articulation 配置与关节位置记录方案

## 1. 文档目的

本文档记录远端场景文件 `Sim_Fangshan_07.usda` 相对于 `Sim_Fangshan_06.usda` 的改动，并定义固定基座四关节挖掘机运动链在 Isaac Sim 中采用 Articulation 直接关节位置控制时必须满足的配置、运行逻辑和记录约定。

本方案的核心约束如下：

- 四个 RevoluteJoint 必须始终保持 `physics:jointEnabled = 1`。
- 不使用 Angular Drive、力矩、刚度或阻尼驱动运动。
- 脚本根据目标角度和指定角速度生成逐帧关节位置。
- 通过 Articulation 的直接关节状态接口应用位置。
- 每帧读取 Articulation 实际关节位置并写入 CSV。
- `Sim_Fangshan_05.usda` 和 `Sim_Fangshan_06.usda` 保持不变。

## 2. 文件位置与校验信息

远端文件：

```text
源文件：/root/gpufree-data/wyb/StageMaterial02/Sim_Fangshan_06.usda
新文件：/root/gpufree-data/wyb/StageMaterial02/Sim_Fangshan_07.usda
```

生成后的校验信息：

| 文件 | SHA-256 | 大小 | 权限 | 属主 |
|---|---|---:|---:|---|
| `Sim_Fangshan_06.usda` | `0e50e88d381b3d198dca26481cc41fcbbed63b523a76180f67bb73aaacea64db` | 34953 bytes | `644` | `root:root` |
| `Sim_Fangshan_07.usda` | `42d06ffc930e4d4b40920b2336d18e85e3bddc2e14a8bee55e560e402acc59cf` | 34572 bytes | `644` | `root:root` |

`Sim_Fangshan_06.usda` 的哈希和修改时间在创建 `07` 前后保持不变。

## 3. 07 相对于 06 的改动

### 3.1 新增固定基座 Articulation 根关节

在 `/World/Joints` 下新增：

```usda
def PhysicsFixedJoint "world_track_fixed_joint" (
    prepend apiSchemas = ["PhysicsArticulationRootAPI"]
)
{
    rel physics:body0 = </root/Xform/track_mesh>
    bool physics:collisionEnabled = 0
    bool physics:jointEnabled = 1
}
```

作用：

- 将 `track_mesh` 固定到世界坐标系。
- 将该 FixedJoint 标记为固定基座 Articulation 的根。
- 允许 PhysX 从根关节沿四个 RevoluteJoint 发现完整运动链。
- 不需要把 `track_mesh` 保持为 kinematic 刚体。

### 3.2 五个刚体全部改为非 kinematic

涉及的刚体：

```text
/root/Xform/track_mesh
/root/Xform/operator_cab_mesh
/root/Xform/boom_mesh
/root/Xform/small_arm_mesh
/root/Xform/bucket_only_full_teeth_mesh
```

`track_mesh` 在 `06` 中为：

```usda
bool physics:kinematicEnabled = 1
```

在 `07` 中改为：

```usda
bool physics:kinematicEnabled = 0
```

其余四个运动部件在 `06` 中已经是非 kinematic，`07` 保持不变。因此 `07` 中五个 link 均满足：

```usda
bool physics:kinematicEnabled = 0
bool physics:rigidBodyEnabled = 1
vector3f physics:velocity = (0, 0, 0)
vector3f physics:angularVelocity = (0, 0, 0)
bool physxRigidBody:disableGravity = 1
```

底盘固定由 `world_track_fixed_joint` 完成，而不是由 kinematic 属性完成。

### 3.3 五个刚体添加显式质量属性

五个刚体的 `apiSchemas` 从：

```usda
prepend apiSchemas = ["PhysicsRigidBodyAPI", "PhysxRigidBodyAPI"]
```

改为：

```usda
prepend apiSchemas = ["PhysicsRigidBodyAPI", "PhysxRigidBodyAPI", "PhysicsMassAPI"]
```

每个刚体新增：

```usda
point3f physics:centerOfMass = (0, 0, 0)
float3 physics:diagonalInertia = (1, 1, 1)
float physics:mass = 1
quatf physics:principalAxes = (1, 0, 0, 0)
```

这些值用于确保 Articulation 初始化时具有正质量和有效惯量，避免 `06` 中出现的无效质量、负质量占位值和小球近似惯量警告。

这些数值是关节状态控制模式使用的临时有效值，不代表真实挖掘机的质量与惯量标定结果。如果以后启用真实动力学、碰撞或力矩控制，必须重新进行物理参数标定。

### 3.4 移除四个 Angular Drive

`07` 从四个 RevoluteJoint 上移除了：

```usda
prepend apiSchemas = ["PhysicsDriveAPI:angular"]
```

同时删除全部 Drive 属性：

```usda
drive:angular:physics:damping
drive:angular:physics:maxForce
drive:angular:physics:stiffness
drive:angular:physics:targetPosition
drive:angular:physics:targetVelocity
drive:angular:physics:type
```

删除原因：

- `06` 中存在非零 `targetPosition`。
- Timeline 启动后，Drive 会主动施加力矩，将初始约为 `0°` 的关节拉向这些历史目标角。
- 新方案由脚本直接设置 Articulation 关节状态，不能再由 Drive 同时控制相同 DOF。
- 去除 Drive 不等于禁用关节；RevoluteJoint 仍然 enabled，限位和运动拓扑仍然有效。

### 3.5 保留四个 RevoluteJoint

四个关节的以下配置均保留：

- Prim 类型 `PhysicsRevoluteJoint`
- `physics:body0`
- `physics:body1`
- `physics:localPos0`
- `physics:localPos1`
- `physics:localRot0`
- `physics:localRot1`
- `physics:axis = "X"`
- `physics:lowerLimit`
- `physics:upperLimit`
- `physics:collisionEnabled = 0`
- `physics:jointEnabled = 1`

`07` 中没有任何 `physics:jointEnabled = 0`。

## 4. 必须保持的运动链拓扑

固定基座运动链为：

```text
World
└─ world_track_fixed_joint
   └─ track_mesh
      └─ track_operator_cab_joint
         └─ operator_cab_mesh
            └─ platform_boom_joint
               └─ boom_mesh
                  └─ boom_small_arm_joint
                     └─ small_arm_mesh
                        └─ small_arm_bucket_joint
                           └─ bucket_only_full_teeth_mesh
```

关节定义：

| 逻辑名称 | Prim 路径 | 父刚体 | 子刚体 | 限位 |
|---|---|---|---|---:|
| Cab | `/World/Joints/track_operator_cab_joint` | `track_mesh` | `operator_cab_mesh` | `-180° ～ 180°` |
| Boom | `/World/Joints/platform_boom_joint` | `operator_cab_mesh` | `boom_mesh` | `-35° ～ 70°` |
| Small arm | `/World/Joints/boom_small_arm_joint` | `boom_mesh` | `small_arm_mesh` | `-80° ～ 70°` |
| Bucket | `/World/Joints/small_arm_bucket_joint` | `small_arm_mesh` | `bucket_only_full_teeth_mesh` | `-90° ～ 80°` |

运动链的父子关系必须保持单一、无环。任何一个 link 被两个不同的 enabled 关节同时作为子节点，都会破坏 Articulation 拓扑。

## 5. Articulation 必须满足的配置

### 5.1 Stage 配置

- Stage 必须存在有效的 `PhysicsScene`。
- `upAxis` 保持 `Z`。
- `metersPerUnit` 保持 `1`。
- FixedJoint 上必须存在 `PhysicsArticulationRootAPI`。
- FixedJoint 和四个 RevoluteJoint 必须全部 enabled。
- 五个 link 必须具有 `PhysicsRigidBodyAPI` 和 `PhysicsMassAPI`。
- 五个 link 必须具有正质量和正对角惯量。
- 不允许存在控制同一 RevoluteJoint 的 Angular Drive。

### 5.2 DOF 发现与映射

脚本初始化 Articulation 后，必须验证：

1. Articulation 初始化成功。
2. 发现的 DOF 数量正好为 4。
3. 四个关节名称均存在。
4. 通过名称获取 DOF 索引，不能假设运行时索引顺序等于 USD 文件中的排列顺序。
5. 每个 DOF 的类型均为 Revolute。
6. 运行时限位与 USD 限位一致。

推荐内部映射：

```python
JOINT_NAMES = (
    "track_operator_cab_joint",
    "platform_boom_joint",
    "boom_small_arm_joint",
    "small_arm_bucket_joint",
)
```

### 5.3 单位约定

- GUI 输入：度 `°`
- GUI 角速度：度每秒 `°/s`
- CSV：度 `°`
- Articulation API：弧度 `rad`
- Articulation 速度 API：弧度每秒 `rad/s`

所有单位转换必须集中在 Articulation 适配层，运动规划器和 GUI 不直接处理弧度。

```python
radians = degrees * math.pi / 180.0
degrees = radians * 180.0 / math.pi
```

## 6. 非动力学恒角速度控制逻辑

### 6.1 控制原则

新控制器不向关节写入 Drive 目标，也不计算力矩。它维护以下状态：

```text
当前实际角度 q_actual
目标角度 q_target
指定角速度 speed
运动方向 sign(q_target - q_actual)
是否到达 reached
```

Articulation 的直接关节位置接口会立即设置关节状态。为了获得连续运动，脚本必须每帧生成一个不超过 `speed × dt` 的中间角度。

### 6.2 单关节更新算法

```python
error = target_degrees - current_degrees
max_step = speed_degrees_per_second * dt

if abs(error) <= max_step:
    next_degrees = target_degrees
    reached = True
else:
    next_degrees = current_degrees + math.copysign(max_step, error)
    reached = False
```

必须满足：

- `speed > 0`
- `dt > 0`
- `dt` 应限制最大值，例如 `MAX_UPDATE_DT = 0.05`
- 目标角必须位于安全限位内
- 最后一帧直接写入目标角，防止累积误差和超调

### 6.3 多关节更新

四个关节使用相同帧时间 `dt`，但分别维护目标和角速度。

默认模式为独立速度模式：

- 四个关节同时开始。
- 每个关节以自己的指定速度运动。
- 不同关节可以在不同时间到达目标。
- 已到达的关节保持最终位置，其余关节继续运动。
- 四个关节全部到达后，整体状态变为 `REACHED`。

第一版不要求四个关节同时到达。如果以后需要同步到达，应新增独立模式，而不是改变每个输入角速度的含义。

### 6.4 更新与记录顺序

每个更新帧应严格执行：

```text
读取当前 Articulation 关节位置
→ 计算四个 next position
→ 将 degree 转成 radian
→ 一次性设置四个 DOF 位置
→ 推进/更新一帧
→ 从 Articulation 回读实际 DOF 位置
→ 转换成 degree
→ 更新 GUI 当前角度
→ 写入 CSV
→ 检查到达状态
```

不要分别触发四次完整的场景更新。四个关节的位置应在同一帧一次性提交，保证采集图像与关节状态一致。

## 7. GUI 功能块

每个关节一行：

| 字段 | 类型 | 说明 |
|---|---|---|
| Current angle | 只读 | Articulation 回读的实际角度 |
| Target angle | 可编辑 | 本次运动目标角度 |
| Speed | 可编辑 | 正数，单位 `°/s` |
| Status | 只读 | `Idle`、`Moving`、`Reached` 或 `Error` |

推荐按钮：

- `Move all`：读取当前角度并启动四关节运动。
- `Stop`：停止在当前角度，并将目标同步为当前位置。
- `Reset targets`：只把目标输入框重置为当前角度，不立即运动。
- `Home`：以指定速度移动到 Home 角度。
- `Start recording`：开始实时角度记录。
- `Stop recording`：完成校验并发布 CSV。

修改目标角或角速度不应立即触发运动，必须显式点击 `Move all`。

## 8. 状态机

推荐状态：

```text
IDLE
  └─ Move all → MOVING

MOVING
  ├─ Stop → IDLE
  ├─ 全部到达 → REACHED
  └─ 异常 → ERROR

REACHED
  ├─ 修改参数并 Move all → MOVING
  └─ Reset targets → IDLE
```

Stage 变化、Articulation 失效、DOF 数量变化或关节名称缺失时，应立即进入 `ERROR`，停止运动并结束或中止当前记录。

脚本重复运行前必须取消旧的键盘、更新和物理事件订阅，防止多个控制器同时写入同一 Articulation。

## 9. 实时角度记录

为保持与现有语义采集轨迹播放器兼容，主 CSV 继续采用：

```csv
time,cab,boom,small_arm,bucket
0.000000000,0.000000000,0.000000000,0.000000000,0.000000000
0.016666667,0.133333333,0.083333333,-0.083333333,0.083333333
```

与旧 Recorder 的区别：

- 旧 Recorder 记录 Drive `targetPosition`。
- 新 Recorder 必须记录 Articulation 回读的实际 DOF position。
- CSV 中角度仍使用度。
- 时间必须严格递增。
- 第一条记录时间为 `0.0`。
- 最后一条记录必须包含最终精确目标角。

建议同时生成元数据 JSON：

```json
{
  "usd": "/root/gpufree-data/wyb/StageMaterial02/Sim_Fangshan_07.usda",
  "control_mode": "articulation_direct_position",
  "angle_unit": "degree",
  "speed_unit": "degree_per_second",
  "joint_order": ["cab", "boom", "small_arm", "bucket"],
  "target_angles": {},
  "commanded_speeds": {},
  "physics_dt": 0.0166666667,
  "completed": true
}
```

纯关节状态控制下，回读角度通常会等于本帧命令角度。这里的“实际角度”表示 Isaac Sim Articulation 已接受并应用的状态，不表示真实动力学跟踪误差。

## 10. 与旧 Recorder 的兼容性

现有目录：

```text
/root/gpufree-data/repositories/260714_02ExcavatorActionRecorder
```

其中 `ExcavatorJointController.bind()` 强制查找：

```text
drive:angular:physics:targetPosition
```

由于 `07` 已移除 Angular Drive，旧 Recorder 在 `07` 上绑定失败是预期行为。不得为了兼容旧 Recorder 而重新向 `07` 添加 Drive，否则会重新引入自运动和双控制器竞争问题。

新项目应实现独立的 Articulation 控制器和实际角度 Recorder。

## 11. 建议默认参数

| 参数 | 默认值 |
|---|---:|
| 更新频率 | 60 Hz |
| 最大 `dt` | 0.05 s |
| 到达容差 | 0.01° |
| Cab 角速度 | 8°/s |
| Boom 角速度 | 5°/s |
| Small arm 角速度 | 5°/s |
| Bucket 角速度 | 5°/s |
| 多关节模式 | 同时启动、独立到达 |
| Stop 行为 | 保持当前位置 |

严格恒角速度意味着启动和停止瞬间存在速度突变。由于本方案直接设置关节状态而不计算动力学，这不会产生真实冲击。如果后续需要更自然的视觉运动，应作为新增模式实现梯形速度或 S 曲线，而不是改变恒角速度模式。

## 12. 验收标准

Stage 验收：

1. `Sim_Fangshan_07.usda` 可被 USD 解析器打开。
2. 五个 link 均具有 RigidBodyAPI 和 MassAPI。
3. 五个 link 均为非 kinematic。
4. FixedJoint 具有 ArticulationRootAPI 并连接 `track_mesh`。
5. FixedJoint 和四个 RevoluteJoint 全部 enabled。
6. 四个 RevoluteJoint 不存在 Angular Drive。
7. 四个关节的轴、锚点、父子关系和限位保持不变。

运行时验收：

1. Articulation 初始化成功并发现 4 个 DOF。
2. 未执行控制命令时，Timeline 运行不会产生主动运动。
3. 输入目标和速度后，关节才开始运动。
4. 每个关节的平均角速度与设定值一致，误差只来自离散采样的最后一步。
5. 关节不超调且最终角度精确等于目标值。
6. 四个关节可以使用不同角速度同时运动。
7. Stop 后保持当前位置。
8. CSV 记录 Articulation 回读角度，而不是目标输入值。
9. 重复运行面板不会产生重复订阅或多控制器竞争。
10. 日志中不再出现无效质量或惯量警告。

## 13. 当前验证状态

`Sim_Fangshan_07.usda` 已通过 Isaac Sim 自带 `pxr.Usd` 解析验证，确认：

- 五个目标刚体均识别到 RigidBodyAPI。
- 五个目标刚体均识别到 MassAPI。
- 五个目标刚体的 `kinematicEnabled` 均为 `false`。
- 五个目标刚体的显式质量均为正数。
- 四个 RevoluteJoint 均为 enabled。
- 四个 RevoluteJoint 均未应用 Angular Drive。
- `world_track_fixed_joint` 类型为 PhysicsFixedJoint。
- FixedJoint 具有 ArticulationRootAPI。
- FixedJoint 的 `body0` 正确指向 `/root/Xform/track_mesh`。

尚未在独立 SimulationApp 中完成运行时 DOF 枚举和恒速运动测试。该项应在新控制面板实现后作为第一项集成测试执行。
