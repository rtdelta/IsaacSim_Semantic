# `Excavator_Fangshan_01.usda` 适配 JointPositionRecorder 修改方案

日期：2026-07-29  
文档状态：已实施并完成静态、运行时及 GUI 冒烟验证  
目标项目：`260720_01JointPositionRecorder`

## 1. 目标

使远端资产 `Excavator_Fangshan_01.usda` 能够作为固定基座、四自由度挖掘机 Articulation，运行 `260720_01JointPositionRecorder` 项目的直接关节位置控制和实际角度记录功能。

本方案只处理与 Recorder 运行直接相关的内容：

- Articulation Root；
- 四个 RevoluteJoint；
- Angular Drive；
- 五个刚体 link 的 kinematic、质量和惯量配置；
- Recorder profile 和启动入口；
- 静态校验、运行时校验和回退。

不处理以下内容：

- 资产、材质、纹理或外部引用缺失；
- 碰撞体精度优化；
- 真实挖掘机质量、质心和惯量标定；
- 原有 Drive 控制效果复现；
- 轨迹数据下载、统计或可视化；
- 与本次四关节记录无关的场景调整。

## 2. 相关远端文件

### 2.1 待适配资产

```text
/root/gpufree-data/stage_material_set/excavator_module_set/sim_Fangshan_01/Excavator_Fangshan_01.usda
```

只读分析时的文件信息：

```text
size=117939580
modified=2026-07-29 10:24:23.281324220 +0800
```

### 2.2 参考场景

```text
/root/gpufree-data/stage_material_set/excavator_module_set/sim_Fangshan_01/Sim_Fangshan_08.usda
```

只读分析时的文件信息：

```text
size=39997
modified=2026-07-20 17:36:38.522800769 +0800
```

### 2.3 Recorder 项目

```text
/root/gpufree-data/repositories/260720_01JointPositionRecorder
```

关键文件：

```text
README.md
entrypoints/show_panel.py
profiles/excavator_four_joint_default.json
src/joint_position_recorder/articulation_adapter.py
src/joint_position_recorder/config.py
src/joint_position_recorder/gui.py
src/joint_position_recorder/stage_validator.py
```

## 3. Recorder 的实际运行机制

Recorder 不依赖关节 Angular Drive。其运行方式是：

1. 根据 profile 解析唯一的 Articulation Root 和四个 RevoluteJoint；
2. 启动 Timeline 并等待 Articulation physics tensor 初始化；
3. 根据 DOF 名称而不是 USD 中的声明顺序获取四个 DOF 索引；
4. 每帧根据 `speed × dt` 计算下一个关节角；
5. 通过 Articulation API 一次性写入四个 DOF position；
6. 同时将四个 DOF velocity 写为零；
7. 从 Articulation 回读实际角度并写入 CSV。

因此，同一 DOF 上不能再存在 Angular Drive。否则 Drive 会持续施力，而 Recorder 又会直接写入位置，两种控制方式会冲突。

项目的静态校验器会把以下情况视为错误：

- 找不到配置指定的 Articulation Root；
- 固定根关节没有且仅有一个 `physics:body0`；
- 固定根关节未启用；
- 找不到、重复匹配或禁用了任何一个目标 RevoluteJoint；
- 目标关节应用了 `PhysicsDriveAPI:angular`；
- 关节没有唯一的 `body0` 和 `body1`；
- 关节限位缺失、非有限或安全边距后没有有效区间；
- 四个关节没有组成严格的单链父子关系；
- link 缺少 `PhysicsRigidBodyAPI` 或 `PhysicsMassAPI`；
- link 被禁用或为 kinematic；
- link 质量不为正数；
- link 对角惯量的任一分量不为正数。

运行时还会检查：

- Articulation physics tensor 已准备就绪；
- Articulation 的 DOF 数量恰好为 4；
- profile 中指定的四个 DOF 名称全部存在且唯一。

## 4. 两个 USDA 的关节对比

### 4.1 相同或等价的部分

两个文件都包含四个 RevoluteJoint，名称完全一致：

```text
track_operator_cab_joint
platform_boom_joint
boom_small_arm_joint
small_arm_bucket_joint
```

四个关节都使用：

```text
physics:axis = "X"
physics:collisionEnabled = false
```

关节限位也完全一致：

| 逻辑关节 | 关节名称 | 下限 | 上限 |
|---|---|---:|---:|
| Cab | `track_operator_cab_joint` | -180° | 180° |
| Boom | `platform_boom_joint` | -35° | 70° |
| Small arm | `boom_small_arm_joint` | -80° | 70° |
| Bucket | `small_arm_bucket_joint` | -90° | 80° |

两个文件中对应关节的 `physics:localPos0/1` 相同，`physics:localRot0/1` 只有约 `1e-18` 量级的浮点符号差异，对关节功能没有实际影响。

两者的运动链等价，只是刚体 prim 名称不同。

`Sim_Fangshan_08.usda`：

```text
track_mesh
→ operator_cab_mesh
→ boom_mesh
→ small_arm_mesh
→ bucket_only_full_teeth_mesh
```

`Excavator_Fangshan_01.usda`：

```text
track_prim
→ cab_prim
→ boom_prim
→ arm_prim
→ bucket_with_teeth_prim
```

因此不需要重新计算关节轴、joint frame、父子关系或限位。

### 4.2 Articulation Root 差异

`Sim_Fangshan_08.usda` 包含：

```text
/World/Joints/world_track_fixed_joint
```

该 prim：

- 类型为 `PhysicsFixedJoint`；
- 应用了 `PhysicsArticulationRootAPI`；
- `physics:body0` 指向底盘 link；
- `physics:jointEnabled = true`；
- 将底盘固定到世界坐标系。

`Excavator_Fangshan_01.usda` 当前：

- 没有 `PhysicsFixedJoint`；
- 没有 `PhysicsArticulationRootAPI`；
- 无法被 Recorder 解析为所需的固定基座 Articulation。

### 4.3 Angular Drive 差异

`Sim_Fangshan_08.usda` 的四个 RevoluteJoint 都没有 Angular Drive。

`Excavator_Fangshan_01.usda` 的四个 RevoluteJoint 全部应用：

```text
PhysicsDriveAPI:angular
```

共同参数：

```text
drive:angular:physics:type = "force"
drive:angular:physics:stiffness = 500000
drive:angular:physics:damping = 220000
drive:angular:physics:maxForce = 120000000
drive:angular:physics:targetVelocity = 0
```

目标位置：

| 关节 | `targetPosition` |
|---|---:|
| `track_operator_cab_joint` | -12.000001° |
| `platform_boom_joint` | -7.666667° |
| `boom_small_arm_joint` | -3.0000002° |
| `small_arm_bucket_joint` | -36.833336° |

Recorder 会直接拒绝任何仍应用 `PhysicsDriveAPI:angular` 的目标关节。仅把 stiffness、damping 或 maxForce 设置为零不能满足校验要求，必须从 composed applied schemas 中真正移除该 API。

### 4.4 `jointEnabled` 差异

`Sim_Fangshan_08.usda` 对固定关节和四个 RevoluteJoint 都显式写入：

```text
physics:jointEnabled = true
```

`Excavator_Fangshan_01.usda` 没有显式写入该属性。当前 Isaac Sim 安装中的 USD Physics schema 将其默认值定义为 `true`，所以这不是现阶段的直接阻塞项。

为避免以后由更强 layer 覆盖、人工误读或 schema 行为变化，适配层仍应显式写入 `physics:jointEnabled = true`。

## 5. 两个 USDA 的刚体差异

`Sim_Fangshan_08.usda` 的五个 link 均满足：

```text
PhysicsRigidBodyAPI
PhysicsMassAPI
physics:rigidBodyEnabled = true
physics:kinematicEnabled = false
physics:mass = 1
physics:diagonalInertia = (1, 1, 1)
```

`Excavator_Fangshan_01.usda` 的目标 link 当前状态：

| Link | RigidBodyAPI | MassAPI | kinematic |
|---|---|---|---|
| `track_prim` | 有 | 无 | `true` |
| `cab_prim` | 有 | 无 | `false` |
| `boom_prim` | 有 | 无 | `false` |
| `arm_prim` | 有 | 无 | `false` |
| `bucket_with_teeth_prim` | 有 | 无 | `false` |

当前五个 link 都没有显式的正质量和正对角惯量。即使 PhysX 在某些场景中能够根据碰撞体估算质量，Recorder 的校验器仍明确要求目标 link 应用 `PhysicsMassAPI` 并能读到正质量、正惯量。

## 6. 当前 profile 不匹配

Recorder 的默认入口固定加载：

```text
profiles/excavator_four_joint_default.json
```

当前 profile 名称为：

```text
combine_scene_02_four_joint_fixed_base
```

当前期望的根路径为：

```text
/Fangshan_Excavator_01/Joints/world_track_fixed_joint
```

当前候选关节名称为：

```text
track_cab_joint
platform_boom_joint
boom_arm_joint
arm_bucket_joint
```

目标资产实际名称为：

```text
track_operator_cab_joint
platform_boom_joint
boom_small_arm_joint
small_arm_bucket_joint
```

只有 `platform_boom_joint` 能按名称直接匹配。即使 USD 的物理配置全部调整完成，当前默认 profile 仍不能完整绑定目标资产。

项目本身已经支持多个 profile，因此优先为目标资产创建专用 profile，不应为了迎合旧 profile 而重命名目标关节。

## 7. 总体修改策略

### 7.1 推荐方案：兼容包装层

不直接重写 117,939,580 字节的原始 USDA，而是在同一目录新增一个轻量兼容场景：

```text
/root/gpufree-data/stage_material_set/excavator_module_set/sim_Fangshan_01/Excavator_Fangshan_01_JointRecorder.usda
```

兼容场景：

1. 引用原始 `Excavator_Fangshan_01.usda`；
2. 将默认 prim 组合到 `/Fangshan_Excavator_01`；
3. 通过更强 layer 的 override 移除 Angular Drive；
4. 新增固定根关节；
5. 覆盖五个 link 的 kinematic、Mass API、质量和惯量；
6. 在需要独立运行时提供 PhysicsScene。

优点：

- 原始大型资产不变；
- 不会破坏原有 Drive 控制用途；
- 修改内容体积小、容易审查；
- 可通过删除兼容文件完整回退；
- 能明确验证最终 composed Stage，而不是只检查源文件文本。

运行 Recorder 时应打开兼容场景，而不是直接打开原始 USDA。

### 7.2 备选方案：原位修改

如果业务明确要求必须直接打开原始文件名，则需要先创建可恢复备份，再对原始文件执行同样的物理修改。

原位修改的风险：

- 大型 ASCII USDA 重写成本高；
- 文本替换或保存中断可能损坏文件；
- 原有 Drive 控制行为会永久改变；
- 回滚、对比和审查成本更高。

在兼容包装层通过全部验收前，不采用原位修改。

## 8. 计划新增的兼容资产

### 8.1 兼容场景

```text
/root/gpufree-data/stage_material_set/excavator_module_set/sim_Fangshan_01/Excavator_Fangshan_01_JointRecorder.usda
```

推荐的顶层组合路径：

```text
/Fangshan_Excavator_01
```

引用关系：

```text
Excavator_Fangshan_01_JointRecorder.usda
└─ /Fangshan_Excavator_01
   └─ reference: ./Excavator_Fangshan_01.usda
```

### 8.2 专用 profile

```text
/root/gpufree-data/repositories/260720_01JointPositionRecorder/profiles/excavator_fangshan_01.json
```

### 8.3 专用启动入口

```text
/root/gpufree-data/repositories/260720_01JointPositionRecorder/entrypoints/show_panel_excavator_fangshan_01.py
```

保留当前默认 profile 和 `show_panel.py`，避免影响已有 `combine_scene_02` 工作流。

## 9. 兼容场景的详细修改规格

### 9.1 新增 PhysicsScene

若兼容场景用于独立打开，应包含一个有效的 `PhysicsScene`，例如：

```text
/PhysicsScene
```

基本要求：

```text
physics:gravityDirection = (0, 0, -1)
physics:gravityMagnitude = 9.81
```

五个目标 link 当前均禁用重力，因此重力数值不会替代 Articulation 配置。

如果未来将兼容资产引用到已经存在 PhysicsScene 的主 Stage，则不应在同一最终 Stage 中额外创建不必要的第二个 PhysicsScene。

### 9.2 新增固定 Articulation Root

新增 prim：

```text
/Fangshan_Excavator_01/Joints/world_track_fixed_joint
```

要求：

```text
类型：PhysicsFixedJoint
应用 API：PhysicsArticulationRootAPI
physics:body0：/Fangshan_Excavator_01/track_prim
physics:collisionEnabled：false
physics:jointEnabled：true
physics:localPos0：(0, 0, 0)
physics:localRot0：(1, 0, 0, 0)
```

不设置 `physics:body1`，表示将底盘固定到世界。

不得同时把 `PhysicsArticulationRootAPI` 应用到其它 link 或关节，确保 profile 指定的固定根关节是唯一目标根。

### 9.3 移除四个 Angular Drive

处理路径：

```text
/Fangshan_Excavator_01/Joints/track_operator_cab_joint
/Fangshan_Excavator_01/Joints/platform_boom_joint
/Fangshan_Excavator_01/Joints/boom_small_arm_joint
/Fangshan_Excavator_01/Joints/small_arm_bucket_joint
```

对每个关节：

1. 使用 USD list-op 从 composed `apiSchemas` 删除 `PhysicsDriveAPI:angular`；
2. 对六个 Drive 属性写入 value block 或以其它可验证方式清除强层意见：

```text
drive:angular:physics:damping
drive:angular:physics:maxForce
drive:angular:physics:stiffness
drive:angular:physics:targetPosition
drive:angular:physics:targetVelocity
drive:angular:physics:type
```

3. 显式覆盖：

```text
physics:jointEnabled = true
physics:collisionEnabled = false
```

4. 保留原有：

```text
physics:axis
physics:body0
physics:body1
physics:localPos0
physics:localPos1
physics:localRot0
physics:localRot1
physics:lowerLimit
physics:upperLimit
```

验收依据不是兼容层文本中出现了 `delete apiSchemas`，而是打开 composed Stage 后：

```python
"PhysicsDriveAPI:angular" not in prim.GetAppliedSchemas()
```

### 9.4 配置五个动态 link

处理路径：

```text
/Fangshan_Excavator_01/track_prim
/Fangshan_Excavator_01/cab_prim
/Fangshan_Excavator_01/boom_prim
/Fangshan_Excavator_01/arm_prim
/Fangshan_Excavator_01/bucket_with_teeth_prim
```

每个 link 应满足：

```text
PhysicsRigidBodyAPI
PhysicsMassAPI
physics:rigidBodyEnabled = true
physics:kinematicEnabled = false
physics:mass > 0
physics:diagonalInertia.x > 0
physics:diagonalInertia.y > 0
physics:diagonalInertia.z > 0
```

第一阶段采用与 `Sim_Fangshan_08.usda` 一致的兼容占位值：

```text
physics:centerOfMass = (0, 0, 0)
physics:diagonalInertia = (1, 1, 1)
physics:mass = 1
physics:principalAxes = (1, 0, 0, 0)
```

这些数值只用于直接关节状态控制，不代表真实机械动力学参数。将来启用碰撞力、真实重力、力矩控制或动力学仿真时，必须重新标定。

### 9.5 保持四关节运动链

最终 composed Stage 必须形成：

```text
World
└─ world_track_fixed_joint
   └─ track_prim
      └─ track_operator_cab_joint
         └─ cab_prim
            └─ platform_boom_joint
               └─ boom_prim
                  └─ boom_small_arm_joint
                     └─ arm_prim
                        └─ small_arm_bucket_joint
                           └─ bucket_with_teeth_prim
```

每个子 link 只能作为一个 enabled 关节的 `body1`，不得形成环或并行父节点。

## 10. 专用 profile 设计

计划文件：

```text
/root/gpufree-data/repositories/260720_01JointPositionRecorder/profiles/excavator_fangshan_01.json
```

建议内容：

```json
{
  "profile_name": "excavator_fangshan_01_four_joint_fixed_base",
  "articulation_root_path": "/Fangshan_Excavator_01/Joints/world_track_fixed_joint",
  "require_fixed_base": true,
  "arrival_tolerance_degrees": 0.01,
  "max_update_dt": 0.05,
  "default_csv_directory": "trajectories",
  "default_csv_filename": "excavator_fangshan_01_angles.csv",
  "joints": [
    {
      "logical_name": "cab",
      "display_name": "Cab",
      "candidate_names": ["track_operator_cab_joint"],
      "candidate_paths": [
        "/Fangshan_Excavator_01/Joints/track_operator_cab_joint"
      ],
      "default_speed_degrees": 8.0,
      "home_degrees": 0.0,
      "safety_margin_degrees": 2.0
    },
    {
      "logical_name": "boom",
      "display_name": "Boom",
      "candidate_names": ["platform_boom_joint"],
      "candidate_paths": [
        "/Fangshan_Excavator_01/Joints/platform_boom_joint"
      ],
      "default_speed_degrees": 5.0,
      "home_degrees": 0.0,
      "safety_margin_degrees": 2.0
    },
    {
      "logical_name": "small_arm",
      "display_name": "Small arm",
      "candidate_names": ["boom_small_arm_joint"],
      "candidate_paths": [
        "/Fangshan_Excavator_01/Joints/boom_small_arm_joint"
      ],
      "default_speed_degrees": 5.0,
      "home_degrees": 0.0,
      "safety_margin_degrees": 2.0
    },
    {
      "logical_name": "bucket",
      "display_name": "Bucket",
      "candidate_names": ["small_arm_bucket_joint"],
      "candidate_paths": [
        "/Fangshan_Excavator_01/Joints/small_arm_bucket_joint"
      ],
      "default_speed_degrees": 5.0,
      "home_degrees": 0.0,
      "safety_margin_degrees": 2.0
    }
  ]
}
```

应用 `2°` 安全边距后的可操作区间：

| 逻辑关节 | 原始限位 | Recorder 安全区间 |
|---|---:|---:|
| Cab | -180° ～ 180° | -178° ～ 178° |
| Boom | -35° ～ 70° | -33° ～ 68° |
| Small arm | -80° ～ 70° | -78° ～ 68° |
| Bucket | -90° ～ 80° | -88° ～ 78° |

四个 Home 角度均为 `0°`，位于安全区间内。

## 11. 专用启动入口设计

计划文件：

```text
/root/gpufree-data/repositories/260720_01JointPositionRecorder/entrypoints/show_panel_excavator_fangshan_01.py
```

该入口复用现有项目源码，只更换 profile 路径，不复制控制器代码。

建议逻辑：

```python
from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
PROFILE_PATH = PROJECT_ROOT / "profiles" / "excavator_fangshan_01.json"

source_text = str(SOURCE_ROOT)
if source_text not in sys.path:
    sys.path.insert(0, source_text)

from joint_position_recorder import load_project_config, show_recorder_window


config = load_project_config(PROFILE_PATH)
show_recorder_window(config, PROJECT_ROOT)
```

Isaac Sim Script Editor 中计划使用：

```python
import runpy

entrypoint = "/root/gpufree-data/repositories/260720_01JointPositionRecorder/entrypoints/show_panel_excavator_fangshan_01.py"
runpy.run_path(entrypoint, run_name="__main__")
```

## 12. 实施顺序

### 阶段 A：实施前保护

1. 重新验证 BatchMode SSH 公钥认证；
2. 记录原始 USDA 的：

```text
路径
大小
mtime
SHA-256
```

3. 确认本次采用兼容包装层，不修改原始文件；
4. 检查计划新增的兼容场景、profile 和入口路径不存在，避免覆盖已有文件；
5. 检查没有其它 Isaac Sim 或 Recorder 进程正在控制同一 Stage。

### 阶段 B：创建兼容资产

1. 创建轻量兼容 USDA；
2. 引用原始默认 prim；
3. 新增固定根关节；
4. 删除四个 composed Angular Drive；
5. 覆盖五个 link 的动态刚体和质量属性；
6. 根据独立运行需求创建 PhysicsScene；
7. 使用 USD 解析器打开并检查 composed 结果。

### 阶段 C：添加 Recorder 配置

1. 新增 `excavator_fangshan_01.json`；
2. 使用项目的配置加载器验证 JSON；
3. 新增专用启动入口；
4. 保持默认 profile 和默认入口不变。

### 阶段 D：静态 Stage 校验

调用项目 `validate_stage()` 并保存完整报告。期望：

```text
report.ok == True
report.articulation_root_path ==
  /Fangshan_Excavator_01/Joints/world_track_fixed_joint
len(report.joint_paths) == 4
len(report.dof_names) == 4
len(report.body_paths) == 5
```

不得出现：

```text
INVALID_ROOT_HINT
MISSING_ROOT
AMBIGUOUS_ROOT
INVALID_FIXED_ROOT
ROOT_DISABLED
MISSING_JOINT
AMBIGUOUS_JOINT
JOINT_DISABLED
DRIVE_CONFLICT
INVALID_BODY_RELATION
MISSING_LIMIT
NONFINITE_LIMIT
INVALID_SAFE_RANGE
BROKEN_CHAIN
CHAIN_CYCLE
MISSING_BODY
MISSING_RIGID_BODY_API
MISSING_MASS_API
BODY_DISABLED
KINEMATIC_BODY
INVALID_MASS
INVALID_INERTIA
```

### 阶段 E：Isaac Sim 运行时验证

按远端运行约束建立带 PTY 的完整交互式 SSH 会话，在同一会话中启动或操作 Isaac Sim，不使用非交互 SSH 命令直接启动 Kit。

运行时检查：

1. 打开 `Excavator_Fangshan_01_JointRecorder.usda`；
2. 执行专用入口；
3. GUI 自动绑定当前 Stage；
4. Timeline 正常启动；
5. Articulation physics tensor 有效；
6. `num_dofs == 4`；
7. 四个 DOF 名称分别为：

```text
track_operator_cab_joint
platform_boom_joint
boom_small_arm_joint
small_arm_bucket_joint
```

8. 面板状态显示：

```text
Ready: 4-DOF Articulation is initialized
```

### 阶段 F：低风险运动与记录测试

1. 确认没有其它控制器写入同一 Articulation；
2. 记录初始四关节角度；
3. 将目标设置为当前角度附近不超过约 `1°` 的安全值；
4. 使用低速执行一次 `Move all`；
5. 验证四关节均按 profile 顺序回读；
6. 使用新的、未占用的 CSV 文件名开始记录；
7. 记录少量帧后正常停止；
8. 检查 CSV 和 `.metadata.json`；
9. 将四关节恢复到初始角度；
10. 正常关闭面板和会话。

测试不得覆盖已有轨迹文件。

## 13. 验收标准

只有同时满足以下条件，才视为适配完成：

- 原始 `Excavator_Fangshan_01.usda` 的 SHA-256、大小和 mtime 未改变；
- 兼容场景可以由 USD 正常解析；
- composed Stage 中存在唯一目标固定 Articulation Root；
- 四个目标关节都是 enabled RevoluteJoint；
- 四个目标关节均不再应用 `PhysicsDriveAPI:angular`；
- 四个关节的轴、body0/body1、joint frame 和限位保持原值；
- 五个 link 都是 enabled、非 kinematic 的刚体；
- 五个 link 都应用 `PhysicsMassAPI`；
- 五个 link 的质量和三个惯量分量均为正数；
- 项目 `validate_stage()` 返回成功；
- Articulation 运行时恰好发现四个 DOF；
- Recorder GUI 进入 Ready 状态；
- 小角度运动能够执行并到达；
- CSV 中按 `cab,boom,small_arm,bucket` 顺序记录实际回读角度；
- 测试结束后恢复初始关节角度；
- 默认 profile、默认入口及已有轨迹文件未被破坏。

## 14. 风险与处理

### 14.1 Drive API 删除不彻底

风险：兼容层虽然阻断 Drive 属性，但 composed applied schemas 中仍存在 `PhysicsDriveAPI:angular`。

处理：

- 使用 USD API 检查 `GetAppliedSchemas()`；
- 以 composed Stage 为准，不以文本 grep 为唯一依据；
- 若 reference 上的 list-op 无法得到期望结果，调整兼容层强度或改用明确的更强 override；
- 未通过前不启动运动测试。

### 14.2 出现多个 Articulation Root

风险：上层 Stage 还应用了其它 Articulation Root，造成 profile 解析或 PhysX 拓扑冲突。

处理：

- profile 始终使用精确根路径；
- 检查目标链上只有一个根；
- 不在 link 上重复应用 `PhysicsArticulationRootAPI`。

### 14.3 多个 PhysicsScene

风险：兼容场景带 PhysicsScene，又被引用到已有 PhysicsScene 的主 Stage。

处理：

- 独立运行版和上层场景引用版分开管理；
- 最终 Stage 中优先使用一个明确的 PhysicsScene。

### 14.4 占位质量惯量不适合真实动力学

风险：`mass = 1` 和 `diagonalInertia = (1,1,1)` 只能保证数值有效，不能代表真实设备。

处理：

- 当前只用于 Recorder 的直接位置控制；
- 文档和文件注释明确标记为占位值；
- 以后启用真实动力学前重新标定。

### 14.5 旧 Drive 目标姿态不再自动维持

风险：移除 Drive 后，不再由原目标角主动施力维持姿态。

处理：

- Recorder 绑定后先同步当前实际角度；
- 目标输入默认同步为当前角度；
- 未点击 `Move all` 或 `Move home` 前不主动运动；
- 冒烟测试前记录初始角度，结束后恢复。

### 14.6 Profile 路径随引用位置变化

风险：若兼容资产被引用到不同 prim 路径，固定的 `articulation_root_path` 和 candidate paths 会失效。

处理：

- 本方案固定运行入口路径为 `/Fangshan_Excavator_01`；
- 若上层场景采用其它引用路径，为该组合场景建立独立 profile；
- 不依赖 USD 文件中的声明顺序推断 DOF。

## 15. 回退方案

采用兼容包装层时，原始 USDA 不变。回退步骤：

1. 关闭 Recorder 面板和 Isaac Sim Stage；
2. 停止使用专用入口；
3. 删除或移出以下新增文件：

```text
Excavator_Fangshan_01_JointRecorder.usda
profiles/excavator_fangshan_01.json
entrypoints/show_panel_excavator_fangshan_01.py
```

4. 重新打开原始 `Excavator_Fangshan_01.usda`；
5. 验证原始 SHA-256 与实施前记录一致。

兼容层方案不会要求恢复原始文件内容。

## 16. 最终预期结构

```text
PhysicsScene

Fangshan_Excavator_01
├─ track_prim
├─ cab_prim
├─ boom_prim
├─ arm_prim
├─ bucket_with_teeth_prim
└─ Joints
   ├─ world_track_fixed_joint
   │  └─ PhysicsArticulationRootAPI
   ├─ track_operator_cab_joint
   ├─ platform_boom_joint
   ├─ boom_small_arm_joint
   └─ small_arm_bucket_joint
```

四个 RevoluteJoint 均保持启用、有限限位和原有 joint frame，不应用 Angular Drive。五个 link 全部为非 kinematic、正质量、正惯量刚体。

## 17. 实际实施记录

实施时间：2026-07-29

用户确认目标文件已有备份，并明确授权直接修改目标 USDA。因此实际执行采用本文件第 7.2 节的“原位修改”分支，没有创建兼容包装层。

用户消息中的 `Fangshan_Excavator_01.usda` 在目标目录中不存在；经目录核对，实际修改的是此前持续分析的：

```text
/root/gpufree-data/stage_material_set/excavator_module_set/sim_Fangshan_01/Excavator_Fangshan_01.usda
```

### 17.1 USDA 实际改动

已在原始文件中完成：

- 新增 `/PhysicsScene`；
- 新增 `/excavator_prim/Joints/world_track_fixed_joint`；
- 在固定关节上应用 `PhysicsArticulationRootAPI`；
- 将固定关节 `body0` 指向 `/excavator_prim/track_prim`；
- 从四个 RevoluteJoint 移除 `PhysicsDriveAPI:angular`；
- 删除四个关节共 24 行 `drive:angular:*` 属性；
- 对固定关节和四个 RevoluteJoint 显式写入 `physics:jointEnabled = true`；
- 对五个 link 应用 `PhysicsMassAPI`；
- 将五个 link 全部设置为 `physics:kinematicEnabled = false`；
- 对五个 link 写入 `mass = 1` 和 `diagonalInertia = (1,1,1)`；
- 保留四个关节原有的 axis、body0/body1、joint frame 和限位。

修改前：

```text
size=117939580
sha256=34367e48562eb475e2f7c9e95c900094c9a4ef855e87436b68a544505edd1921
```

修改后：

```text
size=117939569
sha256=7ff743876fc0745a22d4271d2b59db907f4c4e5420aa5eb15056e20da843d2b9
owner=root:root
mode=644
```

修改采用同目录临时文件完整写入、校验后原子替换，未留下临时文件。

### 17.2 实际新增 Recorder 文件

专用 profile：

```text
/root/gpufree-data/repositories/260720_01JointPositionRecorder/profiles/excavator_fangshan_01.json
sha256=ba3dc6bdca271e013a10dac7f146830097afa6f5d1596cc8ccc7eacab7ce2202
```

专用入口：

```text
/root/gpufree-data/repositories/260720_01JointPositionRecorder/entrypoints/show_panel_excavator_fangshan_01.py
sha256=be5c96605a4b6fb27909e38322cfcb5d6094883644f2887e63c72a41b44e1023
```

因为本次直接打开原始 USDA，而不是把它引用到 `/Fangshan_Excavator_01`，实际 profile 使用：

```text
articulation_root_path=/excavator_prim/Joints/world_track_fixed_joint
```

四个实际 candidate path 也统一使用 `/excavator_prim/Joints` 前缀。默认 profile 和默认入口未被修改。

### 17.3 静态验证结果

使用 Isaac Sim 自带 USD Python 模块打开修改后的 Stage，并调用项目原生 `validate_stage()`。

结果：

```text
ok=True
errors=0
warnings=0
root=/excavator_prim/Joints/world_track_fixed_joint
root_body=/excavator_prim/track_prim
```

解析出的 link：

```text
/excavator_prim/track_prim
/excavator_prim/cab_prim
/excavator_prim/boom_prim
/excavator_prim/arm_prim
/excavator_prim/bucket_with_teeth_prim
```

解析出的安全限位：

```text
cab=(-178.0, 178.0)
boom=(-33.0, 68.0)
small_arm=(-78.0, 68.0)
bucket=(-88.0, 78.0)
```

### 17.4 Articulation 运行时验证

使用带 PTY 的完整交互式 SSH 登录环境启动 Isaac Sim headless SimulationApp。

运行时结果：

```text
num_dofs=4
ready_after_updates=1
initial_degrees=(0.0, 0.0, 0.0, 0.0)
commanded_degrees=(0.25, 0.25, 0.25, 0.25)
read_back_degrees=(0.2499999981, 0.2499999981, 0.2499999981, 0.2499999981)
restored_degrees=(0.0, 0.0, 0.0, 0.0)
result=PASS
```

日志：

```text
/root/gpufree-data/repositories/260720_01JointPositionRecorder/logs/isaac_articulation_smoke_excavator_fangshan_01_20260729_105750.log
```

### 17.5 GUI 入口验证

通过专用入口实际创建 `Articulation Joint Position Recorder` 面板。

验证内容：

- Stage 自动校验成功；
- Articulation physics tensor 初始化成功；
- 面板进入 `Ready: 4-DOF Articulation is initialized`；
- 四关节通过 GUI 控制链从 `0°` 移动到 `0.25°`；
- 四关节全部到达；
- 四关节恢复到 `0°`；
- 面板正常关闭。

结果：

```text
result=PASS
```

日志：

```text
/root/gpufree-data/repositories/260720_01JointPositionRecorder/logs/isaac_gui_smoke_excavator_fangshan_01_20260729_105855.log
```

两次运行时验证均出现 Isaac Sim experimental articulation API 的提示：

```text
DOF types mismatch:
USD=[Invalid, Invalid, Invalid, Invalid]
Physics tensor=[Rotation, Rotation, Rotation, Rotation]
```

该提示未影响项目行为：physics tensor 正确识别四个旋转 DOF，名称绑定、位置写入、回读、GUI 控制和恢复全部通过。当前 Recorder 源码也不把该提示作为失败条件。

### 17.6 副作用检查

- 未启动轨迹记录；
- 未创建或覆盖 CSV、metadata 或 partial 文件；
- 两次测试结束后四关节均恢复为 `0°`；
- Isaac Sim 正常关闭；
- PTY SSH 会话通过 `exit` 正常关闭；
- 没有残留 Isaac Sim、SimulationApp 或 GPU compute 进程。
