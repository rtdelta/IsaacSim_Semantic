# 05 履带原点与 swing 水平参考系实施记录

日期：2026-09-16。已完成远端新资产、新场景及本地/远端发布程序更新。原 USD 文件保留。

## 交付位置

| 内容 | 远端位置 |
| --- | --- |
| 新挖掘机资产 | `/root/gpufree-data/IsaacSim_Asset/excavator_module_set/Sim_Fangshan_02/Excavator_Fangshan_05_origin03.usda` |
| 新场景 | `/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_11_origin03.usda` |
| 资产验证/运动学记录 | 新资产同目录 `Excavator_Fangshan_05_origin03_data/` |
| GUI 程序 | `/root/gpufree-data/semantic/scripts/260907LidarVisualizer/run_in_isaac.py` |
| TF/ROS 原生验证报告 | 程序目录下 `validation/results/origin03_horizontal/` |

本目录 `sources/` 是两个 USD 文本文件的审计副本，未打包模型、材质、传感器等依赖，不能视为本地独立运行包。

## 实施内容

05 原点改为与 03 履带原点对应的位置。新根原点在旧 05 根坐标系中的偏移为：

```
d = (0.05816097110509872, 0.034142205119133, 0.10500001907348633) m
```

源扫描几何保留统一 2.4 倍缩放。改动后履带源几何局部变换为 `diag(2.4,2.4,2.4,1)`，撤销缩放即回到原 03 履带原点关系。这不是重新定义实测重心或地面中心。

资产部件平移、履带质心坐标、swing 的父侧关节锚点及 URDF 叠加偏移均作相应坐标补偿。场景实例摆放、各部件覆盖值及世界固定关节也同步补偿。几何尺寸、实际摆放、关节轴向/正方向/零位、传感器安装层级不变。URDF 基座参考点相对新根为 `-d`。

场景中的挖掘机 prim 路径仍为 `/Excavator_Fangshan_05`，避免破坏已有传感器和关节引用。新文件名区分版本。初始关节姿态保留原场景的折叠姿态，未改为四关节全零。

运行时 TF 为：

```
world
└── swing_horizontal_coordinate
    └── swing_coordinate
        └── 13 个原雷达 frame
```

`swing_coordinate` 沿用跟随 track 的业务近似，不叠加 cab 独立回转。新增水平参考系由脚本计算；匿名运行层中的 Xform 供 ROS2 节点读取，不调整挖掘机 USD 父子结构。可选 SceneUI 坐标轴只叠加在视口，不创建 USD 几何或额外 Render Product。

## 严格坐标定义

采用列向量。S 在 W 中的位置为 p，旋转矩阵为 R。令 e_z=(0,0,1)，u=R(1,0,0)，v=u-(u·e_z)e_z。

在投影有效时，x_H=v/||v||，y_H=e_z×x_H，R_H=[x_H y_H e_z]。

```
T_W_H = [ R_H   p ]       T_H_S = [ R_H^T R   0 ]
        [  0    1 ]               [    0      1 ]

T_W_H T_H_S = T_W_S
```

H 与 S 始终共原点，H 始终水平。投影模长小于等于 1e-6 时进入航向保持，大于 2e-6 后恢复；首次退化使用零航向。状态可从 `motion.frame_snapshot` 读取。新场景初始 R=I，因此 H、S、world 轴向一致，原点不要求与 world 重合。

`/excavator/root_pose` 继续使用 world 为 header.frame_id，表示 S 的完整世界位姿；`/joint_states` 保留四关节弧度。新录包的 `session.json` 保存坐标系版本与原点定义。旧 MCAP 不自动转换。

## 验证结果与范围

| 检查 | 结果/证据 |
| --- | --- |
| 本地单元测试 | 39 项通过 |
| 旧文件保持 | 38 个源文件 SHA-256 一致，见 `preservation.json`、`asset_validation.json` |
| 几何世界变换保持 | 最大矩阵元素误差 4.44e-16 |
| 传感器/相机安装 | 14 个安装项局部变换、世界变换与层级保持 |
| 关节属性 | 除 swing 父侧位置坐标补偿外保持；见 `payload_validation.json` |
| 双 Payload 实例 | 各实例关节 body 目标正确重映射 |
| 原生 Isaac Sim | 初始位姿、纯 yaw、组合倾斜及坐标轴显示/清理通过；见 `kit_validation.json` |
| MCAP | 15 条 TF 边，61 个完整 TF 时间点，57 次根位姿比对，27 次倾斜样本；见 `bag_validation.json` |
| TF 组合 | 与根位姿最大矩阵元素差 2.8207e-8 |
| 安装外参运行波动 | 最大矩阵元素差 7.1526e-7，处于原生浮点计算精度范围 |

原生验证运行在独立 ROS domain 151，采用保留实际 body/joint/sensor 变换的轻量场景。检查的是 PhysX、状态发布、TF 与 MCAP 序列化链路；没有重跑 13 路 RTX 点云，也没有对新完整场景进行渲染画面验收。时间匹配允许原生双精度秒转纳秒与 Python 舍入产生的 ±1ns 差异。

验证录包：`/root/gpufree-data/semantic/scripts/260907LidarVisualizer/validation/results/origin03_horizontal/captures/20260916_113027_822638_f1356e`。
本次启动的验证进程均已清理。

## 使用与回退

Isaac Sim 打开新场景，在 Script Editor 打开远端 `run_in_isaac.py` 并 Run，再点击 Play Simulation。勾选 `Reference axes` 可查看两组坐标轴；Start/Stop Recording 控制采集。普通 Payload 引用新资产不需要启动程序；动态 TF 发布需要运行程序。

远端首次部署前程序备份：`/root/gpufree-data/semantic/scripts/260907LidarVisualizer/backups/origin03_horizontal_20260916_111145_973160`。

本地首次修改前程序备份：`D:/learning/IntelligentDepartment/CodesSet/Self/260907LidarVisualizer/backups/origin03_horizontal_20260916_105615`。

回退场景时关闭程序并打开原 `combine_scene_11.usda`。恢复旧 TF 行为还需要从上述首次备份恢复程序文件。当前没有执行回退。仅打开旧场景配合新程序，仍将采用新的 TF 名称和水平层。

本地构建、部署和验证辅助脚本位于 `scripts/260916_origin03_horizontal/`。最终部署文件校验记录见 `deployment.json`。
