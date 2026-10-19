# 新挖掘机与旧传感器的组合场景

新场景：

```text
/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_13_3dgs_contract.usda
```

在新实例的 Isaac Sim 中用 File → Open 打开。默认视角是 `/World/ContractOverview`，旧场景的远景相机 `/World/Stage10Overview` 也保留。打开场景无需执行装配脚本。Play 后可通过 `/World/Excavator/Joints` 下各关节的 Angular Drive / Target Position 查看运动，角度单位为度。

13 路 RTX 传感器会使用较多 CUDA/Vulkan 文件句柄。首次运行检查的扫描已通过，但退出时碰到实例进程的 2450 个文件句柄软上限。验证启动器现将该进程上限提高到 16384；不修改 `/etc/security/limits.conf` 等系统配置。

新开 GUI 时，推荐在远端桌面的终端执行以下启动器，它设置同样的进程上限并打开新场景。它会新开一个 Isaac 实例，已有 GUI 请先自行关闭，避免重复占用 GPU：

```bash
bash /root/gpufree-data/semantic/scripts/260920SensorVisualizer/tools/open_combine_stage.sh
```

启动器现统一调用旧发布项目的 `launch_isaac.py`，准备 ROS 2 Jazzy 和 Isaac 原生库路径，将进程文件句柄软上限提高到 65536，并保留 Motion BVH / multi-tick 关闭设置。已经运行的 Isaac 不会获得这些启动环境修正，需要关闭后重开。本项目此次验收使用 GUI；不要给这个 Full GUI 入口添加 `--no-window` 或隐藏 UI 的参数，相关组合在本实例触发过原生 GPU 崩溃。

场景加载完成后，在 Script Editor 中运行：

```python
exec(open('/root/gpufree-data/semantic/scripts/260907LidarVisualizer/run_in_isaac.py', encoding='utf-8').read())
```

等待 `Publishers ready: 13 LiDAR(s)`。仅观察场景运动可选择 `Observe + publish (no motion writes)` 并点击 `Connect / Apply mode`；需要面板控制关节则使用 `Scripted control + publish`。然后点击 `Play Simulation`。

在另一个远端桌面终端启动 RViz：

```bash
/usr/bin/python3 /root/gpufree-data/semantic/scripts/260907LidarVisualizer/launch_rviz.py
```

脚本初始化会生成当前场景的传感器话题、TF 和 RViz 配置，因此先运行 Script Editor 入口，再启动 RViz。结束采集先 Stop Recording，等待停止完成，再 Pause/Stop Simulation。退出测试或观察时出现保存场景询问，应选择 Don't Save；需要保存人为场景修改时由操作者自行决定。

## 组成

传感器来源是最新旧场景 `combine_scene_12_myairy.usda`，因此使用 MyAiry，而不是更早版本的 MyOS0。

| 内容 | 数量 | 新场景中的位置 |
|---|---:|---|
| 合同定义的 3DGS 挖掘机 | 1 | `/World/Excavator` |
| MyAiry | 7 | `/World/Excavator/swing_link/MyAiry_{left,front,right,backleft,backright,up,back}/sensor` |
| MyNZ3 | 6 | `/World/Excavator/swing_link/MyNZ3_{front,left,right,backleft,backright,back}/sensor` |
| 旧大臂相机 | 1 | `/World/Excavator/boom_link/Camera` |
| Fangshan 环境、灯光、方块、地面 | 沿用 | 保持旧场景的位置和尺度 |
| 原生关节 | 4 | `/World/Excavator/Joints/{swing,boom,arm,bucket}` |

底盘由新场景的 `/World/ContractBaseAnchor` 固定在世界中。四关节初始角为新合同定义的零度，不沿用旧场景的角度偏置。独立挖掘机资产、旧场景、传感器资产均不修改。

所有 LiDAR 安装在 `swing_link` 下，相机会跟随 `boom_link`。保留旧实例名称、可见性、外壳模型、发射阵列和完整传感器参数，包括旧 `MyAiry_up` 的高位安装方式。RenderProducts 和创建 RenderProduct 的 OmniGraph 已重新指向新路径。

## 安装坐标如何换算

旧 GS USD 已把原始 PLY 点做过旋转和平移；新 GS USD 保留原始点坐标。直接复制父节点下的安装数字会装错位置。

构建器使用履带、驾驶舱、大臂各自的同序高斯中心，求原始坐标到旧几何坐标的刚体变换。必须点数相同，并逐点验证全量坐标误差小于 `1e-5 m`；不使用 ICP，也不允许通过缩放或形变强行匹配不同素材。

采用列向量记法：

```text
T_newBody_mount = T_newBody_raw · inverse(T_oldBody_raw) · T_oldBody_mount
```

由此保留传感器相对其所附着表面的坐标。构建报告还比较同一部件的所有高斯中心在新旧安装坐标系下的位置。首次构建最大误差约 `3.93e-7 m`，即约 `0.000393 mm`。

挖掘机根节点的世界位姿通过履带几何对齐旧环境而得，因此根节点世界旋转不是单位旋转。这个位姿属于未来的 `world → base_link` 外参；资产内部的公共 raw→base 变换、四个关节零位和 `platform_roll/pitch=0` 定义保持原样。不能把世界放置旋转再次乘入原始素材变换。

## 构建与验证

远端项目目录：`/root/gpufree-data/semantic/scripts/260920SensorVisualizer`。

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer
bash tools/run_cpu.sh cache_grid_asset.py
bash tools/run_cpu.sh build_combine_stage.py
bash tools/run_combine_validation.sh
```

已有生成结果时，构建命令加 `--rebuild`；只替换配置指定的新场景，并先备份至 `reports/combine_stage/backups/`。构建中断留下 `.building.usda` 时，应先检查并归档该文件再重试。不能把 donor 和 output 配成同一个文件。

- `config/combine_stage.json`：来源场景、目标资产、输出路径、部件角色映射及预期传感器数量。
- `tools/build_combine_stage.py`：发现传感器、验证共源几何、换算安装姿态、更新引用、构建固定锚点并保存独立场景。
- `tools/cache_grid_asset.py`：原样缓存官方网格地面 USD 与三张贴图，来源和指纹记录在 `assets/NvidiaGrid/source_manifest.json`。
- `tools/validate_combine_stage.py`：独立无窗口 Isaac 验证。临时关节姿态、测试 RenderProducts 和输出格式设置只写 Session 层，不保存到场景。
- `scenes/combine_scene_13_3dgs_contract.usda`：生成结果的项目内副本。相对引用按远端 `IsaacSim_Asset/combine_stage/` 解析；项目内副本用于留档，不是自包含资产包。
- `reports/combine_stage/build.json`：来源指纹、转换矩阵、各传感器新位置/四元数、参数比对和挂载误差。
- `reports/combine_stage/runtime.json`、`runtime.log`：运行验证结果和原始日志。
- `reports/combine_stage/bind_scene.png`、`combined_scene.png`：零位和组合关节姿态预览。

CPU 检查验证全部传感器属性（包括完整发射数组）、挂载位置、关系目标和关节零位。运行检查覆盖场景引用、四自由度原生 Articulation、14 个挂载的运动跟随、RGB 预览，以及 13 路 RTX 点云各至少两个新扫描帧。

2026-09-21 新实例验收通过：组合引用错误为 0，13 路各取得 2 个新完整扫描帧，单帧有效点数约 2.78 万～7.67 万；14 个挂载在测试姿态中的最大位置误差约 `1.79e-6 m`。最终进程退出码为 0，日志无 `[Error]`。运行报告同时要求数值检查通过与进程正常退出，避免把退出阶段崩溃误报为成功。

仍有安装环境/接口警告，包括无音频设备、PerfSDK 不可用、Fabric 字符串数组映射提示、CPU 回读性能提示，以及沿用关闭 Motion BVH 的提示。此次验证证明静态扫描与安装跟随可用，没有验收运动补偿、长时间采集或 ROS 联调。GUI 启动器通过 Shell 语法检查；本次实际渲染验收使用独立无窗口进程。

旧 FlatGrid 使用 NVIDIA HTTPS 资产，首次运行检查在加载阶段等待较久。新场景改为引用原样缓存的 `/root/gpufree-data/IsaacSim_Asset/environment_module_set/NvidiaGrid_6_0/default_environment.usd`；三张贴图一并保存，几何、材质和原有场景缩放保持不变。内置 `OmniPBR.mdl` 由 Isaac 安装提供。构建时读取旧 donor 仍可能出现网络引用警告；新场景的全部 USD 组合引用需通过运行验证。

## 接口边界

USD 装配测试使用 `GenericModelOutput` 读取点云。2026-09-21 后续 GUI 联调验证了旧 LiDAR Visualizer 自动发现新场景的四关节与 13 个雷达，并成功初始化 Scripted / Observe 两种模式。独立 ROS 接收进程收到全部 13 路非空 PointCloud2、各雷达 TF 与 `/clock`，退出码为 0。本次没有实际打开 RViz 验收显示，也没有验证新场景的 MCAP 录制、长时间运行或运动畸变补偿。

旧发布器仍使用 `world → swing_horizontal_coordinate → swing_coordinate → 各雷达` 的命名；不等于已经实现对方合同约定的完整部件 TF 接口。兼容旧项目的实时点云流程与后续完整合同接口迁移应分别验收。详细排障与证据见 `docs/reports/ros_entry/REPORT.md`，运行结果见 `reports/ros_entry/result.json`。

新项目使用 `swing/boom/arm/bucket` 四关节合同零位，后续接入采集时应使用这组定义，并发布实际的根节点世界外参及每个传感器安装变换。

## 本次部署范围

新实例为 `120.209.70.195:30729`。只写项目源码/配置/报告、生成的新场景及地面素材缓存；测试启动独立 Isaac 进程。未安装或升级系统库，未修改桌面组件和系统启动配置。

同步工具默认端口已更新为新实例，并排除 `diagnostics/`、`migration/`，避免将历史排障材料一起部署。SSH 凭据仍由用户交互输入或使用已有密钥，不写入项目文件。

实现参考：[OpenUSD XformCache](https://openusd.org/release/api/class_usd_geom_xform_cache.html)、[NVIDIA Kit --exec 示例](https://docs.omniverse.nvidia.com/extensions/latest/ext_scene-optimizer/user-manual.html)。具体可用性以本实例已安装的 Isaac 6.0.1 API 和运行报告为准。
