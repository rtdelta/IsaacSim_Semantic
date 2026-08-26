# `01_capture_multisensor.example.json` 参数说明

这是 v03 的主运行配置。命令行只需要把这个文件传给 `--config`；其余 JSON/CSV 由本文件通过相对路径引用。JSON 不支持注释，所以实际解释集中在本文档中。

文档中的“整数”指 JSON `integer`，“数字”指 JSON `number`（整数或浮点数），“对象”指 JSON `object`，“数组”指 JSON `array`。

## 顶层字段

以下顺序与 JSON 文件一致。

| 顺序 | JSON 路径 | 类型 | 必填 | 含义与填写要求 |
|---:|---|---|---:|---|
| 1 | `schema_version` | 整数 | 是 | 配置协议版本。当前代码只接受 `6`。 |
| 2 | `run_id` | 非空字符串 | 是 | 本次数据集运行的唯一名称。建议只使用字母、数字、下划线和短横线，并在不同任务间保持唯一。 |
| 3 | `output` | 字符串路径 | 是 | 输出根目录。可填绝对路径；相对路径按主配置所在目录解析。正式采集建议使用数据盘绝对路径。 |
| 4 | `scene` | 对象 | 是 | USD 场景、物理时钟、语义映射和运动驱动。见下一节。 |
| 5 | `render_groups` | 非空对象 | 是 | RTX 渲染组。对象键是渲染组 ID，值是渲染组配置。 |
| 6 | `drivers` | 对象 | 是 | 自定义传感器驱动注册表。没有自定义驱动时填 `{}`。 |
| 7 | `sensors` | 非空数组 | 是 | 传感器列表。至少一个传感器必须设置 `enabled: true`。 |
| 8 | `capture` | 对象 | 是 | 数据集帧数、采集基准频率、场景变体和事务同步规则。 |
| 9 | `runtime` | 对象 | 是 | 分段、断点续采、超时、重启和 Isaac Python 启动命令。 |

## `scene` 字段

| 顺序 | JSON 路径 | 类型 | 必填 | 含义与填写要求 |
|---:|---|---|---:|---|
| 1 | `scene.usd` | 字符串路径 | 是 | 要打开的 USD/USDA/USDC Stage。可以是绝对路径、相对路径或支持的 URL。运行前文件必须可访问。 |
| 2 | `scene.physics_hz` | 正整数 | 是 | 物理更新频率，单位 Hz。示例为 `60`。它必须能被 `capture.base_hz` 和每个启用传感器的 `clock.hz` 整除。 |
| 3 | `scene.mapping` | 字符串路径或 `null` | 否 | 语义映射 JSON。需要稳定 `semantic_id.npy` 和 `semantic_color.png` 时填写；只采 RGB 或只保留原始语义时可填 `null`。 |
| 4 | `scene.motion` | 对象或 `null` | 否 | 可选运动驱动。静态场景可删除该字段或填 `null`。 |
| 5 | `scene.state_prim_paths` | 字符串数组 | 否 | 参与世界状态哈希的绝对 USD Prim Path。应填写会影响采集结果的机器人/车辆根 Prim。每项必须以 `/` 开头且不能是 `/`。 |
| 6 | `scene.pre_roll_steps` | 非负整数 | 否 | 正式采集前预运行的物理步数，默认 `0`。用于让物理、材质或传感器状态稳定。 |

### `scene.motion`

| 顺序 | JSON 路径 | 类型 | 必填 | 含义与填写要求 |
|---:|---|---|---:|---|
| 1 | `scene.motion.driver` | 非空字符串 | 是 | 运动驱动导入路径，格式必须为 `python.module:ClassName`。内置 CSV 驱动为 `semantic_world_v03.motion:CsvArticulationMotion`。 |
| 2 | `scene.motion.trajectory` | 字符串路径或 `null` | CSV 驱动必填 | 轨迹 CSV。相对路径按主配置目录解析。 |
| 3 | `scene.motion.settings` | 对象 | 是 | 传给运动驱动的专用参数。CSV 驱动字段如下。 |

### `scene.motion.settings`（CSV 运动驱动）

| 顺序 | JSON 路径 | 类型 | 必填 | 含义与填写要求 |
|---:|---|---|---:|---|
| 1 | `articulation_prim_path` | 绝对 Prim Path 字符串 | 是 | `SingleArticulation` 的根 Prim。它必须是 Stage 中可初始化的 Articulation。 |
| 2 | `time_column` | 字符串 | 否 | CSV 时间列名，默认 `time`；单位为秒，值必须严格递增。 |
| 3 | `joint_columns` | 非空对象 | 是 | 键是 USD/Articulation DOF 名称，值是 CSV 列名。所有 DOF 和列都必须存在。 |
| 4 | `angle_units` | 枚举字符串 | 否 | `radians` 或 `degrees`，默认 `radians`。只影响关节列。 |
| 5 | `interpolation` | 枚举字符串 | 否 | `linear` 表示线性插值；`hold` 表示保持左侧样本。默认 `linear`。 |
| 6 | `root_pose` | 对象或省略 | 否 | 同时按 CSV 设置 Articulation 世界位姿。省略时只驱动关节。 |
| 6.1 | `root_pose.position` | 长度为 3 的字符串数组 | 是 | 依次填写世界坐标 X、Y、Z 对应的 CSV 列名，单位通常为米。 |
| 6.2 | `root_pose.orientation_wxyz` | 长度为 4 的字符串数组 | 是 | 依次填写四元数 W、X、Y、Z 对应的 CSV 列名。每行四元数不能为零，代码会归一化。 |

## `render_groups`

对象键（示例中的 `camera_pt`、`lidar_rtx`）是渲染组 ID，必须匹配 `^[A-Za-z][A-Za-z0-9_.-]*$`。同一 worker 中所有非空渲染配置必须选择相同的全局 renderer。

每个渲染组内部字段顺序如下：

| 顺序 | 字段 | 类型 | 必填 | 含义与填写要求 |
|---:|---|---|---:|---|
| 1 | `kind` | 枚举字符串 | 是 | `camera_rtx`、`rtx_sensor` 或 `mixed_rtx`。相机组通常使用 `camera_rtx`，RTX LiDAR 组使用 `rtx_sensor`。 |
| 2 | `profile` | 字符串路径或 `null` | 否 | 渲染配置文件。示例引用 `02_render_pathtracing.example.json`。填 `null` 时不会从文件加载全局 renderer/settings。 |
| 3 | `execution` | 枚举字符串 | 否 | `batched`：同组需要触发渲染的传感器共享一次渲染；`serial`：逐传感器触发。默认 `serial`，多相机通常推荐 `batched`。 |
| 4 | `multi_gpu` | 布尔值 | 否 | 是否向启动配置声明多 GPU。当前单张 RTX 4090 环境填写 `false`。 |
| 5 | `rt_subframes` | 正整数 | 否 | 每次 Replicator 渲染触发使用的 RTX 子帧数，默认 `1`。PathTracing 常用 `8`，质量越高通常越慢。 |
| 6 | `warmup_frames` | 非负整数 | 否 | 传感器初始化或场景切换后预热的 App 更新次数，默认 `0`。PathTracing 建议设置足够的预热帧。 |
| 7 | `settings` | 对象 | 否 | 渲染组扩展参数，目前可填 `{}`；不要在这里填写未被对应后端识别的任意字段。 |

## `drivers`

`drivers` 是“传感器类型 → Python 类”的对象。例如：

```json
{
  "camera.custom": "my_package.my_driver:CustomCameraDriver"
}
```

键和值都是非空字符串，值必须含 `:`。内置类型无需填写：`camera.pinhole`、`camera.fisheye_opencv`、`lidar.rtx.rotary`、`lidar.rtx.solid_state`。

## `sensors`

### 所有传感器共有字段

每个数组元素内部按照以下顺序填写：

| 顺序 | 字段 | 类型 | 必填 | 含义与填写要求 |
|---:|---|---|---:|---|
| 1 | `id` | 非空字符串 | 是 | 本次任务内唯一的传感器 ID，格式为 `^[A-Za-z][A-Za-z0-9_.-]*$`。它也用于变体和同步组引用。 |
| 2 | `type` | 字符串 | 是 | 驱动类型。使用内置类型或在 `drivers` 中注册的自定义类型。 |
| 3 | `enabled` | 布尔值 | 否 | 是否在本次运行初始化和采集。默认 `true`。模板传感器建议保持 `false`，确认 Stage 后再启用。 |
| 4 | `source` | 对象 | 是 | 使用已有 Prim，或者在 Session Layer 中创建传感器。 |
| 5 | `render_group` | 字符串 | 是 | 必须引用 `render_groups` 中存在的键。 |
| 6 | `clock` | 对象 | 是 | 传感器采样时钟。 |
| 7 | `modalities` | 非空字符串数组 | 是 | 该传感器可能输出的全部模态，不能重复。变体只能选择其子集。 |
| 8 | `resolution` | `[宽, 高]` 正整数数组 | 相机必填 | 相机 RenderProduct 分辨率；LiDAR 可省略。鱼眼相机应与标定 `imageSize` 一致。 |
| 9 | `calibration` | 对象 | 否 | 标定读取、验证或创建策略。默认策略为 `read_from_prim`。 |
| 10 | `output` | 对象 | 否 | 输出 sink、是否为必需传感器和子目录。 |
| 11 | `settings` | 对象 | 否 | 驱动专用参数。普通已有 Camera 通常填 `{}`。 |

### `source` 两种模式

已有 Prim：

| 顺序 | 字段 | 类型 | 必填 | 含义 |
|---:|---|---|---:|---|
| 1 | `mode` | 字符串 | 是 | 固定为 `existing_prim`。 |
| 2 | `prim_path` | 绝对 Prim Path 字符串 | 是 | Stage 内实际存在的相机或 LiDAR Prim。Camera 必须是 `Camera` 类型；鱼眼还要含 OpenCV Fisheye Schema/属性。 |

动态创建：

| 顺序 | 字段 | 类型 | 必填 | 含义 |
|---:|---|---|---:|---|
| 1 | `mode` | 字符串 | 是 | 固定为 `create`。 |
| 2 | `parent_prim` | 绝对 Prim Path 字符串 | 是 | 已存在的父 Prim。代码不会自动补建父节点。 |
| 3 | `prim_name` | 单个 USD 名称字符串 | 是 | 新建 Prim 名称，不能包含 `/`。最终路径为 `parent_prim/prim_name`，且运行前不能已存在。 |
| 4 | `config` | 字符串或省略 | 条件必填 | Isaac 内置传感器配置名，例如 LiDAR 的 `Example_Rotary`。不能与 `usd_path` 同时填写。 |
| 5 | `usd_path` | 字符串路径或省略 | 条件必填 | 从 USD 资产创建传感器时填写。不能与 `config` 同时填写。 |
| 6 | `variant` | 字符串、字符串对象或省略 | 否 | 创建 API 使用的变体选择。对象的键和值都必须是字符串。 |

### `clock`

| 顺序 | 字段 | 类型 | 必填 | 含义与约束 |
|---:|---|---|---:|---|
| 1 | `hz` | 正数 | 是 | 传感器采样频率。必须整除 `scene.physics_hz`，并且必须是 `capture.base_hz` 的整数因子。 |
| 2 | `phase_seconds` | 非负数字 | 否 | 相对采集时间轴的相位，默认 `0`，必须对齐到整数物理步。 |
| 3 | `acquisition` | 枚举字符串 | 是 | 相机必须为 `snapshot`；旋转/固态 LiDAR 使用 `interval`。 |

### `modalities`

相机支持：`rgb`、`semantic_segmentation`、`instance_segmentation`、`instance_id_segmentation`、`distance_to_camera`、`distance_to_image_plane`、`depth`、`normals`、`motion_vectors`、`pointcloud`、`bounding_box_2d_tight`、`bounding_box_2d_loose`、`bounding_box_3d`。

RTX LiDAR 支持：`generic_model_output`、`point_cloud`、`range`、`intensity`、`stable_id_map`。

### `calibration`

| 顺序 | 字段 | 类型 | 必填 | 含义与填写要求 |
|---:|---|---|---:|---|
| 1 | `policy` | 枚举字符串 | 否 | `read_from_prim`、`read_and_validate`、`from_profile`、`inline` 或 `explicit_override`。动态创建鱼眼必须使用后三种之一。 |
| 2 | `profile` | 字符串路径 | `from_profile` 必填 | 外部标定 JSON；相对路径按主配置目录解析。 |
| 3 | `expected_model` | 字符串或省略 | 否 | 期望模型。针孔写 `pinhole`，OpenCV 鱼眼写 `opencv_fisheye`。 |
| 4 | `expected_hash` | 字符串或省略 | 否 | 期望标定 SHA-256，可写纯十六进制或 `sha256:<hex>`；不匹配时预检失败。 |
| 5 | `model` | 字符串或省略 | 否 | 内联/自定义标定的模型说明。 |
| 6 | `attributes` | 对象或省略 | `inline` 必填 | 直接填写要写入新建传感器 Prim 的 USD 属性。 |

示例文件中的已有鱼眼使用 `read_and_validate`，所以不需要再写 `fx/fy/k1...k4`；代码会从 `/World/FisheyeCamera` 自动读取。动态创建鱼眼使用 `from_profile`。

### `output`

| 顺序 | 字段 | 类型 | 必填 | 含义与约束 |
|---:|---|---|---:|---|
| 1 | `sink` | 字符串 | 否 | 当前只支持 `filesystem`。 |
| 2 | `required` | 布尔值 | 否 | `true` 表示该传感器失败时不能完整提交同步事务；默认 `true`。 |
| 3 | `folder` | 安全相对路径字符串 | 否 | 传感器输出子目录。不能是绝对路径，不能包含 `..`。 |
| 4 | `settings` | 对象 | 否 | 输出 sink 扩展参数，当前文件系统 sink 可填 `{}`。 |

### 示例中驱动专用 `settings`

| 传感器 | 字段 | 类型 | 含义 |
|---|---|---|---|
| `fisheye_created` | `warmup_frames` | 非负整数 | Camera 驱动初始化后的额外预热 App 更新次数。与渲染组预热是两个不同阶段。 |
| `rotary_lidar` | `scan_rate_hz` | 正数 | 期望扫描频率，必须与该传感器 `clock.hz` 相等。 |
| `rotary_lidar` | `accumulate_outputs` | 布尔值 | 是否累积一个完整扫描周期后输出。 |
| `rotary_lidar` | `aux_output_level` | 字符串 | 传给 Isaac RTX LiDAR 的辅助输出级别，例如 `BASIC` 或 `EXTRA`。具体可用值取决于 Isaac 版本。 |
| `rotary_lidar` | `coordinates` | 字符串 | `SPHERICAL` 或包含 `CARTESIAN` 的坐标类型说明，用于解析 GenericModelOutput。 |
| `rotary_lidar` | `attributes` | 对象 | 创建/包装 LiDAR 时写入的额外 USD 属性，键为属性名。没有时填 `{}`。 |

## `capture`

| 顺序 | JSON 路径 | 类型 | 必填 | 含义与填写要求 |
|---:|---|---|---:|---|
| 1 | `capture.frames` | 正整数 | 是 | 每个变体的数据集帧数。两个变体、300 帧、一个相机将计划 600 个相机采集事务。 |
| 2 | `capture.base_hz` | 正数 | 是 | 数据集帧率基准，单位 Hz。必须整除 `scene.physics_hz`。 |
| 3 | `capture.capture_initial_frame` | 布尔值 | 否 | `true` 表示在时间 `0` 采第 0 帧；`false` 表示先推进一个采集周期。 |
| 4 | `capture.variant_execution` | 枚举字符串 | 否 | `variant_major`：完整跑完一个变体再跑下一个；`frame_major`：每帧切换变体。多变体且含 interval 传感器时必须使用 `variant_major`。 |
| 5 | `capture.variants` | 非空对象数组 | 否 | 场景可见性和模态变体。默认只有 `full_scene`。 |
| 6 | `capture.synchronization_groups` | 对象数组 | 否 | 定义同一 capture ID 中哪些传感器作为一个提交事务。 |

### `capture.variants[]`

| 顺序 | 字段 | 类型 | 必填 | 含义与约束 |
|---:|---|---|---:|---|
| 1 | `id` | 非空字符串 | 是 | 变体唯一 ID，格式规则与传感器 ID 相同。 |
| 2 | `visibility` | 对象 | 否 | 键为绝对 Prim Path，值只能是 `inherited` 或 `invisible`。意见只写 Session Layer。 |
| 3 | `include_paths` | Prim Path 字符串数组 | 否 | 非空时启用白名单隔离：仅保留这些路径分支、相机/传感器及显式 inherited 分支。空数组表示不做白名单隔离。 |
| 4 | `modalities_by_sensor` | 对象 | 否 | 键为已启用传感器 ID，值为该变体实际读取/写出的非空模态数组。每项必须已在对应 `sensors[].modalities` 中声明。 |

### `capture.synchronization_groups[]`

| 顺序 | 字段 | 类型 | 必填 | 含义与约束 |
|---:|---|---|---:|---|
| 1 | `id` | 非空字符串 | 是 | 同步组唯一名称。 |
| 2 | `sensor_ids` | 非空字符串数组 | 是 | 启用的传感器 ID，不能重复，同一传感器不能出现在多个同步组。 |
| 3 | `commit_policy` | 枚举字符串 | 否 | `all_or_nothing`：全部成功才提交；`best_effort`：允许可选传感器失败。必需传感器仍受 `output.required` 约束。 |

## `runtime`

| 顺序 | JSON 路径 | 类型 | 必填 | 含义与填写要求 |
|---:|---|---|---:|---|
| 1 | `runtime.segment_frames` | 正整数 | 否 | 每个 worker 负责的帧数，默认 `500`。较小值隔离 GPU/Kit 长时间运行风险，但会增加重启开销。 |
| 2 | `runtime.resume` | 布尔值 | 否 | 是否依据 ledger 断点续采，默认 `true`。同一输出目录的配置指纹必须一致。 |
| 3 | `runtime.heartbeat_seconds` | 正数 | 否 | worker 心跳写入周期，单位秒。 |
| 4 | `runtime.startup_timeout_seconds` | 正数 | 否 | Isaac/Stage/传感器初始化超时。大型 Stage 和 PathTracing 应留足时间。 |
| 5 | `runtime.render_timeout_seconds` | 正数 | 否 | 单个渲染/采集阶段超时。PathTracing 高分辨率时应适当增大。 |
| 6 | `runtime.shutdown_timeout_seconds` | 正数 | 否 | worker 正常退出的等待时间。 |
| 7 | `runtime.max_worker_restarts` | 非负整数 | 否 | 单个 segment 失败后的最大重启次数；`0` 表示不重试。 |
| 8 | `runtime.poll_seconds` | 正数 | 否 | supervisor 查询 worker/心跳状态的间隔。 |
| 9 | `runtime.worker_command` | 非空字符串数组 | 建议必填 | 启动 worker 的命令前缀，每个数组元素是一个独立 argv。远端必须通过 ABI-safe wrapper，不能把整条命令写成一个含空格的字符串。 |

## 使用前必须修改的内容

1. 修改 `output`，为新任务使用新的输出目录。
2. 确认 `scene.usd`、Camera Prim Path 和 Articulation Prim Path 真正存在。
3. 用真实 DOF 名和 CSV 列名替换 `joint_columns`。
4. 只启用 Stage 中存在或能够成功创建的传感器。
5. 动态创建传感器前，确保 `/World/Sensors` 父 Prim 已存在。
6. 将示例语义类别替换为 Stage 的真实语义标签。
7. 先执行 `validate` 和 `plan`，再执行 `run`。

```bash
/usr/bin/python3 run_capture.py validate --config configs/example/01_capture_multisensor.example.json
/usr/bin/python3 run_capture.py plan --config configs/example/01_capture_multisensor.example.json
/usr/bin/python3 run_capture.py run --config configs/example/01_capture_multisensor.example.json --headless
```
