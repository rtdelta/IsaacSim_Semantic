# 03 原点与水平参考系版本

新资产：`/root/gpufree-data/IsaacSim_Asset/excavator_module_set/Sim_Fangshan_02/Excavator_Fangshan_05_origin03.usda`

新场景：`/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_11_origin03.usda`

原 03/04/05 和 Stage08/10/11 均保留。新场景继续使用原 prim 路径，传感器父子关系和局部安装变换不变。
资产原点恢复到 03 履带原点对应的位置，扫描几何仍统一放大 2.4 倍。新场景补偿了实例摆放、各部件覆盖值和世界固定关节。

## GUI 操作

1. 在 Isaac Sim 打开新的 `combine_scene_11_origin03.usda`。
2. Script Editor 打开本项目 `run_in_isaac.py`，点击 Run；程序自动识别当前场景。
3. 点击 Play Simulation；按需勾选 `Reference axes`。短粗 RGB 轴为 swing，长细浅色轴为 horizontal。
4. Start Recording 开始采集，Stop Recording 正常结束。无需 shell 启动脚本；普通 Payload 使用不依赖本程序。

坐标轴采用 SceneUI 视口叠加，不创建 USD Mesh、碰撞体或 Render Product。匿名运行层及叠加随程序关闭清理。

## 坐标约定

`world -> swing_horizontal_coordinate -> swing_coordinate -> 13 个雷达`，共 15 条动态 TF 边。

`swing_coordinate` 名义上是上车业务参考系，仿真中仍跟随底盘 track，不叠加 cab 独立回转。
H 和 S 共原点；H.Z 与 world.Z 同向；H.X 是 S.X 在世界 XY 平面上的归一化投影。
H.Y = H.Z × H.X。H 到 S 的平移为零，旋转为 R_H 的转置乘 R_S。
两段 TF 使用同一仿真时间戳。`/excavator/root_pose` 继续表示 S 在 world 中的完整姿态；关节角为原生弧度。

前向投影模长低于 1e-6 时保持上一有效航向，高于 2e-6 恢复；首次退化使用零航向。
该状态可在运行时 `motion.frame_snapshot` 中查看。近竖直朝向本来就不能唯一确定投影航向。
当前新场景初始 H、S、world 轴向一致；程序不强行重置其他场景的真实朝向。

## 旧数据兼容

新原点在旧 05 根系中为 d=(0.05816097110509872, 0.034142205119133, 0.10500001907348633) m。
新根世界位置 p_new = p_old + R_old*d；同一点的新根坐标 x_new = x_old-d。
旧 MCAP 保留旧 TF 定义；旧绝对根轨迹或外参不能未经转换直接用于新模型。
新录包 `session.json` 包含 `frame_convention_version`、原点版本和坐标规则。

URDF 叠加保持原先几何位置，其原始基座参考点现在位于新根的 -d，不再与新根重合。
新资产旁的 `Excavator_Fangshan_05_origin03_data/validation.json` 记录几何/安装验证和旧文件 SHA-256。

## 已完成的验证（2026-09-16）

- 本地 39 项测试通过，包括水平参考系、随机姿态组合、航向越界和投影退化处理。
- 原 03/04/05、Stage08/10/11 和 05 附属数据共 38 个文件的 SHA-256 与修改前一致。
- 几何世界变换与旧场景一致（最大矩阵元素误差 4.45e-16）；13 个雷达和 1 个相机的安装局部变换、世界变换及父子层级不变。
- 两个同时加载的新资产 Payload 实例通过关节目标路径重映射验证。引用时需要保留原有模型及材质等依赖文件。
- Isaac Sim 原生 PhysX/ROS2 验证通过：初始轴向一致、纯航向旋转和组合倾斜、视口坐标轴显示与清理。
- 实际录制的 MCAP 包含 15 条 TF 边，核验 61 个完整 TF 时间点、57 次根位姿比对，其中 27 次有倾斜。两段 TF 组合与根位姿的最大矩阵元素误差为 2.83e-8。

远端详细报告位于 `validation/results/origin03_horizontal/kit_validation.json` 与 `bag_validation.json`。
这次原生验证使用保留实际关节和传感器变换的轻量场景，没有重跑 13 路 RTX 点云渲染，也没有完成新完整场景的画面验收。
本次验证进程已结束，不会在后台持续运行。

## 回退

场景回退只需关闭程序并重新打开原 `combine_scene_11.usda`。如果也需要恢复旧 TF 名称和旧发布行为，应同时恢复程序备份。

远端首次部署前程序备份：
`/root/gpufree-data/semantic/scripts/260907LidarVisualizer/backups/origin03_horizontal_20260916_111145_973160`

本地程序备份：`backups/origin03_horizontal_20260916_105615`。
按备份清单恢复原文件；后续同名前缀的备份是部署中间版本，不应作为首次修改前版本。
未执行回退，也未覆盖旧场景和资产。
