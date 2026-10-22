# 当前挖机 3DGS TF 仿真对接规范

本文是当前 3DGS 挖机本体的 TF 唯一对接定义，供仿真、运动解算和环视渲染三方
统一使用。数值来自正式配置
[`aif_excavator_3d_surround_view.yaml`](../config/aif_excavator_3d_surround_view.yaml)，
不是历史 URDF 的关节原点。

## 1. 坐标约定

- 遵循 ROS REP-103：`+X` 向前、`+Y` 向左、`+Z` 向上；
- TF 平移单位为米，关节角和 `sensor_msgs/JointState` 使用弧度；
- 正角遵循右手定则；
- `base_link` 是环视渲染、点云融合和整机定位的基准；
- 当前地面参考平面约为 `base_link z=-0.39 m`；
- 当前 3DGS 履带可见下缘约为 `z=-0.375 m`，与地面基准相差约 1.5 cm。

## 2. 必须使用的 TF 树

```text
map / odom / world                 可选，由仿真表达整机全局位姿
└── base_link                      环视和点云融合基准
    ├── swing_link                 回转平台主干
    │   ├── boom_link              大臂
    │   │   └── arm_link           小臂
    │   │       └── bucket_link    挖斗
    │   ├── lidar_front            前雷达固定外参
    │   ├── lidar_rear             后雷达固定外参
    │   ├── lidar_left             左雷达固定外参
    │   └── lidar_right            右雷达固定外参
    └── track_link                 履带独立附属支路，到此结束
```

![当前正式TF树](images/tf_tree.svg)

必须注意：

1. 主干是 `base_link -> swing_link -> boom_link -> arm_link -> bucket_link`；
2. 履带是另一条 `base_link -> track_link` 支路；
3. 当前定义中不存在 `track_link -> swing_link`；
4. 不能把历史 URDF 的 `track_link -> swing_link` 和当前主干同时发布；
5. 每个 child frame 只能有一个 TF 发布者，仿真发布本树时应停用其他同名发布器。

履带和平台在机械上仍然通过中心回转支承连接。这里把它们拆成两个 `base_link`
子节点，是为了避免不可靠的履带-平台观测角污染平台、工作装置、雷达和虚拟相机
主干。

## 3. 每段 TF 的精确定义

绑定姿态下所有固定 RPY 均为 `(0, 0, 0)`，所有固定平移在运动中保持不变。

| 关节 | 父坐标系 | 子坐标系 | 父系固定平移 / m | 固定 RPY | 动态旋转轴 |
|---|---|---|---:|---:|---:|
| J0 平台 | `base_link` | `swing_link` | `(0.000, 0.000, 0.600)` | `(0,0,0)` | `+Z`，另叠加平台 roll/pitch |
| 履带支路 | `base_link` | `track_link` | `(0.000, 0.000, 0.000)` | 默认 `(0,0,0)` | 当前无动态关节 |
| J1 大臂 | `swing_link` | `boom_link` | `(-0.374, -0.270, 0.954)` | `(0,0,0)` | `+Y` |
| J2 小臂 | `boom_link` | `arm_link` | `(4.550, -0.066, 3.198)` | `(0,0,0)` | `+Y` |
| J3 挖斗 | `arm_link` | `bucket_link` | `(1.226, -0.093, -2.662)` | `(0,0,0)` | `+Y` |

当前不在环视包中限制 J0～J3 的角度范围；角度限位由仿真或运动解算端负责。
上述四个关节都只有旋转自由度，没有任何平移自由度。

### 3.1 `base_link -> swing_link`

```text
translation = (0.000, 0.000, 0.600)
rotation    = Rz(q_swing) × Ry(platform_pitch) × Rx(platform_roll)
```

对应当前 C++ 四元数组合顺序：

```text
q_base_swing = q_fixed × q_yaw × q_platform_rpy
q_fixed      = quaternionFromRPY(0, 0, 0)
q_yaw        = quaternion(axis=+Z, angle=q_swing)
q_platform_rpy = quaternionFromRPY(platform_roll, platform_pitch, 0)
```

当前正式设备没有可靠平台回转角时，`q_swing=0`。仿真如果有可信平台回转角，可直接
按 `+Z` 右手正方向发布。平台 roll/pitch 表达司机室顶部、与平台固连 IMU 的姿态。

### 3.2 `base_link -> track_link`

当前默认是严格单位变换：

```text
translation = (0, 0, 0)
quaternion  = (x=0, y=0, z=0, w=1)
```

如果以后有独立可信的履带姿态，可只修改这条支路；不能把 `track_link` 重新插入
平台主干。

### 3.3 J1、J2、J3

三段都使用相同形式：

```text
T_parent_child = Translation(fixed_xyz) × Ry(q_joint)
```

对应四元数为：

```text
quaternion = (x=0, y=sin(q_joint/2), z=0, w=cos(q_joint/2))
```

因此仿真不要在这些关节中加入额外的固定 RPY，也不要使用历史 URDF 的局部 `+Z`
轴。当前 3DGS 适配后的 J1/J2/J3 全部明确使用父系 `+Y` 单轴。

## 4. 绑定姿态下的关节中心

下面的坐标全部是在当前 3DGS 绑定姿态的 `base_link` 中测得，可用于仿真可视化
标记和接缝复核：

| 点 | 机械含义 | `base_link` 坐标 / m | 绑定姿态轴 |
|---|---|---:|---:|
| J0 | 履带与平台的中心回转轴 | `(0.000, 0.000, 0.600)` | `+Z` |
| J1 | 平台与大臂的大臂根主销 | `(-0.374, -0.270, 1.554)` | `+Y` |
| J2 | 大臂与小臂主销 | `(4.176, -0.336, 4.752)` | `+Y` |
| J3 | 小臂与挖斗主销 | `(5.402, -0.429, 2.090)` | `+Y` |

父系固定平移与这些点的关系为：

```text
J0_base                 = ( 0.000,  0.000,  0.600)
J1_swing = J1-J0        = (-0.374, -0.270,  0.954)
J2_boom  = J2-J1        = ( 4.550, -0.066,  3.198)
J3_arm   = J3-J2        = ( 1.226, -0.093, -2.662)
```

连接点图片：

- [整机和局部连接点](images/3dgs_tf_connection_points.png)
- [逐部件入端/出端](images/3dgs_tf_connection_points_by_part.png)
- [单轴组合转动检查](images/3dgs_tf_single_axis_rotation_test.png)

## 5. 3DGS 文件和坐标系绑定

| 3DGS 文件 | TF frame | 说明 |
|---|---|---|
| `track.ply` | `track_link` | 履带独立支路 |
| `cab.ply` | `swing_link` | 回转平台、驾驶室和车尾主体 |
| `boom.ply` | `boom_link` | 大臂 |
| `arm.ply` | `arm_link` | 小臂 |
| `bucket_without_teeth.ply` | `bucket_link` | 挖斗 |

五份 PLY 共用一个重建坐标系，并不是分别以各关节为原点。渲染器内部统一应用：

```text
base_link <- reconstruction
translation = (3.20352, -0.34217, 2.04934) m
RPY         = (-103.98993°, -5.69811°, 61.29154°)
scale       = 2.40
```

这组 `reconstruction_to_base` 是 3DGS 资产显示变换，不是 ROS TF。仿真端不能把
它再发布到 TF 树，也不能再次把关节平移或雷达外参乘以 `2.40`，否则会重复变换。

## 6. 启动零位与绝对关节角

当前所有部件使用 `pose_mode=capture_startup`。环视节点启动时记录每个部件的
`base_link <- part_link`，之后只应用相对启动时刻的变化：

```text
M_part(t) = T_base_part(t)
            × inverse(T_base_part(t_bind))
            × T_base_reconstruction
```

因此仿真对接必须遵守：

1. 先稳定发布完整 TF 树；
2. 挖机保持一个确定的绑定姿态；
3. 再启动环视渲染器；
4. 环视启动后再开始关节运动；
5. 如果 TF 发布器重启或零位改变，环视节点也应重新启动并重新捕获绑定姿态。

当前没有跨所有仿真模型通用的“绝对 URDF 关节零位”。推荐仿真发布 3DGS 相对角：

```text
q_3dgs_joint(t) = sign × (q_sim_joint(t) - q_sim_joint(t_bind))
```

其中 `sign` 由仿真关节轴与本文 `+Z/+Y` 轴是否同向决定。

### 6.1 当前 `bag_2` 仿真的已验证映射

如果仿真同事使用的是生成 `bag_2.mcap` 的同一模型，已经验证过的绑定绝对角为：

```text
swing_bind =   0.0000°
boom_bind  = +37.1667°
arm_bind   = -85.0000°
bucket_bind=  -5.8742°
```

映射公式为：

```text
q_swing_3dgs = +(q_swing_sim -   0.0000°)
q_boom_3dgs  = -(q_boom_sim  -  37.1667°)
q_arm_3dgs   = -(q_arm_sim   - (-85.0000°))
q_bucket_3dgs= -(q_bucket_sim- ( -5.8742°))
```

`bag_2` 中 swing 和 bucket 没有变化，所以本次只动态验证了 boom/arm 的符号；平台
回转和挖斗仍应通过仿真单关节动作再确认一次。

## 7. 雷达 TF

所有安装在回转平台上的雷达必须是 `swing_link` 的固定子节点：

```text
swing_link -> lidar_front
swing_link -> lidar_rear
swing_link -> lidar_left
swing_link -> lidar_right
```

正式环视节点不假设固定数量，但点云消息的 `header.frame_id` 必须与对应雷达 TF
的 child frame 完全一致。固定外参建议通过 `/tf_static` latch 发布。渲染器会按
点云时间戳查询完整的 `base_link <- lidar_frame`，仿真端不要提前把点坐标改写成
`base_link` 后仍保留雷达 frame_id。

`bag_2` 本次适配后的四雷达外参可以作为同一仿真模型的参考：

| TF | `swing_link` 平移 / m |
|---|---:|
| `swing_link -> MyOS0_front` | `(1.2754, 0.6793, 2.4164)` |
| `swing_link -> MyOS0_back` | `(-3.1913, 0.1418, 1.7042)` |
| `swing_link -> MyOS0_left` | `(-1.3920, 1.5970, 1.2861)` |
| `swing_link -> MyOS0_right` | `(-1.1015, -1.3781, 1.1772)` |

以上只适用于 `bag_2` 对应的仿真安装位置；实车或其他仿真模型必须使用各自标定
外参，但父节点仍应是 `swing_link`。

## 8. 全局位姿的职责边界

当前建议：

```text
world/map/odom -> base_link：整机全局平移和可信航向
base_link -> swing_link：平台相对主干的 roll/pitch 和 J0 yaw
base_link -> track_link：履带独立附属姿态，当前单位变换
```

如果仿真已经在 `world -> base_link` 中加入整机 roll/pitch，就不要再把同一组
roll/pitch 重复写入 `base_link -> swing_link`。当前环视部署采用平台 IMU 的
roll/pitch 写入 `base_link -> swing_link`，因此配套的全局 `base_link` 通常只承担
定位平移和可信 yaw。双方必须选择一种唯一所有权，避免姿态叠加两次。

## 9. 仿真发布模板

伪代码如下：

```cpp
publishTf("base_link", "track_link",
          xyz(0.0, 0.0, 0.0), quaternionFromRPY(0.0, 0.0, 0.0));

publishTf("base_link", "swing_link",
          xyz(0.0, 0.0, 0.600),
          quaternionFromAxisAngle(+Z, q_swing) *
          quaternionFromRPY(platform_roll, platform_pitch, 0.0));

publishTf("swing_link", "boom_link",
          xyz(-0.374, -0.270, 0.954), quaternionFromAxisAngle(+Y, q_boom));

publishTf("boom_link", "arm_link",
          xyz(4.550, -0.066, 3.198), quaternionFromAxisAngle(+Y, q_arm));

publishTf("arm_link", "bucket_link",
          xyz(1.226, -0.093, -2.662), quaternionFromAxisAngle(+Y, q_bucket));
```

建议动态 TF 频率不低于 30 Hz，所有同一周期的关节 TF 使用同一个时间戳。雷达
固定外参通过 `/tf_static` 发布一次；点云 header 使用采样时刻，不使用发布时间。

## 10. 对接验收清单

- [ ] TF 树中 `track_link` 和 `swing_link` 都直接属于 `base_link`；
- [ ] 不存在 `track_link -> swing_link`；
- [ ] J0 平移始终为 `(0,0,0.600)`，只允许角度变化；
- [ ] J1/J2/J3 固定平移与本文完全一致；
- [ ] J1/J2/J3 只有 `+Y` 单轴旋转，没有额外 RPY 或动态平移；
- [ ] 单动 boom 时只有 boom 及其后代运动；
- [ ] 单动 arm 时只有 arm、bucket 运动；
- [ ] 单动 bucket 时只有 bucket 运动；
- [ ] 四雷达父节点为 `swing_link`，外参在运行中不变化；
- [ ] TF 发布稳定后再启动环视并捕获绑定姿态；
- [ ] 没有两个节点同时发布同一个 child frame；
- [ ] 全局 TF 和平台 TF 没有重复叠加同一组 roll/pitch；
- [ ] 3DGS `2.40` 缩放只由渲染器应用，仿真 TF 保持米制。
