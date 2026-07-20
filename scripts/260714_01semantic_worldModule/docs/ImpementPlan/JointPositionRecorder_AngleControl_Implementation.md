# JointPositionRecorder 角度控制集成实现说明

更新时间：2026-07-20

## 1. 实现目标

本次更新将 `260714_01semantic_worldModule` 的四关节运动后端，从向 USD Angular Drive
持续写入 `targetPosition`，替换为与 `260720_01JointPositionRecorder` 一致的固定基座
Articulation 直接位置控制。

两项目共享以下外部数据合同，但语义相机项目保持自包含，不在运行时导入相邻项目：

- CSV 列顺序固定为 `time,cab,boom,small_arm,bucket`；
- CSV 中时间单位为秒、角度单位为度；
- Isaac Articulation API 内部使用弧度；
- 四个 DOF 按逻辑名称解析索引后一次性批量写入；
- 写位置时同步把四个 DOF 速度清零；
- 命令在物理步之前写入，实际位置在物理步之后读取；
- 录制器产生的非闭合轨迹默认使用 `hold`，不能无条件循环。

## 2. 运行生命周期

```text
解析 CLI、渲染配置、关节配置和 Recorder sidecar
  -> 打开并等待 USD 完成组合
  -> 通用 Stage preflight
  -> Articulation 专项 preflight（只读）
  -> 创建 Articulation wrapper，并按名称绑定 4 个 DOF
  -> 启动 Timeline
  -> 以有上限的 counted physics steps 等待 tensor ready
  -> 初始化运行时并读取一次实际角度
  -> 在 t=0 写入初始四关节位置，推进 1 个 setup physics step，再回读
  -> 可选 pre-roll，始终保持 t=0
  -> 建立 dataset time 原点
  -> 每个数据物理步：步前批量写入 -> physics step -> 步后批量回读
  -> 冻结 Timeline 并采集图像、语义和同一时刻的关节状态
```

bootstrap 和 setup 步都计入总物理步数，但位于 dataset time 原点之前，因此不会污染
训练数据的 `dataset_time`。它们的数量会写入 `run_config.json`，用于重现实验。

## 3. 新增模块

### `joint_control_profile.py`

读取并严格校验 `configs/excavator_four_joint_articulation.json`，内容包括：

- 固定基座 Articulation root 候选；
- 四个逻辑关节的候选 USD 路径和 DOF 名称；
- 每个关节的安全限位余量；
- 运行时实际角度回读容差；
- Recorder metadata sidecar 的单位、关节顺序、控制模式和 profile 兼容要求。

若同名 `.metadata.json` 存在但未完成、单位错误、关节顺序错误、控制方式不兼容或
profile 不匹配，采集会在启动 Isaac Sim 之前失败。没有 sidecar 的手写 CSV 仍允许使用。

### `articulation_stage_validator.py`

该模块只读取 USD，不修改资产。运动模式必须通过以下检查：

- 能唯一确定配置的 Articulation root；
- root 是启用的 FixedJoint，且能定位 root rigid body；
- 四个 RevoluteJoint 均存在、启用且唯一；
- 四个关节不存在 `PhysicsDriveAPI:angular`；
- 四关节的 body0/body1 构成单一、无环的五刚体链；
- limit 有限，扣除安全余量后仍有有效范围；
- 五个 link 均启用 RigidBodyAPI 和 MassAPI；
- link 显式为非 kinematic，质量与三个对角惯量均为正有限数。

Articulation 专项错误不会被 `--no-strict-stage` 绕过，因为直接控制在合同不完整时没有
安全、可解释的降级路径。

### `articulation_adapter.py`

适配器延迟导入 `isaacsim.core.experimental.prims.Articulation`，使普通 Python 可以加载
项目模块并运行单元测试。适配器负责：

- Timeline 启动前创建 wrapper；
- 按名称得到稳定 DOF index，避免依赖 USD 遍历顺序；
- Timeline 启动后确认 physics tensor entity ready；
- 确认 Articulation 恰好包含四个目标 DOF；
- 度/弧度转换；
- 以形状 `(1, 4)` 批量写位置和零速度；
- 以逻辑顺序批量读取四个实际位置；
- 将 root、DOF 名、index 和 ready 状态写入 manifest。

## 4. 已修改模块

### `excavator_joint_motion.py`

保留原 CSV 加载、SHA-256、严格递增时间、线性插值、`loop/hold` 采样和安全限位检查，
删除运行时 Angular Drive 写入逻辑，改为：

- `bind()`：静态合同校验和 Articulation 名称绑定；
- `initialize_runtime()`：tensor ready 后验证并读取初始实际角度；
- `before_physics_step(t)`：采样轨迹并提交四 DOF 命令；
- `after_physics_step(t)`：读取实际角度、计算 `actual - commanded`；
- `get_state()`：输出命令、实际位置、误差、轨迹时间和刚体世界变换。

每帧状态新增：

```json
{
  "control_mode": "articulation_direct_position",
  "commanded_degrees": {},
  "actual_degrees": {},
  "position_error_degrees": {},
  "target_degrees": {}
}
```

`target_degrees` 暂时作为向后兼容别名保留，值必须与 `commanded_degrees` 完全一致。

### `world_scheduler.py`

`advance_exact_steps()` 增加物理步前、步后回调，执行顺序固定为：

```text
world attributes -> before hook -> SimulationApp.update -> step count + 1 -> after hook
```

新增 `bootstrap_until()`，将等待 physics tensor 的每次 `SimulationApp.update()` 纳入
物理步计数，并在达到 CLI 配置的上限后明确失败，避免无限等待。

### `simulation_orchestrator.py`

新增 CLI：

- `--joint-profile`；
- `--articulation-ready-timeout-steps`。

`--trajectory-mode` 默认值由 `loop` 改为 `hold`。运行清单升级为 schema v3，并新增：

- 关节 profile 路径与 SHA-256；
- Recorder sidecar 内容；
- Articulation preflight 报告；
- bootstrap/setup 物理步数；
- root、joint path、DOF name/index 和 adapter ready 状态；
- 命令范围、实际安全限位和运行控制模式。

### `validate_semantic_output.py`

schema v1/v2 兼容逻辑保留。对 schema v3 的运动输出新增强制校验：

- 控制模式必须为 `articulation_direct_position`；
- profile 的逻辑关节顺序和回读容差有效；
- Articulation preflight 必须通过；
- adapter 必须记录为 bound 且 ready；
- adapter DOF 顺序必须与静态发现结果一致；
- bootstrap 非负且 setup 恰好为一个物理步；
- 每帧 command/actual/error/legacy target 都恰好包含四个关节且数值有限；
- `error == actual - commanded`；
- command 和 actual 均在安全限位内；
- 每个实际位置误差不超过 profile 容差。

## 5. Sim_Fangshan_07 默认配置

运动模式默认改用：

```text
USD overlay: configs/Sim_Fangshan_07_capture_overlay.usda
source USD:  /root/gpufree-data/wyb/StageMaterial02/Sim_Fangshan_07.usda
mapping:     configs/semantic_mapping_Sim_Fangshan_07_native.json
camera:      /root/Xform/operator_cab_mesh/Camera_01
profile:     configs/excavator_four_joint_articulation.json
```

07 的原生标签为 `arm`、`boom`、`bucket_noteeth`、`cab`、`track` 和
`tooth_1` 至 `tooth_5`。新 mapping 使用这些精确名称，未沿用 02 mapping 中的
`tooth_01` 至 `tooth_05`。

2026-07-20 的远端短测还确认，07 源文件引用的
`StageMaterial02/textures/color_121212.hdr` 当前不存在。后续评审策略将缺失图片、纹理和
环境贴图归类为 `RENDER_ASSET_UNRESOLVED` warning：问题仍写入 manifest，但不会阻碍严格
采集。缺失 USD composition layer、未知类型依赖、相机、语义和 Articulation 合同错误仍然
阻断运行。本次实现没有修改源 USD 或伪造 HDR 资产。

## 6. 使用示例

```bash
./run_capture_remote.sh \
  --renderer RealTimePathTracing \
  --trajectory /absolute/path/excavator_actual_angles.csv \
  --trajectory-mode hold \
  --frames 50 \
  --physics-hz 60 \
  --capture-fps 10 \
  --output /new/output/path
```

若确实要循环，必须保证 CSV 最后一行的四个角度与第一行相同，然后显式传入：

```bash
--trajectory-mode loop
```

## 7. 失败策略

以下问题均在写出正式数据前或当帧采集前直接终止：

- USD 仍包含 Angular Drive；
- Articulation root、DOF 或刚体链不符合 profile；
- Recorder sidecar 不兼容；
- CSV 目标超出扣除 margin 后的安全限位；
- 非闭合轨迹错误选择 `loop`；
- physics tensor 在限定步数内未 ready；
- DOF 名称到 index 的绑定不完整或重复；
- 物理步后实际角度与命令角度超差。

失败时 `run_config.json` 状态为 `failed` 并保存异常类型与消息；该输出不得作为生产数据。
