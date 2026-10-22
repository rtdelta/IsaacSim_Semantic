# single0602Headless 坐标系与键盘运动契约

更新日期：2026-10-15（北京时间）。契约版本：`s0602_track_equivalent_v1`。

single0602 沿用现有业务 TF 名称。实际工程尚不能测量 cab 相对 track 的回转角，因此本版本将该角度假定为 0°，以底盘参考位姿表达整机。WASD 使用随整机航向更新的 `swing_horizontal_coordinate`，替代前一轮尚未确定的水平控制轴方案。

## 已确定的工程假设

定义 `q_cab_track` 为 cab 相对 track 的回转角，正方向及原生 DOF 映射由所用资产的关节定义确定。本版本采用：

```text
q_cab_track = 0 rad
angle_source = assumed_zero
```

这是缺少实际测量时的工程假设。仿真内部读回的关节角用于核验该假设是否得到执行，不能因此把真实设备角度标记为已测得。

在这项假设和现行业务原点约定下，定义业务参考系的等效关系：

```text
swing_coordinate            ≡ track_coordinate
swing_horizontal_coordinate ≡ track_horizontal_coordinate
```

右侧名称是语义别名，首版不新增同义 TF 节点。TF、MCAP、轨迹和网页继续使用左侧名称。

该等效关系不要求 `cab_prim` 与 `track_prim` 的实际原点重合，也不删除两部件间的固定安装偏移。传感器仍安装在实际 cab、大臂等部件下。未来具备回转角测量能力并启用非零回转时，需要升级坐标系契约，重新明确 track 与 cab 的关系。

## 坐标系定义

| 名称 | 原点 | 轴向与更新方式 | 主要用途 |
| --- | --- | --- | --- |
| `world` | 当前场景世界原点 | 世界轴固定，Z 向上 | 全局摆放、整机位姿和传感器世界位姿 |
| `swing_coordinate` | 当前资产声明的底盘业务参考点 | 完整跟随底盘平移及姿态 | 整机轨迹根位姿，等效于 track 参考系 |
| `swing_horizontal_coordinate` | 与 `swing_coordinate` 同原点，保留其高度 | Z 与世界 Z 同向，X 为当前整机参考 X 轴的水平投影，Y 按右手系确定 | WASD 水平移动，水平航向与倾斜参考 |
| 部件局部系 | 对应 track、cab、boom、arm、bucket 刚体的资产原点 | 随各自部件运动 | 刚体状态、关节连接、传感器安装 |
| 雷达 frame | 对应雷达数据原点 | 遵循该雷达原生输出轴向 | 保存局部 XYZ 和计算外参 |
| 相机 optical frame | 对应相机光学中心 | X 向右、Y 向下、Z 向前 | 图像、标定与相机外参 |

业务原点沿用加载资产的既有定义。origin03 系列采用原 03 track 来源原点，不能将其解释为实测接地点、重心或回转销轴中心。运行时根据实际底盘位姿和固定参考偏移计算业务位姿，不持续读取静止模型容器充当实际底盘状态。

车体参考方向采用 X 前、Y 左、Z 上的右手约定；倾斜后，车体 Z 可以偏离世界 Z。部件和关节局部轴以资产定义为准，不能把三根工作装置关节的原生轴都解释成世界轴。

## 水平参考系计算

采用列向量记号。令 `B = swing_coordinate`，`H = swing_horizontal_coordinate`，`p_B` 为世界位置，`R_W_B` 为从 B 到世界的旋转。水平系计算为：

```text
p_H = p_B
forward_W = R_W_B × [1, 0, 0]
projection = [forward_W.x, forward_W.y, 0]
x_H = normalize(projection)
z_H = [0, 0, 1]
y_H = z_H × x_H
R_W_H = [x_H  y_H  z_H]
heading = atan2(x_H.y, x_H.x)
```

水平投影只去掉姿态中的倾斜分量，不改变原点位置，不进行贴地或地形法向跟随。H 的 X/Y 随整机航向实时更新，不冻结为启动时方向，也不固定为世界 X/Y。

复用 v06 `HorizontalFrame` 的退化处理：前向轴接近竖直时保留上一次有效航向；尚无有效历史时使用零航向并令 `heading_valid=false`。保留投影长度、迟滞和四元数符号连续性。网页显示退化状态，验收覆盖恢复过程。

## 键位和运动规则

| 按键 | 动作 | 参考或角度语义 |
| --- | --- | --- |
| W / S | 前进 / 后退 | 沿当前 H 的 +X / -X |
| A / D | 左移 / 右移 | 沿当前 H 的 +Y / -Y |
| Z / X | 升高 / 降低 | 沿世界 +Z / -Z，也等于 H 的 +Z / -Z |
| Q / E | 增加 / 减少整机航向 | 绕世界 Z，转动整机；不改变 cab–track 回转角 |
| R / F | 增加 / 减少横滚偏移 | 方案采用现有 roll 参数通道 |
| T / G | 增加 / 减少俯仰偏移 | 方案采用现有 pitch 参数通道 |
| U / J | 增加 / 减少大臂关节角 | boom 角色，cab 与大臂之间的原生 DOF |
| I / K | 增加 / 减少小臂关节角 | arm 角色，大臂与小臂之间的原生 DOF |
| O / L | 增加 / 减少铲斗关节角 | bucket 角色，小臂与铲斗之间的原生 DOF |

WASD 与 Z/X 为已确认的控制定义；R/F 与 T/G 对应 roll、pitch 是本实现方案对另外两组旋转通道的具体分配。各关节角的增加方向由资产正轴决定，界面需提供单关节方向示意，不能将所有正角统一称为抬起。

令 `f = W-S`、`l = A-D`、`u = Z-X`，按键按下取 1，未按下取 0。平移速度为 `v`，控制步长为 `dt`：

```text
n = max(1, sqrt(f*f + l*l))
delta_p_W = v * dt * ((f*x_H + l*y_H)/n + u*z_H)
```

相反按键抵消。水平斜向移动归一化，水平速度不因 W+A 等组合增加；垂直通道独立。每次控制更新只积分一次，并将水平分量对应的世界 Z 增量保持为零。

2026-10-15 补充：`v` 和角度变化率用于计算逐帧位置增量，不表示向物理后端下发速度或角速度。本轮继续位置指定，物理速度保持零，不新增加速度计算。[002 连续交互改进方案](ImpPlan/002_连续交互改进方案.md) 已将控制 `dt` 改为原生仿真步长、以 1× 为交互目标；该时间改造不改变本文件的坐标几何及契约版本。

同一步组合平移和转向时，先使用本步开始状态的 H 计算平移，再应用本步航向增量，随后更新参考系并读回状态。下一步使用更新后的 H，保证组合操作顺序可复现。

整机旋转中心采用业务参考原点，不绕观察相机或自动选取的接地点旋转。首版继续使用现有姿态参数化：

```text
R_W_B = Rz(heading) × Ry(initial_pitch + pitch_offset)
                         × Rx(initial_roll + roll_offset)
```

R/F 和 T/G 修改对应角度参数，不将这两个 Euler 参数增量宣称为绕固定世界 X/Y 的任意轴旋转。沿用当前姿态范围和关节限位，正式轨迹保存世界四元数；实现保持 USD/Gf 行向量与规范列向量之间的显式适配。

## TF 与元数据

发布树继续为：

```text
world
└── swing_horizontal_coordinate
    └── swing_coordinate
        ├── 各雷达 frame
        └── 各相机 optical frame
```

这是一棵业务参考树。传感器相对 `swing_coordinate` 的变换按每组实际状态计算；挂在运动部件上的传感器，其相对变换可以随关节变化。

轨迹 metadata 与采集 manifest 增加以下语义记录，具体序列化字段在实现时保持版本化：

```json
{
  "frame_contract_version": "s0602_track_equivalent_v1",
  "root_frame": "swing_coordinate",
  "horizontal_frame": "swing_horizontal_coordinate",
  "keyboard_translation_frame": "swing_horizontal_coordinate",
  "cab_track_angle_rad": 0.0,
  "cab_track_angle_source": "assumed_zero"
}
```

另行记录资产原点版本、实际根与底盘固定偏移、swing 原生 DOF 零位映射及启动读回值。旧轨迹缺少新契约时，先核对其原点、轴向和回转角假设，再进行显式迁移；不能仅补上版本字符串就认定兼容。

## 来源与实现边界

- 用户在 2026-10-15 确认 cab–track 回转角默认为 0°，两组业务参考系分别等效，WASD 沿当前 `swing_horizontal_coordinate` 移动。
- [v06 配置](../../config/robot_sensors.json)。
- [水平系算法](../../sensor_visualizer_v06/robot/reference_frames.py)。
- [整机参考偏移与状态读回](../../sensor_visualizer_v06/robot/articulation_motion.py)。
- [既有运动参数化](../../sensor_visualizer_v06/robot/base_control.py)。
- [当前简化 TF](../../sensor_visualizer_v06/messages.py)。

旧 v06 的键盘按航向换算水平位移，基本符合本次确认的 WASD 语义。其 swing DOF 保持的是启动原生角度，并未单独证明工程角为零；single0602 需增加零位映射和启动、重放核验。
