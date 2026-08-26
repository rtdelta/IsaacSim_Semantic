# Semantic World Module 支持 JointPositionRecorder_zhanyang 根位姿轨迹的实现方案

## 1. 文档目的

本文档给出 `260714_01semantic_worldModule` 读取 `JointPositionRecorder_zhanyang` 版本输出 CSV，并在离线语义采集过程中按照 CSV 同步回放以下状态的完整实现方案：

- 驾驶室关节角 `cab`；
- 动臂关节角 `boom`；
- 小臂关节角 `small_arm`；
- 铲斗关节角 `bucket`；
- 挖掘机根节点的世界坐标位置；
- 挖掘机根节点的世界旋转。

方案的核心目标是将现有“固定基座四关节回放”扩展为“浮动 Articulation Root + 四关节 + 根世界位姿回放”，使挖掘机在离线采集时能够按照 CSV 整体移动和旋转，而不是继续受 `fixed_root` 约束。

本文档仅描述实现设计、修改范围、测试和验收要求，不包含本轮代码修改。

## 2. 当前系统状态

### 2.1 Semantic World Module 当前运动模型

当前 `excavator_joint_motion.py` 只接受以下 CSV：

```csv
time,cab,boom,small_arm,bucket
```

当前实现具有以下特征：

- 只解析四个旋转关节；
- 只对四关节角度做线性插值；
- 使用 Isaac Sim Articulation direct-position API 写入四个 DOF；
- 每个物理步前写入关节位置；
- 每个物理步后回读实际关节位置；
- 使用固定基座 Articulation profile；
- 不读取或写入 Articulation Root 的世界位置和旋转；
- 输出状态中不包含根位姿命令、回读和误差。

因此，即使放宽 CSV 列检查，新增根位姿列也只会被忽略，挖掘机整体仍不会移动。

### 2.2 JointPositionRecorder_zhanyang CSV 格式

`JointPositionRecorder_zhanyang` 在启用 root motion 后输出以下列：

```csv
time,
cab,boom,small_arm,bucket,
root_quat_w,root_quat_x,root_quat_y,root_quat_z,
root_roll_x_deg,root_pitch_y_deg,root_yaw_z_deg,
root_world_x_m,root_world_y_m,root_world_z_m
```

合并为实际 CSV 表头：

```csv
time,cab,boom,small_arm,bucket,root_quat_w,root_quat_x,root_quat_y,root_quat_z,root_roll_x_deg,root_pitch_y_deg,root_yaw_z_deg,root_world_x_m,root_world_y_m,root_world_z_m
```

各列含义如下：

| 列 | 含义 | 单位/约定 |
|---|---|---|
| `time` | 记录会话的有效累计时间 | 秒 |
| `cab` | 驾驶室实际关节角 | 度 |
| `boom` | 动臂实际关节角 | 度 |
| `small_arm` | 小臂实际关节角 | 度 |
| `bucket` | 铲斗实际关节角 | 度 |
| `root_quat_w/x/y/z` | 根节点世界旋转四元数 | `wxyz`，无量纲 |
| `root_roll_x_deg` | 根节点世界 Roll | 度 |
| `root_pitch_y_deg` | 根节点世界 Pitch | 度 |
| `root_yaw_z_deg` | 根节点世界 Yaw | 度 |
| `root_world_x/y/z_m` | 根节点模型原点的世界位置 | 米 |

根旋转应以四元数列为权威数据。Euler 角是用于人工阅读和兼容下游工具的冗余表示，不应作为旋转插值和驱动的主要数据源。

### 2.3 当前主要不兼容点

现有模块与新 CSV 之间存在以下阻塞：

1. CSV 表头被严格限定为五列，新表头会直接被拒绝。
2. 轨迹关键帧数据结构只保存关节角，不保存根位置和根旋转。
3. Articulation Adapter 只提供四关节位置读写，不提供 root world pose 读写。
4. 当前 joint profile 要求 `require_fixed_base=true`。
5. 当前 USD Articulation Root 通常位于 `world_track_fixed_joint`，无法可靠执行整体移动。
6. 当前 sidecar metadata 只接受 `articulation_direct_position` 控制模式。
7. Recorder 输出的控制模式为 `articulation_direct_joint_position_and_root_pose`。
8. Recorder profile 名称与现有 semantic profile 名称不同，会触发 profile match 失败。
9. 当前每帧 motion state 和最终输出验证器只验证四关节。
10. 当前 body world transform 记录会在五刚体链中忽略第一个 root body。

## 3. 总体设计

### 3.1 目标执行链

```text
JointPositionRecorder_zhanyang CSV
        ↓
解析四关节角 + 根世界位置 + 根世界四元数
        ↓
按照 dataset_time 对轨迹采样和插值
        ↓
物理步前：
  写入四关节位置
  写入浮动根世界位姿
  清零关节速度和根速度
        ↓
推进一次 Physics
        ↓
回读四关节和根世界位姿
        ↓
按照配置决定是否在捕获前重新对齐根位姿
        ↓
冻结 Timeline 和 Physics
        ↓
采集 full_scene / excavator_only / front_teeth_only
```

### 3.2 兼容策略

系统应同时支持旧格式和新格式：

| CSV 类型 | 基座要求 | 回放行为 |
|---|---|---|
| 旧五列 CSV | 可继续使用 fixed base | 只控制四关节 |
| 新十五列 CSV | 必须使用 floating base | 同时控制四关节与根世界位姿 |

不得采用“允许任意额外列但静默忽略”的策略。对于新 CSV，应要求配置显式启用 root pose playback；否则启动时直接报错。

### 3.3 推荐的回放语义

本需求的主要目标是离线语义数据采集中的轨迹复现，而不是履带动力学仿真。因此推荐默认采用：

```text
authoritative_pose
```

即 CSV 采样结果是最终采集位姿的权威状态。Physics 可以用于更新 Articulation、接触和渲染状态，但不允许物理漂移显著改变最终捕获位姿。

## 4. CSV 轨迹模型设计

### 4.1 常量定义

建议在轨迹模块中明确维护：

```text
JOINT_NAMES
ROOT_QUATERNION_COLUMNS
ROOT_EULER_COLUMNS
ROOT_WORLD_POSITION_COLUMNS
LEGACY_TRAJECTORY_COLUMNS
ROOT_POSE_TRAJECTORY_COLUMNS
```

其中：

```text
JOINT_NAMES = cab, boom, small_arm, bucket
ROOT_QUATERNION_COLUMNS = root_quat_w, root_quat_x, root_quat_y, root_quat_z
ROOT_EULER_COLUMNS = root_roll_x_deg, root_pitch_y_deg, root_yaw_z_deg
ROOT_WORLD_POSITION_COLUMNS = root_world_x_m, root_world_y_m, root_world_z_m
```

### 4.2 关键帧数据结构

当前关键帧只有时间和关节目标。建议改为逻辑等价的数据结构：

```text
ExcavatorTrajectoryKeyframe
  time
  joint_positions_degrees
  root_world_position_meters | None
  root_orientation_wxyz | None
  recorded_euler_xyz_degrees | None
```

旧五列 CSV 的根位姿字段为 `None`。新十五列 CSV 的根位姿字段必须全部存在，不允许只提供位置或只提供旋转。

### 4.3 CSV schema 识别

读取器只接受两种明确表头：

1. `LEGACY_TRAJECTORY_COLUMNS`；
2. `ROOT_POSE_TRAJECTORY_COLUMNS`。

对于以下情况应直接拒绝：

- 列缺失；
- 列顺序错误；
- 存在未知额外列；
- 只包含部分根位姿列；
- 根位姿 CSV 与启动配置不匹配。

### 4.4 数值校验

每行应校验：

- `time` 为有限非负数；
- 四关节角为有限数；
- 根位置三个分量均为有限数；
- 根四元数四个分量均为有限数；
- 根四元数不能为零四元数；
- 根四元数归一化后才能进入内存轨迹；
- Euler 三个分量必须为有限数，但不作为控制权威值；
- 第一帧时间必须为 `0.0`；
- 至少包含两个关键帧；
- 时间严格递增。

可以增加可配置的 quaternion norm 容差。轻微浮点偏差可归一化，明显异常应拒绝。

### 4.5 插值规则

轨迹采样返回统一的 `ExcavatorTrajectorySample`：

```text
trajectory_time
joint_positions_degrees
root_world_position_meters | None
root_orientation_wxyz | None
```

插值规则：

- 四关节角：线性插值；
- 根世界位置：线性插值；
- 根世界旋转：四元数 SLERP；
- Euler：不直接插值，必要时由插值后的四元数重新计算。

SLERP 必须处理：

- 输入四元数归一化；
- `q` 和 `-q` 表示相同旋转；
- 点积为负时翻转其中一个四元数，以选择最短旋转路径；
- 两四元数非常接近时退化为归一化线性插值；
- 输出再次归一化。

### 4.6 `hold` 模式

当数据集时间超过轨迹时长时：

- 四关节保持最后一帧角度；
- 根位置保持最后一帧位置；
- 根旋转保持最后一帧四元数。

### 4.7 `loop` 模式

除现有四关节首尾闭合检查外，还必须检查：

- 根首尾位置的欧氏距离小于配置容差；
- 根首尾旋转的四元数角距离小于配置容差。

四元数闭合不能直接逐分量比较，因为 `q` 与 `-q` 表示同一旋转。

Recorder 人工录制的非闭合轨迹应使用 `hold`。若检测到不闭合的新格式 CSV 配置为 `loop`，应在启动阶段拒绝。

## 5. USD 与 Articulation Root 改造

### 5.1 为什么必须取消 fixed root

现有 semantic profile 通常将 `PhysicsArticulationRootAPI` 放在 `world_track_fixed_joint` 上，并要求固定基座。FixedJoint 会将根刚体约束到世界，直接写入 root world pose 会受到约束冲突或被 PhysX 恢复，因此不能作为正式方案。

### 5.2 推荐建立独立浮动 Stage

建议新建一个专用于整体运动离线采集的 USD/USDA 版本，不覆盖现有固定基座 Stage，从而保持旧采集配置可继续使用。

浮动版本应满足：

- `PhysicsArticulationRootAPI` 位于履带或根刚体；
- 世界到履带的 FixedJoint 被删除或禁用；
- 原 FixedJoint 上不再保留有效 ArticulationRootAPI；
- Stage 中只有一个目标 Articulation Root；
- root/track 具有 `RigidBodyAPI`；
- `physics:rigidBodyEnabled=true`；
- `physics:kinematicEnabled=false`；
- root/track 具有有效 mass 和 diagonal inertia；
- 四个内部 RevoluteJoint 仍形成连续的五刚体链；
- 四个内部关节不保留 `PhysicsDriveAPI:angular`；
- Camera、语义 Prim 和可见性隔离 Prim 仍处于正确的模型层级中。

### 5.3 非破坏性 USD 处理建议

优先使用独立的浮动版本或 overlay layer：

- 保留原 fixed-base USD；
- 浮动版本禁用世界固定关节；
- 将 ArticulationRootAPI 应用到实际 root rigid body；
- 避免在采集程序启动时临时修改持久 Stage；
- 在 Stage preflight 中记录浮动根的最终组合结果。

如果使用 overlay，需要确认原 fixed joint 上的 ArticulationRootAPI 已通过组合规则正确移除，而不是仅仅把 joint disabled 后留下两个 Articulation Root。

## 6. Joint Control Profile 设计

### 6.1 新建浮动 profile

保留现有 fixed-base profile，新增 semantic world 专用浮动 profile，例如：

```text
configs/waji_aligned_four_joint_floating_semantic.json
```

建议将 joint-control profile schema 升级，并增加以下语义：

```json
{
  "schema_version": 2,
  "profile_name": "waji_aligned_four_joint_floating",
  "articulation_root_path": "/Waji_Mesh_3DGS/track",
  "require_fixed_base": false,
  "require_floating_base": true,
  "root_pose_playback_supported": true,
  "root_position_readback_tolerance_meters": 0.001,
  "root_orientation_readback_tolerance_degrees": 0.05
}
```

以上数值应通过真实 Isaac Sim smoke test 调整，不应在未经验证时视为最终生产默认值。

### 6.2 Profile 必须继续包含

- 四个逻辑关节定义；
- candidate names；
- candidate paths；
- safety margin；
- 关节 readback tolerance；
- 是否禁止 Angular Drive；
- trajectory sidecar 契约；
- 兼容的 Recorder profile 名；
- 兼容的 control mode；
- 根位姿单位和四元数顺序约定。

### 6.3 `require_floating_base` 的必要性

只设置 `require_fixed_base=false` 表示“固定根和浮动根都可以接受”，不能保证当前 Stage 真的可移动。

当 `root_pose_playback.enabled=true` 时必须要求：

```text
require_floating_base=true
```

并在 Stage validator 中拒绝 FixedJoint 类型的 Articulation Root。

## 7. Articulation Adapter 扩展

### 7.1 新增接口

在现有四关节接口之外增加：

```text
get_root_world_pose()
set_root_world_pose(position_meters, orientation_wxyz)
zero_root_velocities()
```

也可以封装一个更高层的原子语义接口：

```text
set_excavator_state(
  joint_positions_degrees,
  root_position_meters,
  root_orientation_wxyz
)
```

底层仍可以依次调用 Isaac API，但对上层表现为同一个 physics pre-step 中完成的一次状态提交。

### 7.2 根位姿读取

通过 Articulation wrapper 的 `get_world_poses()` 读取：

- 单个 Articulation Root 的三维世界位置；
- 单个 Articulation Root 的 `wxyz` 世界四元数。

需要检查：

- 返回值中只能有一个 root pose；
- position shape 为 `1 x 3`；
- orientation shape 为 `1 x 4`；
- 所有值均为有限数；
- quaternion 非零并归一化后返回。

### 7.3 根位姿写入

通过 `set_world_poses()` 写入：

- `positions` shape 为 `1 x 3`；
- `orientations` shape 为 `1 x 4`；
- quaternion 使用 Isaac 的 `wxyz` 顺序；
- 输入 quaternion 写入前归一化。

写入后调用 root velocity API，将：

- linear velocity 清零；
- angular velocity 清零。

现有四关节 `set_dof_positions()` 和 `set_dof_velocities()` 行为继续保留。

### 7.4 Adapter binding 信息

`binding_info()` 应增加：

- articulation root path；
- root body path；
- root 是否为 floating；
- 是否支持 world pose 读写；
- 初始 root position；
- 初始 root quaternion；
- DOF 名称到 index 映射；
- adapter bound/ready 状态。

## 8. 每物理步回放策略

### 8.1 初始化与 setup step

Timeline 启动并等待 Articulation tensor ready 后：

1. 从 CSV 采样 `t=0`；
2. 写入 `t=0` 四关节角；
3. 写入 `t=0` 根世界位姿；
4. 清零 DOF/root velocities；
5. 推进一个 setup physics step；
6. 回读四关节和根位姿；
7. 必要时执行 capture-pose reassert；
8. 将当前 physics step 之前的时间排除在 dataset time 之外。

### 8.2 Pre-roll

所有 pre-roll step 都应持续采样并应用 trajectory time `0.0`：

- 四关节保持第一帧；
- 根位置保持第一帧；
- 根旋转保持第一帧。

不能只保持关节而允许 root 在重力作用下漂移。

### 8.3 正式数据时间线

每个物理步：

1. WorldScheduler 计算 `next_dataset_time`；
2. 轨迹模块按该时间采样；
3. physics pre-step 写入四关节与根位姿；
4. 推进一次 Physics；
5. physics post-step 回读四关节与根位姿；
6. 计算关节、位置和旋转误差；
7. 根据 `apply_policy` 处理根漂移；
8. 到达捕获时间时冻结世界并采集。

### 8.4 两种 apply policy

#### `authoritative_pose`，推荐默认值

用于严格按 CSV 生成语义数据：

1. pre-step 写入目标根位姿；
2. Physics 后读取 `physics_readback_pose`；
3. 若误差超过 capture 对齐阈值，则重新写入目标根位姿；
4. 清零 root velocity；
5. 再次读取 `capture_pose`；
6. 最终图像使用 `capture_pose`。

这样可以记录物理漂移，同时保证捕获状态与 CSV 一致。

#### `physics_accepted`

用于更强调物理结果的场景：

- 只在 pre-step 写入；
- 不在捕获前重新对齐；
- 图像使用 Physics 后的实际根位姿；
- 若误差超过 tolerance，可报警或失败。

该策略可能受到重力、碰撞和约束影响，导致图像位置不再严格等于 CSV，因此不建议作为本需求第一版的默认方式。

## 9. 捕获配置扩展

建议升级 capture launch config schema，并加入显式配置：

```json
"root_pose_playback": {
  "enabled": true,
  "coordinate_mode": "absolute_world",
  "position_interpolation": "linear",
  "orientation_interpolation": "slerp",
  "apply_policy": "authoritative_pose",
  "zero_root_velocity": true,
  "position_tolerance_meters": 0.001,
  "orientation_tolerance_degrees": 0.05
}
```

### 9.1 字段约束

- `enabled`：JSON boolean；
- `coordinate_mode`：`absolute_world` 或 `relative_to_initial`；
- `position_interpolation`：第一版只接受 `linear`；
- `orientation_interpolation`：第一版只接受 `slerp`；
- `apply_policy`：`authoritative_pose` 或 `physics_accepted`；
- `zero_root_velocity`：建议第一版必须为 `true`；
- position tolerance：正有限数；
- orientation tolerance：正有限数。

### 9.2 配置与 CSV 的匹配规则

- 新十五列 CSV + `enabled=false`：拒绝，不能静默忽略根位姿；
- 旧五列 CSV + `enabled=true`：拒绝，提示缺少 root pose 列；
- 新十五列 CSV + fixed-base profile：拒绝；
- 新十五列 CSV + floating profile：允许；
- `coordinate_mode=absolute_world`：必须通过坐标系预检；
- `coordinate_mode=relative_to_initial`：必须记录初始变换校准信息。

## 10. 世界坐标和单位策略

### 10.1 `absolute_world`

第一版推荐使用：

```text
T_target(t) = T_csv(t)
```

该模式要求 Recorder 与 semantic capture 使用：

- 相同或严格对齐的模型资产；
- 相同 root 模型原点；
- 相同世界轴方向；
- 相同 up-axis；
- 相同 `metersPerUnit`；
- 相同根四元数约定。

如果这些条件不满足，直接写入 CSV 的绝对世界位姿可能使挖掘机跳到错误位置。

### 10.2 `relative_to_initial`

当 Recorder Stage 与 semantic Stage 的初始世界位置不同，但模型根坐标轴一致时，可以使用：

```text
T_target(t)
  = T_target_initial
  · inverse(T_csv_initial)
  · T_csv(t)
```

该模式保留 CSV 的相对平移和旋转变化，并将轨迹重定位到 semantic Stage 的初始位置。

第一版可只实现 `absolute_world`，但建议配置 schema 预留 `relative_to_initial`，避免后续破坏配置兼容性。

### 10.3 长度单位

CSV 列名声明根位置单位为米。Stage preflight 应读取 USD `metersPerUnit`：

- 若 Stage/API 使用米，直接写入；
- 若 Stage unit 不等于一米，进行显式换算；
- 将源单位、目标单位和换算系数记录到 run manifest；
- 禁止在单位无法确定时静默运行。

### 10.4 Up-axis

应检查 Recorder 与 target Stage 是否使用相同 up-axis。当前 Recorder 的 WASD+FG 根运动逻辑以 Local Z 为前进旋转相关轴约定的一部分，但 CSV 已记录最终世界四元数，因此回放阶段不应重新解释 WASD 输入，只需确保世界坐标约定一致。

## 11. Trajectory metadata sidecar 兼容

### 11.1 Recorder 输出的关键 metadata

根运动模式下 Recorder 会输出：

```text
profile = waji_aligned_four_joint_floating
control_mode = articulation_direct_joint_position_and_root_pose
angle_unit = degree
root_motion_enabled = true
root_quaternion_order = wxyz
recorded_root_orientation_columns
recorded_root_world_position_columns
additional_columns
csv_columns
world_position_reference
completed = true
```

### 11.2 Semantic profile 契约扩展

`TrajectoryMetadataContract` 建议增加：

- `compatible_control_modes`；
- `compatible_recorder_profiles`；
- `require_root_motion_metadata`；
- `position_unit`；
- `quaternion_order`；
- `expected_root_orientation_columns`；
- `expected_root_world_position_columns`；
- `require_world_position_reference`。

### 11.3 新格式 CSV 建议强制 sidecar

旧五列手写 CSV 可以继续允许缺少 sidecar。

新根位姿 CSV 建议强制要求 `<trajectory-stem>.metadata.json`，原因是单靠 CSV 无法可靠确认：

- 根位置单位；
- 四元数顺序；
- 世界坐标参考 Prim；
- Recorder profile；
- Recorder control mode；
- CSV 是否正常完成发布；
- 是否由支持 root motion 的 Recorder 产生。

### 11.4 Profile 匹配策略

不建议完全取消 profile 校验。应由 semantic profile 明确列出兼容的 Recorder profile，例如：

```json
"compatible_recorder_profiles": [
  "waji_aligned_four_joint_floating"
]
```

如果 Recorder root Prim 与 semantic root Prim 路径不同：

- `absolute_world` 模式下应拒绝或要求显式 path alias；
- `relative_to_initial` 模式下允许通过校准映射，但必须记录映射来源。

## 12. Stage Validator 扩展

### 12.1 Root playback 专用检查

当 `root_pose_playback.enabled=true` 时增加：

- profile 明确声明 `require_floating_base=true`；
- `articulation_root_path` 对应有效 Prim；
- root Prim 具有 `PhysicsArticulationRootAPI`；
- root Prim 是带 RigidBodyAPI 的刚体；
- root Prim 不能是 FixedJoint；
- 不存在另一个竞争性的 Articulation Root；
- world-track FixedJoint 不存在或已禁用且不再持有 Root API；
- root body 是四关节链的第一个 body；
- root body 非 kinematic；
- root body 的 mass 和 inertia 有效；
- Stage `metersPerUnit` 和 up-axis 已确认；
- Camera 和需要捕获的语义资产确实继承根运动。

### 12.2 保持现有关节检查

现有以下检查继续保留：

- 正好四个逻辑关节；
- candidate name/path 唯一解析；
- RevoluteJoint 类型；
- joint enabled；
- 无 Angular Drive；
- body0/body1 唯一；
- 连续五刚体链；
- 无循环；
- 有效限位与 safety margin；
- 所有 link 的 RigidBodyAPI、MassAPI、mass、inertia 和非 kinematic 状态。

## 13. Motion Scheduler 扩展

### 13.1 类职责

现有 `ExcavatorJointMotion` 实际将扩展为同时负责：

- 轨迹 CSV 加载；
- 四关节采样；
- root position 采样；
- root quaternion 采样；
- 关节和根状态提交；
- 关节和根状态回读；
- readback tolerance；
- 每帧 motion state 输出。

可以保留类名以减少调用方修改，也可以在后续重构中改名为 `ExcavatorTrajectoryMotion`。第一版建议保留现有类名，将功能扩展限定在内部。

### 13.2 运行状态

建议新增内部状态：

```text
_commanded_root_position
_commanded_root_orientation
_physics_readback_root_position
_physics_readback_root_orientation
_capture_root_position
_capture_root_orientation
_root_position_error
_root_position_error_norm
_root_orientation_error_degrees
_root_pose_reasserted
```

### 13.3 `before_physics_step()`

对于新格式轨迹：

1. 按 dataset time 采样；
2. 写入四关节目标；
3. 写入 root position/quaternion；
4. 清零四关节速度；
5. 清零 root linear/angular velocity；
6. 保存 commanded state。

### 13.4 `after_physics_step()`

1. 回读四关节；
2. 回读 Physics 接受后的 root pose；
3. 计算四关节误差；
4. 计算根位置逐轴误差和欧氏距离；
5. 计算四元数角距离；
6. 根据 apply policy 选择失败、接受或重新对齐；
7. 保存最终 capture pose。

### 13.5 根旋转误差

建议使用符号不敏感的角距离：

```text
d = clamp(abs(dot(q_commanded, q_actual)), 0, 1)
orientation_error = 2 * acos(d)
```

最终转换为度。使用 `abs(dot)` 可以避免将 `q` 和 `-q` 误判为不同旋转。

## 14. Orchestrator 调整

### 14.1 不需要改变的时序骨架

现有 `WorldScheduler` 已支持：

- physics pre-step callback；
- physics post-step callback；
- setup step；
- pre-roll；
- dataset time origin；
- capture freeze；
- capture 后恢复 Timeline。

因此不需要重写整体调度器，只需让现有 motion callback 同时处理根位姿。

### 14.2 需要调整的 Orchestrator 内容

- 在读取 config 后解析 `root_pose_playback`；
- 在加载 trajectory metadata 后验证 root contract；
- 将 root playback 要求传给 Stage validator；
- 创建 motion scheduler 时传入 root playback config；
- setup/pre-roll callback 同时保持根位姿；
- manifest 中记录 root playback 配置和实际 binding；
- 捕获前确认 motion scheduler 的最终 capture pose 已确定；
- Camera state 应在根位姿最终对齐之后读取；
- 所有 variant 使用同一个冻结后的根位姿。

### 14.3 Camera 行为

如果 Camera 位于挖掘机层级内部，它会随 root 和关节运动改变世界变换。现有 Camera world transform 校验可以继续使用。

如果 Camera 是外部固定相机，则挖掘机整体运动会改变其在图像中的位置。这两种情况都不需要 Camera scheduler 新增运动控制，但配置中的 `camera_prim_path` 必须对应浮动 Stage 的真实路径。

## 15. Manifest 与每帧状态

### 15.1 Run manifest

建议提升 run config schema version，并在 `motion_control` 中记录：

```json
{
  "joint_control_mode": "articulation_direct_position",
  "root_control_mode": "articulation_direct_world_pose",
  "trajectory_schema": "joint_and_root_pose_v1",
  "root_pose_playback": {
    "enabled": true,
    "coordinate_mode": "absolute_world",
    "position_interpolation": "linear",
    "orientation_interpolation": "slerp",
    "apply_policy": "authoritative_pose",
    "position_tolerance_meters": 0.001,
    "orientation_tolerance_degrees": 0.05
  }
}
```

同时记录：

- trajectory path 和 SHA-256；
- sidecar path 和 SHA-256；
- source root Prim path；
- target root Prim path；
- Stage unit/up-axis；
- 坐标换算或初始对齐矩阵；
- floating articulation binding；
- Adapter 的 world-pose 能力。

### 15.2 每帧 motion state

建议新增：

```json
{
  "motion": {
    "commanded_degrees": {},
    "actual_degrees": {},
    "position_error_degrees": {},
    "root_pose": {
      "enabled": true,
      "coordinate_mode": "absolute_world",
      "commanded_position_meters": [0, 0, 0],
      "commanded_orientation_wxyz": [1, 0, 0, 0],
      "physics_readback_position_meters": [0, 0, 0],
      "physics_readback_orientation_wxyz": [1, 0, 0, 0],
      "capture_position_meters": [0, 0, 0],
      "capture_orientation_wxyz": [1, 0, 0, 0],
      "position_error_meters": [0, 0, 0],
      "position_error_norm_meters": 0,
      "orientation_error_degrees": 0,
      "reasserted_after_physics": false
    }
  }
}
```

### 15.3 Body world transform

当前五刚体链记录会忽略第一个 root body。扩展后应记录：

```text
root/track
cab
boom
small_arm
bucket
```

建议使用明确的逻辑名称，而不是继续依赖 `zip(JOINT_NAMES, body_paths[1:])`。

## 16. Writer 与 CaptureContext

现有 `CaptureContext` 可以透传嵌套 `motion_state`，`semantic_dataset_writer` 也会将 context 写入每帧 metadata，因此通常不需要改动核心传输结构。

可能需要的修改：

- 提升每帧 metadata schema version；
- 增加针对 root pose 字段的单元测试；
- 确认 tuple/list 的 JSON 转换对嵌套 root pose 正常；
- 确认三个 variant 的 metadata 中 root capture pose 完全一致。

## 17. 离线输出验证扩展

`validate_semantic_output.py` 应增加以下检查。

### 17.1 Manifest 检查

- root playback 配置存在且结构正确；
- trajectory schema 与 CSV 表头一致；
- floating Articulation Stage preflight 通过；
- root Adapter 被记录为 bound/ready；
- source/target coordinate contract 完整；
- position/orientation tolerance 为正有限数；
- `authoritative_pose` 的最终 capture pose 策略被正确记录。

### 17.2 每帧根位姿检查

- commanded、physics readback、capture position 均为三个有限数；
- commanded、physics readback、capture quaternion 均为四个有限数；
- quaternion 接近单位长度；
- position error 与实际差值一致；
- position error norm 计算正确；
- orientation error 计算正确；
- capture pose 与 commanded pose 的误差不超过 tolerance；
- `reasserted_after_physics` 与 physics/capture pose 关系一致。

### 17.3 运动性检查

如果 CSV 根位置发生变化：

- root body world transform 必须发生变化。

如果 CSV 根旋转发生变化：

- root body world transform 的旋转部分必须发生变化。

不能继续只用“任意一个关节 body transform 是否变化”作为整体运动是否发生的证据。

### 17.4 Variant 同步检查

同一 `frame_id` 下：

- full scene；
- excavator only；
- front teeth only；

三种正式 capture metadata 中的根 capture pose、关节 actual state、dataset time、physics step 必须一致。

### 17.5 `static`/`motion` 语义

- `capture_mode=static` 时，关节、root 和 Camera 都不能变化；
- motion 模式只启用关节轨迹时，允许 root 不变；
- motion 模式启用 root pose playback 且 CSV root 有变化时，root 必须变化；
- `hold` 超过轨迹末尾后，root 和四关节必须保持最终状态。

## 18. Scene Visibility 与语义内容

根位姿回放不需要改变 SceneVariantController 的基本机制，但需要确认：

- visibility whitelist 使用浮动 Stage 的真实 Prim 路径；
- root 移动不会改变 Prim identity；
- full scene 恢复仍与启动 baseline 一致；
- 临时 visibility layer 不修改持久 USD layer；
- probe 和正式 capture 发生在同一个冻结 root pose 下；
- root 移动后目标语义可能离开相机视野，此时仍由现有 variant validation 规则决定是否接受。

如果 Camera 随挖掘机移动，环境相对于 Camera 的画面会变化；如果 Camera 固定，挖掘机会在画面中移动。这属于配置和场景设计，不属于轨迹播放器错误。

## 19. 暂停录制产生的轨迹跳变

Recorder 支持暂停记录，并从 CSV 时间轴中排除暂停时间。当前 sidecar 只记录暂停次数，没有记录具体暂停边界。

如果挖掘机在暂停期间发生移动，恢复记录后的相邻 CSV 行可能在很短的 CSV 时间间隔内出现较大位置或旋转跳变。Semantic world 无法判断这是：

- 应当瞬移；
- 应当快速插值；
- 还是不同轨迹段之间的断点。

第一版可以将所有相邻行视为连续关键帧，并按线性位置 + SLERP 旋转插值，但应在文档和 manifest 中明确该限制。

若以后要求完全保存暂停段语义，Recorder 需要增加：

- `segment_id`；或
- `resume_boundary`；或
- sidecar 中的暂停前后样本索引。

## 20. 文件级修改清单

### 20.1 核心必须修改

| 文件 | 修改内容 |
|---|---|
| `excavator_joint_motion.py` | 新旧 CSV schema、根位姿关键帧、位置插值、SLERP、根状态命令/回读/误差、loop 闭合 |
| `articulation_adapter.py` | root world pose 读写、root velocity 清零、binding 信息 |
| `joint_control_profile.py` | profile schema、floating/root playback 契约、sidecar 兼容校验 |
| `articulation_stage_validator.py` | 强制浮动根、拒绝 FixedJoint、root body 和坐标单位检查 |
| `capture_launch_config.py` | `root_pose_playback` 配置结构与 schema 升级 |
| `simulation_orchestrator.py` | 传递配置、manifest、setup/pre-roll/root capture 对齐 |
| `validate_semantic_output.py` | 根位姿、误差、运动性和 variant 同步验证 |

### 20.2 配置和资产

| 文件/资产 | 修改内容 |
|---|---|
| 新 floating-base USD/USDA | 取消固定世界根，将 Root API 放到 root rigid body |
| 新 floating joint profile | 定义 root path、四关节路径、tolerance 和 metadata 契约 |
| 新 capture config | 指向 floating Stage、新 trajectory 和 root playback 配置 |
| isolated render configs | Prim 层级变化时更新路径 |
| semantic mapping | 仅当浮动 Stage 语义标签或路径发生变化时更新 |

### 20.3 通常无需核心修改

| 文件 | 原因 |
|---|---|
| `world_scheduler.py` | 已有精确 pre/post physics callback 和冻结机制 |
| `capture_context.py` | 已能携带嵌套 motion state |
| `semantic_dataset_writer.py` | 已将 CaptureContext 写入每帧 metadata |
| `scene_visibility_controller.py` | visibility 机制不依赖 world transform |

这些文件仍需增加或调整测试，并可能需要提升 metadata schema version。

## 21. 测试方案

### 21.1 纯 Python CSV 测试

- 旧五列 CSV 正常加载；
- 新十五列 CSV 正常加载；
- 错误列顺序被拒绝；
- 缺少部分根位姿列被拒绝；
- 非有限 position/quaternion 被拒绝；
- 零四元数被拒绝；
- 非单位四元数按容差归一化或拒绝；
- 时间不是从零开始时被拒绝；
- 时间不严格递增时被拒绝。

### 21.2 插值测试

- 四关节线性插值；
- 根位置线性插值；
- 四元数 SLERP；
- `q/-q` 等价；
- 跨越 `+179°/-179°` 时走最短路径；
- 相同四元数不产生数值异常；
- 关键帧时刻返回精确关键帧值。

### 21.3 Playback mode 测试

- `hold` 同时保持四关节与根位姿；
- `loop` 接受完整闭合轨迹；
- `loop` 拒绝关节不闭合；
- `loop` 拒绝根位置不闭合；
- `loop` 拒绝根旋转不闭合；
- `q/-q` 首尾仍视为旋转闭合。

### 21.4 Adapter Fake 测试

- root pose shape 正确；
- quaternion 使用 `wxyz`；
- quaternion 写入前归一化；
- root linear/angular velocity 被清零；
- 错误长度和非有限数被拒绝；
- binding/shutdown 状态正确；
- 四关节功能不回归。

### 21.5 Motion Scheduler 测试

- pre-step 同时提交四关节和 root pose；
- post-step 同时回读两类状态；
- 位置误差计算正确；
- 旋转角误差计算正确；
- `authoritative_pose` 必要时 reassert；
- `physics_accepted` 不执行 reassert；
- setup 和 pre-roll 保持 `t=0` 完整状态；
- get_state 输出完整且 JSON-safe。

### 21.6 Stage Validator 测试

- root playback 接受 floating rigid-body Articulation Root；
- root playback 拒绝 FixedJoint Root；
- 拒绝多个 Articulation Root；
- 拒绝缺少 RigidBodyAPI 的 root；
- 拒绝 kinematic root；
- 拒绝无效 mass/inertia；
- 保留现有四关节链测试。

### 21.7 Config 与 metadata 测试

- root playback 配置类型和枚举；
- 新 CSV + disabled 被拒绝；
- 旧 CSV + enabled 被拒绝；
- 新 CSV + fixed profile 被拒绝；
- 新 control mode 被接受；
- Recorder profile alias 正确匹配；
- quaternion order 错误被拒绝；
- root columns 与 CSV 不一致被拒绝；
- 新格式缺少 sidecar 被拒绝。

### 21.8 输出验证测试

- 根位姿字段完整；
- quaternion norm；
- commanded/readback/capture pose 一致性；
- root position/rotation movement detection；
- 三 variant 同帧状态一致；
- `hold` 末尾状态保持；
- static 模式拒绝 root movement。

### 21.9 Isaac Sim smoke test

必须在真实 floating Articulation Stage 上验证：

1. 仅四关节运动；
2. 仅 X/Y/Z 平移；
3. 仅根旋转；
4. 平移和旋转同时发生；
5. 四关节和根运动同时发生；
6. setup/pre-roll 后 frame 0 与 CSV `t=0` 一致；
7. Camera 随 root/关节运动时 world transform 正确；
8. 三个 variant 使用同一冻结位姿；
9. 长轨迹无 tensor invalid、NaN、约束爆炸或 Stage 污染；
10. 运行结束后离线验证通过。

## 22. 实施顺序

### 阶段一：USD 与 profile

1. 创建 floating-base Stage；
2. 确认只有一个 Articulation Root；
3. 新建 floating semantic profile；
4. 在 Isaac Sim 中手工验证 root world pose 可读写；
5. 验证四关节仍可直接写入。

### 阶段二：CSV 与插值

1. 定义新旧 schema；
2. 扩展关键帧和 sample 类型；
3. 实现位置线性插值；
4. 实现 quaternion SLERP；
5. 扩展 hold/loop；
6. 完成纯 Python 单元测试。

### 阶段三：Adapter 与 Motion Scheduler

1. 增加 root pose API；
2. 增加 root velocity 清零；
3. pre-step 同时写关节和根；
4. post-step 回读两类状态；
5. 实现 authoritative pose reassert；
6. 扩展 state 和 body transforms。

### 阶段四：配置、metadata 和 manifest

1. 升级 capture config schema；
2. 升级 joint profile schema；
3. 校验 Recorder sidecar；
4. 扩展 run manifest；
5. 更新 capture 示例配置。

### 阶段五：输出验证和真实运行

1. 扩展离线验证器；
2. 完成 Fake 和集成测试；
3. 执行 Isaac Sim smoke test；
4. 执行小帧数 semantic capture；
5. 验证三 variant 同步；
6. 再执行长轨迹正式采集。

## 23. 验收标准

实现完成后必须满足：

- 旧五列 CSV 与旧 fixed-base 采集不回归；
- 新十五列 CSV 被明确识别；
- 新 CSV 在 root playback 未启用时不会静默忽略根位姿；
- 新 CSV 只能在通过校验的 floating Articulation 上运行；
- frame 0 对应 CSV `t=0` 的四关节和根位姿；
- 每个 physics step 都按照 dataset time 采样四关节和根位姿；
- 根位置使用线性插值；
- 根旋转使用最短路径 SLERP；
- `hold` 同时保持四关节和根位姿；
- `loop` 同时检查四关节、根位置和根旋转闭合；
- 每帧输出 commanded、physics readback 和 capture root pose；
- capture root pose 与 CSV 采样值的误差不超过配置容差；
- full scene、excavator only、front teeth only 使用同一个冻结状态；
- root body world transform 能证明整体移动或旋转确实发生；
- Stage、mapping、visibility 和 frame transaction 现有校验继续通过；
- 最终 `validate_semantic_output.py` 能完整验证关节和整体根运动。

## 24. 第一版建议范围

为降低风险，第一版建议只实现：

- 旧五列与新十五列两种严格 CSV schema；
- floating-base Stage；
- `absolute_world` 坐标模式；
- 根位置 linear；
- 根旋转 SLERP；
- `authoritative_pose`；
- `hold` 为正式录制默认模式；
- 完整 sidecar 强校验；
- 根位姿 manifest、每帧 metadata 和离线验证。

第二版再考虑：

- `relative_to_initial`；
- 轨迹 segment/pause 边界；
- 速度和加速度合理性检查；
- 更物理化的 `physics_accepted` 根运动；
- 根位姿轨迹重定向和坐标校准工具。

上述范围可以先确保 semantic world 在不破坏现有 fixed-base 工作流的前提下，可靠读取 `JointPositionRecorder_zhanyang` 输出，并在离线语义采集过程中按照 CSV 完成挖掘机整体移动、旋转与四关节同步回放。
