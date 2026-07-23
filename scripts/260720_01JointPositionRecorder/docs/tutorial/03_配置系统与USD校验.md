# 03 配置系统与 USD 校验

## 1. 为什么把关节映射放进 JSON

控制算法只关心四个逻辑关节：

```text
cab, boom, small_arm, bucket
```

但不同 USD 可能使用不同 Prim 名和路径。若把 `/World/Joints/...` 写死在控制器里，每换一台挖掘机就要改 Python。Profile 把“通用控制逻辑”和“具体模型命名”分开：

```text
通用代码 + 某个 JSON Profile + 兼容 USD = 可运行控制面板
```

## 2. 默认 Profile 逐项解释

文件：`profiles/excavator_four_joint_default.json`

### 2.1 项目级字段

| 字段 | 默认值 | 作用 |
|---|---|---|
| `profile_name` | `four_joint_fixed_base_excavator` | 元数据和 GUI 中显示的配置名称 |
| `articulation_root_path` | `null` | 为 null 时自动发现唯一根；多个根时应明确填路径 |
| `require_fixed_base` | `true` | 拒绝把普通刚体当浮动 Articulation 根 |
| `arrival_tolerance_degrees` | `0.01` | 到达判定和规划器吸附容差，单位度 |
| `max_update_dt` | `0.05` | 单次控制推进允许使用的最大 `dt`，单位秒 |
| `default_csv_directory` | `trajectories` | 相对项目根目录的默认输出目录，也允许配置绝对目录 |
| `default_csv_filename` | `excavator_actual_angles.csv` | 默认 CSV 文件名，不允许夹带目录 |
| `joints` | 4 个对象 | 严格要求正好四个逻辑关节 |

如果 Stage 中有多个 Articulation Root，可以把字段改成类似：

```json
"articulation_root_path": "/World/Joints/world_track_fixed_joint"
```

这里应填**应用了 ArticulationRootAPI 的 Prim 路径**。默认设计中它是 FixedJoint，而不是底盘 Mesh 路径。

### 2.2 单关节字段

以 Cab 为例：

```json
{
  "logical_name": "cab",
  "display_name": "Cab",
  "candidate_names": ["track_operator_cab_joint"],
  "candidate_paths": ["/World/Joints/track_operator_cab_joint"],
  "default_speed_degrees": 8.0,
  "home_degrees": 0.0,
  "safety_margin_degrees": 2.0
}
```

| 字段 | 解释 |
|---|---|
| `logical_name` | Python 字典键、CSV 列名和稳定业务标识，四关节不能重复 |
| `display_name` | GUI 上给人看的名称 |
| `candidate_names` | 可接受的 RevoluteJoint Prim 名，可配置多个候选 |
| `candidate_paths` | 可接受的完整 Prim 路径，可为空 |
| `default_speed_degrees` | 面板初始速度，必须有限且大于 0 |
| `home_degrees` | Home 目标角，必须是有限数 |
| `safety_margin_degrees` | 在 USD 上下限两端各缩进多少度，必须非负 |

关节只要提供 `candidate_names` 或 `candidate_paths` 中至少一种即可。默认 Profile 两种都给，是为了既能快速按绝对路径命中，也能在关节被移动到别的父路径后按 Prim 名发现。

## 3. `config.py` 的强类型模型

Profile 不是读出一个随意的 `dict` 就直接使用，而是经过两层不可变 dataclass：

```text
JSON object
  └─ ProjectConfig
       └─ tuple[JointDefinition, JointDefinition, JointDefinition, JointDefinition]
```

### 3.1 `JointDefinition.from_dict()`

它完成：

- 必填键访问；
- 字符串去除首尾空白；
- 列表转成 tuple；
- 数值转成 float；
- 缺省值补齐；
- 调用 `validate()`。

校验内容包括：名称非空、至少有一种候选、候选项非空、三个数值有限、默认速度为正、安全边距非负。

### 3.2 `ProjectConfig.from_dict()`

项目级校验包括：

- Profile 名非空；
- `joints` 数量严格为 4；
- 四个 `logical_name` 唯一；
- 到达容差和最大 `dt` 都是有限正数；
- CSV 目录字符串非空；
- 默认 CSV 名只是文件名，不能是路径；
- 默认文件名必须以 `.csv` 结尾。

所有配置对象都是 `frozen=True`，创建后不能随意改字段。这能降低运行中配置被意外修改的风险。

### 3.3 `load_project_config()`

加载过程：

1. `expanduser()` 展开用户目录表示。
2. `resolve()` 得到绝对路径。
3. 要求文件存在。
4. 以 UTF-8 读取并用 `json.loads()` 解析。
5. 要求 JSON 根是对象。
6. 转成 `ProjectConfig` 并完整校验。

配置错误统一包装为 `ConfigurationError`，文件不存在仍使用更明确的 `FileNotFoundError`。

### 3.4 CSV 目录解析

```python
config.resolve_csv_directory(project_root)
```

- 若 Profile 配的是绝对目录，直接解析它；
- 若配的是 `trajectories` 这类相对目录，则以 `project_root` 为基准，而不是以当前终端工作目录为基准。

这避免了从不同工作目录启动时，输出文件位置发生漂移。

## 4. Profile 校验与 Stage 校验是两回事

```text
Profile 校验：配置自身有没有语法和逻辑问题
Stage 校验：当前打开的 USD 是否真的符合这份配置
运行时校验：PhysX 初始化后的 Articulation 是否正好有预期 DOF
```

例如，Profile 写了四个合法的候选名称，只能证明配置格式正确；这些名字在当前 USD 中是否存在，要由 `validate_stage()` 判断。

## 5. `validate_stage()` 的发现流程

`stage_validator.py` 的检查是只读的，不会为了通过检查而修改 USD。

### 5.1 收集 Prim

```python
prims = [prim for prim in stage.Traverse() if prim.IsValid()]
```

随后筛选带 `UsdPhysics.ArticulationRootAPI` 的根候选。

### 5.2 确定唯一 Articulation Root

- Profile 提供根路径：只检查该 Prim 是否有效且具有 ArticulationRootAPI。
- Profile 未提供且 Stage 只有一个根：自动使用。
- 没有根：`MISSING_ROOT`。
- 多个根：`AMBIGUOUS_ROOT`，要求在 Profile 中明确选择。

若根 Prim 是 FixedJoint：

- `physics:body0` 必须正好指向一个根刚体；
- 根关节必须 enabled。

若根 Prim 自身是刚体，代码可以识别这种浮动根形式，但默认 `require_fixed_base = true` 会报 `FLOATING_ROOT`。

### 5.3 解析四个逻辑关节

对每个 `JointDefinition`：

1. 逐个检查 `candidate_paths` 指向的 Prim 是否为 RevoluteJoint。
2. 遍历 Stage，查找 Prim 名出现在 `candidate_names` 中的 RevoluteJoint。
3. 用完整路径作为字典键去重。
4. 0 个结果报 `MISSING_JOINT`。
5. 多于 1 个结果报 `AMBIGUOUS_JOINT`。
6. 唯一结果写入 `report.joint_paths` 和 `report.dof_names`。

同一个关节同时被 candidate path 和 candidate name 命中不会算两个，因为完整路径相同会被去重。但如果场景里有两个同名 RevoluteJoint，依然会歧义；此时应减少候选名或只保留唯一绝对路径。

### 5.4 校验关节属性与安全限位

每个命中的 RevoluteJoint 必须：

- `physics:jointEnabled is True`；
- 未应用 `PhysicsDriveAPI:angular`；
- `body0` 和 `body1` 各有且仅有一个目标；
- 上下限能转成有限 float；
- 扣除安全边距后仍有非空范围。

安全范围公式：

```text
safe_lower = physics:lowerLimit + safety_margin_degrees
safe_upper = physics:upperLimit - safety_margin_degrees
```

默认设计中的结果：

| 关节 | USD 原始限位 | 两端边距 | GUI/Controller 可接受安全范围 |
|---|---:|---:|---:|
| Cab | `[-180, 180]` | 2° | `[-178, 178]` |
| Boom | `[-35, 70]` | 2° | `[-33, 68]` |
| Small arm | `[-80, 70]` | 2° | `[-78, 68]` |
| Bucket | `[-90, 80]` | 2° | `[-88, 78]` |

最终范围以实际打开的 Stage 属性为准。上表只是 `Sim_Fangshan_07` 设计值。

### 5.5 校验串联父子链

校验器从根刚体开始，按 Profile 中的四关节顺序检查：

```text
expected_parent = root_body
第 1 关节 body0 必须等于 expected_parent
把第 1 关节 body1 作为新的 expected_parent
重复四次
```

这样不仅要求四个关节“都存在”，还要求它们按 Cab → Boom → Small arm → Bucket 串成一条链。

如果某个 child 已经出现在先前的 body 列表中，则报 `CHAIN_CYCLE`，说明链出现回环。

### 5.6 校验五个刚体

根刚体加四个关节的 child，共五个 body。每个必须：

- Prim 存在；
- 具有 RigidBodyAPI；
- 具有 MassAPI；
- `physics:rigidBodyEnabled = true`；
- `physics:kinematicEnabled = false`；
- `physics:mass` 为有限正数；
- `physics:diagonalInertia` 三个分量都是有限正数。

底盘虽然固定，但固定性来自根 FixedJoint，不是来自 kinematic body。

## 6. 校验报告的数据结构

`StageValidationReport` 不只保存错误，还把后续运行需要的数据集中起来：

| 字段 | 内容 |
|---|---|
| `articulation_root_path` | Adapter 创建 Articulation wrapper 所需路径 |
| `root_body_path` | 固定根关节连接的底盘刚体 |
| `joint_paths` | 逻辑名 → RevoluteJoint 完整路径 |
| `dof_names` | 逻辑名 → 实际 DOF/Prim 名 |
| `body_paths` | 根到末端的五个刚体路径 |
| `limits_degrees` | 逻辑名 → `(safe_lower, safe_upper)` |
| `issues` | 所有 error/warning；当前实现实际只产生 error |

`report.ok` 的定义是“没有 error”。`require_valid()` 会把所有错误格式化后一次性抛出，而不是只报第一个问题。

## 7. 错误码速查

| 错误码 | 含义/优先检查位置 |
|---|---|
| `NO_STAGE` | 没有打开 USD Stage |
| `INVALID_ROOT_HINT` | Profile 指定根不存在或无 ArticulationRootAPI |
| `MISSING_ROOT` | Stage 中没有 Articulation Root |
| `AMBIGUOUS_ROOT` | 找到多个根，Profile 没指定 |
| `INVALID_FIXED_ROOT` | Fixed root 的 `body0` 不是唯一一个目标 |
| `ROOT_DISABLED` | 根 FixedJoint 未 enabled |
| `FLOATING_ROOT` | Profile 要求固定基座，但根是普通刚体 |
| `UNSUPPORTED_ROOT` | 根既不是 FixedJoint，也不是刚体 |
| `MISSING_JOINT` | 候选路径/名称找不到对应 RevoluteJoint |
| `AMBIGUOUS_JOINT` | 一个逻辑关节命中多个 RevoluteJoint |
| `JOINT_DISABLED` | 目标 RevoluteJoint 未 enabled |
| `DRIVE_CONFLICT` | 目标关节仍有 Angular Drive |
| `INVALID_BODY_RELATION` | `body0` 或 `body1` 不是唯一目标 |
| `MISSING_LIMIT` | 上下限缺失或不能转 float |
| `NONFINITE_LIMIT` | 限位是 NaN/Infinity |
| `INVALID_SAFE_RANGE` | 两端减去安全边距后没有可用范围 |
| `BROKEN_CHAIN` | 当前关节的 body0 不是上一 link |
| `CHAIN_CYCLE` | 某个 child body 重复出现，形成环 |
| `MISSING_BODY` | 关节关系引用的刚体 Prim 不存在 |
| `MISSING_RIGID_BODY_API` | link 没有 RigidBodyAPI |
| `MISSING_MASS_API` | link 没有 MassAPI |
| `BODY_DISABLED` | 刚体未 enabled |
| `KINEMATIC_BODY` | link 是 kinematic，违反当前 Articulation 约定 |
| `INVALID_MASS` | 质量非有限正数 |
| `INVALID_INERTIA` | 对角惯量不是三个有限正数 |

## 8. 给另一台四关节挖掘机制作 Profile

推荐复制默认文件，不直接覆盖：

```text
profiles/my_excavator.json
```

操作步骤：

1. 在 Isaac Sim Stage 面板中找到 Articulation Root Prim。
2. 若 Stage 有多个根，填写 `articulation_root_path`。
3. 沿实际父子链确认四个 RevoluteJoint 的顺序。
4. 为每个逻辑关节填写唯一 candidate path，必要时再加 candidate name。
5. 根据模型设置合理默认速度、Home 和安全边距。
6. 将 `entrypoints/show_panel.py` 的 `PROFILE_PATH` 指向新文件，或另建入口脚本。
7. 先运行 Stage 校验/Articulation smoke test，再使用 GUI 做小角度试运动。

不要只按视觉上的零件名称猜链路，要检查 `physics:body0` 和 `physics:body1` 关系。

## 9. 当前实现没有校验的设计项

原始设计文档还提出一些要求，但当前 `validate_stage()` 没有实际检查：

- Stage 是否存在有效 `PhysicsScene`；
- `upAxis` 是否为 Z；
- `metersPerUnit` 是否为 1；
- RevoluteJoint 的旋转轴是否为预期轴；
- 运行时限位是否与 USD 限位一致；
- 每个 DOF 的运行时类型是否明确为 Revolute。

此外，Stage 校验器只验证选中的四个关节；整个 Articulation 是否还有额外 DOF，要等 `IsaacArticulationAdapter.validate_runtime()` 用 `num_dofs == 4` 再把关。

这一区分很重要：设计文档描述的是目标契约，源码才代表当前实际执行的检查。

## 10. 下一步

Stage 校验通过后，真正决定“每帧写多少角度”的是 `ConstantSpeedPlanner`，而决定何时调用它的是 `MotionController`。下一章用具体数字推导这两部分。
