# 斗齿前侧语义采集与后处理更新实现方案

## 1. 文档目的

本文档是本次功能更新的独立实现方案，不复用或修改 `ImpementPlan` 文件夹内的旧方案文档。

本次更新包含三个核心目标：

1. 在 Semantic World Module 中新增 `front_teeth_only` 采集步骤，只保留用户明确提供的五个斗齿前侧 Prim 及其子层级。
2. 在 Post Process Chain V02 中增加基于 4 邻域的最小连通区域过滤，并使用清理后的 `front_teeth_only` 语义图替代原来的 `excavator_only` 语义图参与像素统计。
3. 将“单齿模型整帧删除阈值”和“碰撞模型整帧删除阈值”分别参数化，二者互不共用。

本方案只描述后续实现内容；当前阶段不修改业务代码、不启动采集、不运行后处理。

## 2. 已确认的固定决策

### 2.1 五个斗齿前侧 Prim path

以下路径由用户精确提供，代码和配置不得根据名称、语义标签或层级关系猜测、补全或替换：

```text
/Fangshan_Excavator_01/bucket_with_teeth_prim/tooth_01_front_3DGS
/Fangshan_Excavator_01/bucket_with_teeth_prim/tooth_02_front_3DGS
/Fangshan_Excavator_01/bucket_with_teeth_prim/tooth_03_front_3DGS
/Fangshan_Excavator_01/bucket_with_teeth_prim/tooth_04_front_3DGS
/Fangshan_Excavator_01/bucket_with_teeth_prim/tooth_05_front_3DGS
```

### 2.2 连通区域规则

- 邻接方式固定为 4 邻域，即只把上、下、左、右相邻的同标签像素视为连通。
- 对角线接触的两个像素不属于同一个连通区域。
- 最小连通区域像素数默认为 `5`。
- 像素数小于 `5` 的连通区域删除；像素数等于或大于 `5` 的连通区域保留。
- 同一个语义标签可以保留多个合格连通区域，不采用“只保留最大区域”的策略。
- 不同 semantic label 的像素必须分别计算，不能跨标签连接。

### 2.3 整帧删除规则

- 单独斗齿模型的不合格斗齿数量阈值默认为 `3`。
- 碰撞模型的不合格斗齿数量阈值默认为 `3`。
- 两个阈值必须是两个独立配置参数，允许以后分别调整。
- 判断采用“大于或等于阈值”，即默认情况下不合格斗齿达到 `3` 个便触发相应的整帧删除。
- 统计基数固定为五颗物理斗齿；某颗斗齿在完整场景中没有有效像素时，该斗齿记为不合格。

### 2.4 高宽比方向

- 参数名继续表达“高宽比”，但实际哪个图像轴作为高、哪个轴作为宽由配置指定。
- 默认模式为 `x_over_y`。
- `x_over_y` 表示：把检测框的 x 方向长度作为分子，把 y 方向长度作为分母，计算 `x方向长度 / y方向长度`。
- 高宽比必须使用清理后的完整场景目标像素所生成的最终 YOLO 轴对齐框计算，不能再使用参考旋转框计算。

### 2.5 semantic runtime ID

- `save_runtime_ids` 的默认值设为 `false`。
- 默认不把原始 runtime semantic ID 数组写入磁盘。
- Isaac Sim Writer 内部仍允许临时取得 runtime ID，并依据 `idToLabels` 和 `semantic_mapping.json` 将其转换成稳定的 semantic ID；因此关闭的是“runtime ID 文件产出”，不是删除内部映射过程。
- 稳定 semantic ID 图仍然正常保存，并继续作为后处理输入。

## 3. 祖先 Prim、目标 Prim 和子层级的渲染边界

### 3.1 当前隔离算法的实际行为

对每一个用户提供的目标 Prim path，隔离渲染需要同时保持以下对象可见：

1. 目标 Prim 本身。
2. 目标 Prim 的全部子孙 Prim。
3. 从 USD Stage 根节点到目标 Prim 之间的祖先 Prim。
4. 为完成渲染而保护的相机等基础设施 Prim。

目标路径之外的兄弟分支以及其他不相关的可渲染子树会被设为不可见。

### 3.2 祖先会不会出现在画面中

祖先 Prim 必须保持 `visible`，否则 USD 的继承可见性会使目标斗齿及其子层级也不可见。但祖先是否产生画面像素取决于祖先自身类型：

- 如果祖先只是 `Xform`、`Scope` 或其他仅用于组织层级/变换的 Prim，它自身没有几何表面，因此不会产生画面像素。
- 如果祖先 Prim 自身就是带几何的 `Mesh`、`BasisCurves` 或其他可渲染对象，它自身的几何也可能被渲染。
- 保留祖先不会自动保留祖先下面的所有兄弟分支；没有被选中的兄弟分支仍会单独隐藏。

因此，本方案中的“只包含五个前侧模型”准确含义是：保留五个目标 Prim 的完整子树，同时保留让这些子树正常生效所必需的祖先层级。代码不会把 `/Fangshan_Excavator_01` 或 `bucket_with_teeth_prim` 当成额外的包含根，从而不会因为祖先路径而自动放开整个挖掘机或整个 bucket 子树。

### 3.3 不增加业务内容校验

按照已确认要求，采集链路不检查 front-only 图像中是否只出现五种 semantic ID，也不要求每一帧必须同时出现五颗斗齿。默认信任用户提供的 Prim path 和既有采集链路。

仍保留程序运行所必需的结构性检查，例如：配置格式合法、Prim path 在 Stage 中存在、输出文件能够写入、帧号与图像尺寸一致。这些检查不推断 Prim path，也不分析 front-only 图像的业务内容。

## 4. Prim path 独立配置文件

新增独立配置文件：

```text
configs/front_teeth_only_render_prims.json
```

建议沿用现有 `IsolatedRenderConfig` 的严格格式：

```json
{
  "schema_version": 1,
  "render_prim_paths": [
    "/Fangshan_Excavator_01/bucket_with_teeth_prim/tooth_01_front_3DGS",
    "/Fangshan_Excavator_01/bucket_with_teeth_prim/tooth_02_front_3DGS",
    "/Fangshan_Excavator_01/bucket_with_teeth_prim/tooth_03_front_3DGS",
    "/Fangshan_Excavator_01/bucket_with_teeth_prim/tooth_04_front_3DGS",
    "/Fangshan_Excavator_01/bucket_with_teeth_prim/tooth_05_front_3DGS"
  ]
}
```

该文件只存储允许渲染的物体 Prim path，不混入输出路径、阈值、相机参数或后处理参数。后续修改斗齿模型路径时，只需修改这一模块化配置文件。

## 5. Semantic World Module 更新方案

### 5.1 采集变体

在现有两个采集变体之外新增：

```text
FULL_SCENE
EXCAVATOR_ONLY
FRONT_TEETH_ONLY
```

`FRONT_TEETH_ONLY` 的字符串值为：

```text
front_teeth_only
```

### 5.2 单帧采集顺序

每个轨迹帧按以下顺序完成三次渲染：

```text
冻结物理状态与相机状态
  -> full_scene
  -> excavator_only
  -> front_teeth_only
恢复可见性
  -> 进入下一仿真帧
```

三次渲染必须复用完全相同的：

- 仿真时间；
- 关节状态；
- 相机位置和姿态；
- 相机内参；
- 输出帧编号。

在每次切换可见性之后重置渲染历史，避免 Path Tracing 的历史缓存把前一个变体的内容残留到下一个变体。

### 5.3 front-only 可见性控制器

为 `front_teeth_only` 建立独立的 `SceneVisibilityController` 实例：

- `included_prim_paths` 只读取 `front_teeth_only_render_prims.json` 中的五个精确路径。
- `protected_prim_paths` 保留相机等渲染基础设施。
- 不把 bucket、boom、arm、cab、track、环境几何或其他语义模型加入允许列表。
- 每次 front-only 捕获结束后，在 `finally` 路径恢复本次临时可见性覆盖，防止影响下一帧或退出后的 Stage 状态。

为了避免匿名层名称继续绑定旧语义，控制器内部的临时可见性层名称应从固定的 `excavator_only_visibility.usda` 改为可按变体区分，例如：

```text
excavator_only_visibility.usda
front_teeth_only_visibility.usda
```

### 5.4 主采集配置扩展

主配置增加独立的 front-only 配置段：

```json
{
  "front_teeth_only_capture": {
    "enabled": true,
    "render_prim_paths_config": "front_teeth_only_render_prims.json",
    "save_rgb": false
  },
  "save_runtime_ids": false
}
```

配置含义：

- `enabled=true`：启用第三次采集。
- `render_prim_paths_config`：引用独立的五个 Prim path 配置文件。
- `save_rgb=false`：front-only 默认只为后处理提供语义数据，不额外保存 RGB。
- `save_runtime_ids=false`：所有采集变体默认都不把 runtime ID 数组写入磁盘。

主采集配置 schema 需要升级，并保持严格字段检查；新旧 schema 不应静默混用。

### 5.5 输出目录

在每次完整采集的输出根目录下新增：

```text
front_teeth_only_semantic/
  semantic_id/
    semantic_id_0000.npy
    ...
  semantic_color/
    semantic_color_0000.png
    ...

metadata/
  front_teeth_only/
    frame_0000.json
    ...
```

front-only 默认不产生：

```text
front_teeth_only_rgb/
semantic_runtime_id_*.npy
```

现有 `full_scene` 和 `excavator_only` 输出继续保留。`excavator_only` 不再作为新后处理像素统计的参考输入，但可以保留作人工排查和历史兼容。

### 5.6 Writer 与回执

- `CaptureVariant` 增加 `FRONT_TEETH_ONLY`。
- Writer 的输出根映射增加 front-only semantic ID、semantic color 和 metadata。
- RGB 写入从全局开关细化为按变体决定，允许 full-scene 和 excavator-only 保存 RGB、front-only 不保存 RGB。
- `CaptureReceipt.rgb_path` 继续允许为空。
- runtime ID 仍可被 Writer 临时读取并映射，但只有显式把 `save_runtime_ids` 改为 `true` 时才写文件。
- Writer、运行清单和配置 schema 版本同步升级，避免旧缓存或旧验证器误判新目录。

## 6. Post Process Chain V02 更新方案

### 6.1 参考语义输入替换

后处理不再把配置字段绑定到 `excavator_only` 这一具体名称，改成通用参考输入：

```json
{
  "inputs": {
    "full_scene": {
      "rgb_dir": "<full_scene_rgb目录>",
      "semantic_dir": "<full_scene_semantic/semantic_id目录>"
    },
    "reference": {
      "capture_variant": "front_teeth_only",
      "semantic_dir": "<front_teeth_only_semantic/semantic_id目录>"
    }
  }
}
```

每帧必须按相同帧号配对：

```text
full_scene RGB
+ full_scene semantic ID
+ front_teeth_only semantic ID
```

旧采集目录没有 `front_teeth_only` 数据，不能直接用于新逻辑。实现完成后必须重新复用原轨迹采集，才能运行采用新参考数据的后处理。

### 6.2 最小连通区域配置

后处理配置新增：

```json
{
  "component_filter": {
    "enabled": true,
    "connectivity": 4,
    "minimum_connected_component_pixels": 5
  }
}
```

处理顺序如下：

1. 加载 semantic ID 图。
2. 按每个目标 semantic label 分别生成二值 mask。
3. 对每个 mask 运行 4 邻域连通区域分析。
4. 删除像素数小于 `minimum_connected_component_pixels` 的区域。
5. 合并该标签剩余的全部合格区域。
6. 使用清理后的 mask 进入后续统计和框生成。

该步骤同时应用于：

- `full_scene` semantic ID；
- `front_teeth_only` semantic ID。

原始 `.npy` 文件只读，不在原位置覆盖。

### 6.3 清理后数据的统一用途

所有后续几何和阈值计算统一使用清理后的 mask，包括：

- 完整场景目标像素数；
- front-only 参考像素数；
- 可见比例；
- 参考旋转框及其填充比例；
- 单齿 YOLO 轴对齐框；
- YOLO 框的 x、y 方向长度；
- 高宽比；
- 碰撞模型的完整场景边界与参考边界；
- 单齿和碰撞模型的不合格斗齿计数。

建议在报告中同时保留原始像素数和清理后像素数，以便知道多少噪声像素被移除，但不改变原始采集文件。

### 6.4 单齿判定及整帧删除

单颗斗齿满足以下任一条件便记为“单齿模型不合格”：

- 完整场景中目标像素缺失，或连通区域过滤后没有有效像素；
- 单颗斗齿可见比例小于阈值 `a`；
- 参考旋转框填充比例小于阈值 `c`；
- 按 `height_width_axis_mode` 计算的高宽比小于阈值 `d`；
- 框尺寸或比值无效。

配置增加：

```json
{
  "single_tooth": {
    "minimum_visible_ratio_a": 0.55,
    "minimum_reference_fill_ratio_c": 0.45,
    "height_width_axis_mode": "x_over_y",
    "minimum_height_width_ratio_d": 1.25,
    "drop_all_single_boxes_if_bad_teeth_at_least": 3
  }
}
```

当一帧的 `single_bad_tooth_count >= 3` 时：

- 该帧五颗斗齿的单独模型标注全部不输出；
- 即使其中一颗或两颗本来通过单齿条件，也随该帧一起删除；
- 不影响碰撞模型使用其自己的独立计数规则。

### 6.5 碰撞模型判定及整帧删除

每颗物理斗齿按碰撞模型规则独立判断。满足以下任一条件便计入 `collision_bad_tooth_count`：

- 完整场景中目标像素缺失，或清理后无有效像素；
- 可见比例小于碰撞模型阈值 `b`；
- 参考旋转框填充比例小于阈值 `c`；
- 高宽比小于阈值 `d`；
- 框尺寸或比值无效。

配置增加：

```json
{
  "collision_model": {
    "minimum_visible_ratio_b": 0.55,
    "drop_collision_box_if_bad_teeth_at_least": 3
  }
}
```

当一帧的 `collision_bad_tooth_count >= 3` 时，该帧碰撞模型标注不输出。该阈值不读取也不复用 `drop_all_single_boxes_if_bad_teeth_at_least`。

原有的：

```text
drop_if_low_visibility_teeth_at_least
drop_if_bad_pose_teeth_at_least
```

不再直接决定碰撞模型是否删除。旧的遮挡数量和姿态数量可以保留为报告诊断字段，但最终删除动作只使用新的统一 `collision_bad_tooth_count` 规则。

## 7. 报告、缓存与版本管理

### 7.1 建议新增的报告字段

每颗斗齿记录：

```text
full_raw_pixel_count
full_clean_pixel_count
full_removed_component_count
full_removed_pixel_count
reference_raw_pixel_count
reference_clean_pixel_count
reference_removed_component_count
reference_removed_pixel_count
box_x_length
box_y_length
height_width_axis_mode
height_width_ratio
single_tooth_bad
collision_tooth_bad
```

每帧记录：

```text
single_bad_tooth_count
single_bad_tooth_limit
drop_all_single_boxes
collision_bad_tooth_count
collision_bad_tooth_limit
drop_collision_box
reference_capture_variant=front_teeth_only
```

建议使用明确原因码：

```text
frame_single_bad_tooth_limit_reached
frame_collision_bad_tooth_limit_reached
```

### 7.2 缓存失效

本次更新改变像素 mask、参考数据来源、检测框和判定规则，因此不能复用旧特征缓存。分析指纹至少加入：

- `reference.capture_variant`；
- front-only semantic 目录和文件指纹；
- `component_filter.enabled`；
- `connectivity`；
- `minimum_connected_component_pixels`；
- 两个独立的不合格斗齿数量阈值；
- 高宽比方向和阈值。

同步提升 Post Process Chain 的 cache schema 与 pipeline version，使旧缓存明确失效，而不是静默得到旧结果。

## 8. 实施顺序

1. 扩展 Semantic World Module 配置 schema，新增 front-only 配置段和输出目录字段，并将 `save_runtime_ids` 默认行为确定为 `false`。
2. 新建 `front_teeth_only_render_prims.json`，原样写入本文档中的五个路径。
3. 扩展 `CaptureVariant`、Writer、CaptureReceipt 和 manifest，使第三种语义采集能够写入独立目录且默认不写 RGB/runtime ID。
4. 将可见性控制器支持的临时层名称参数化，为 `excavator_only` 与 `front_teeth_only` 分别建立控制器。
5. 在仿真编排器中加入同一冻结帧内的第三次渲染，并确保异常路径也恢复可见性。
6. 扩展 Semantic World Module 的配置、Writer、帧配对和可见性单元测试。
7. 修改 Post Process Chain 输入配置，从 `excavator_only` 专用字段迁移到 `reference.capture_variant=front_teeth_only`。
8. 实现按 semantic label、4 邻域、最小 5 像素的连通区域过滤。
9. 确保所有像素统计、YOLO 框、填充比例和高宽比使用清理后的 mask。
10. 实现单齿模型与碰撞模型两个互相独立的整帧不合格数量阈值。
11. 扩展报告字段，更新缓存指纹并提升缓存/pipeline schema 版本。
12. 完成本地单元测试后部署到远端；先运行少量帧验证程序链路，再按用户指令决定是否运行完整轨迹采集和后处理。

## 9. 测试范围

### 9.1 连通区域单元测试

- 1、2、3、4 像素区域被删除。
- 恰好 5 像素区域被保留。
- 大于 5 像素区域被保留。
- 只在对角线接触的区域在 4 邻域下保持分离。
- 同标签的多个合格区域全部保留。
- 不同标签即使相邻也不互相连接。
- 清理后为空时正确标记为目标缺失/无有效框。
- 原始像素数等于保留像素数与删除像素数之和。

### 9.2 判定规则单元测试

- 单齿不合格数小于、等于和大于阈值时的行为。
- 碰撞模型不合格数小于、等于和大于阈值时的行为。
- 修改其中一个阈值不会影响另一个阈值。
- 单齿整帧删除时，原本合格的单齿框也不输出。
- `x_over_y` 确实计算 `x方向长度 / y方向长度`。
- 高宽比使用最终 YOLO 源框，不使用参考旋转框。

### 9.3 采集链路测试

- 同一帧三个变体使用相同帧号、相机和冻结的物理状态。
- front-only 的 CaptureReceipt 没有 RGB 路径，但有 semantic ID、semantic color 和 metadata 路径。
- `save_runtime_ids=false` 时三个变体均不写 runtime ID 文件。
- 可见性控制器退出或异常后恢复 Stage 可见性状态。
- 不增加“front-only 图中只能出现指定 semantic ID”或“五颗斗齿每帧必须齐全”的业务内容校验。

## 10. 实施完成后的数据链路

```text
同一冻结仿真帧
  ├─ full_scene
  │    ├─ RGB：最终数据集图像来源
  │    └─ semantic ID：目标实际可见像素、YOLO 框和高宽比来源
  ├─ excavator_only
  │    └─ 保留用于人工排查，不再参与新像素比例计算
  └─ front_teeth_only
       └─ semantic ID：参考像素、参考旋转框和填充比例来源

full_scene semantic ID ─┐
                        ├─ 逐标签 4 邻域、最小 5 像素清理
front_teeth_only ID ────┘
                        ├─ 单齿可见比例/填充比例/YOLO框高宽比
                        ├─ 单齿不合格数达到独立阈值 -> 删除全帧单齿框
                        └─ 碰撞不合格数达到独立阈值 -> 删除该帧碰撞框
```

## 11. 当前方案结论

- 五个 Prim path 已经明确，可直接写入独立配置，无需继续猜测路径。
- 每个目标 Prim 及其全部子层级会参与 front-only 渲染。
- 祖先层级保持可见只是为了维持 USD 层级和继承可见性；普通无几何祖先不会产生像素，带几何祖先理论上可能产生像素。
- 非目标兄弟分支不会因为祖先被保留而自动参与渲染。
- runtime semantic ID 默认不落盘，`save_runtime_ids=false`；稳定 semantic ID 继续保存并用于后处理。
- 新后处理必须等待重新采集出 `front_teeth_only` 数据，旧的 `headless_render0805_01` 数据不能直接替代这一新增参考输入。
