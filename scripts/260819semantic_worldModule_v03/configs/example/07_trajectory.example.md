# `07_trajectory.example.csv` 参数说明

该 CSV 是 `CsvArticulationMotion` 的轨迹输入数据。它不是 JSON 配置，但主配置的运动参数会引用它，因此在示例集中提供同名说明。

第一行是列名；从第二行开始，每一行都是一个绝对时间样本。所有被主配置引用的单元格必须能转换为浮点数。

## 列说明

以下顺序与 CSV 表头一致。

| 顺序 | 列名 | 数据类型 | 单位/格式 | 含义与填写要求 |
|---:|---|---|---|---|
| 1 | `time` | 浮点数 | 秒 | 数据集绝对时间。必须非空并严格递增，不能有重复时间。主配置通过 `time_column` 指定它。 |
| 2 | `cab` | 浮点数 | 由 `angle_units` 决定 | 驾驶室/上车体回转关节位置示例列。主配置把它映射到 `track_operator_cab_joint`。 |
| 3 | `boom` | 浮点数 | 角度或弧度 | 大臂关节位置示例列。 |
| 4 | `small_arm` | 浮点数 | 角度或弧度 | 小臂关节位置示例列。 |
| 5 | `bucket` | 浮点数 | 角度或弧度 | 铲斗关节位置示例列。 |
| 6 | `root_world_x_m` | 浮点数 | 米 | Articulation 根节点世界坐标 X。 |
| 7 | `root_world_y_m` | 浮点数 | 米 | 根节点世界坐标 Y。 |
| 8 | `root_world_z_m` | 浮点数 | 米 | 根节点世界坐标 Z。 |
| 9 | `root_quat_w` | 浮点数 | 四元数 W | 根节点世界朝向四元数的实部。 |
| 10 | `root_quat_x` | 浮点数 | 四元数 X | 根节点世界朝向四元数 X。 |
| 11 | `root_quat_y` | 浮点数 | 四元数 Y | 根节点世界朝向四元数 Y。 |
| 12 | `root_quat_z` | 浮点数 | 四元数 Z | 根节点世界朝向四元数 Z。四个四元数分量不能同时为零，代码会在应用前归一化。 |

## 与主配置的映射关系

```json
{
  "time_column": "time",
  "joint_columns": {
    "track_operator_cab_joint": "cab",
    "platform_boom_joint": "boom",
    "boom_small_arm_joint": "small_arm",
    "small_arm_bucket_joint": "bucket"
  },
  "angle_units": "degrees",
  "interpolation": "linear",
  "root_pose": {
    "position": ["root_world_x_m", "root_world_y_m", "root_world_z_m"],
    "orientation_wxyz": ["root_quat_w", "root_quat_x", "root_quat_y", "root_quat_z"]
  }
}
```

对象键是 Stage 中的真实 DOF 名称，对象值是 CSV 列名。CSV 可以使用其他列名，只要同步修改主配置。

## 采样和插值

- CSV 不强制与物理频率相同；`linear` 模式会按时间在相邻行之间插值。
- `hold` 模式会保持最近的左侧样本。
- 请求时间早于第一行时使用第一行；晚于最后一行时使用最后一行。
- 每一行描述完整的绝对关节/根位姿，因此当前 v03 可以对分段起点执行绝对 seek，避免从第 0 帧重复回放。
- 示例只有三行，仅用于展示格式，不能直接代表完整采集轨迹。
