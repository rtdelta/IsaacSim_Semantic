# combine_scene_11：环境整体放大 2.5 倍

远端主文件：

`/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_11.usda`

说明、预览、采集样例和验收记录：

`/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_11_data/`

这是从 stage 10 派生的新场景。stage 10、Excavator05、环境包和共享传感器资产没有修改。该目录中的本地 USD 是远端文件的镜像，其相对依赖沿用远端布局，应在远端 Isaac Sim 中打开。

## 打开与使用

1. 在 Isaac Sim 中选择 File → Open，打开 `combine_scene_11.usda`。
2. 总览相机仍使用 `/World/Stage10Overview`，已后移以容纳扩大后的环境。保留原节点名称和路径，是为了保持场景层级及绑定关系。
3. 点击 Play，原有 `/World/Stage10SensorPipeline` 启用 14 个传感器 RenderProduct。挖掘机仍通过 Payload 引用原有 `Excavator_Fangshan_05.usda`，加载和装配无需 Python 或 `.sh` 脚本。
4. 如需启动新的 Isaac 进程，可使用本目录的 `IsaacSim_Stage11.desktop`；它直接执行 Kit 二进制，并沿用 stage 10 已验证的 RTX 雷达库路径。启动后通过 File → Open 打开主文件。
5. 如需保存短时点云与相机样例，可在 Isaac Script Editor 运行 `capture_sensors.py`。它把 13 份雷达 NPZ、相机 PNG 和坐标说明写到本目录的 `captures/<时间>/`，不会保存或修改 USD。

仍保留已有 NVIDIA 在线 USD/材质依赖；本次在远端 Isaac 中解析成功。

## 缩放规则

缩放中心是挖掘机根节点在世界 Z=0 平面上的投影：

```text
C = (-1.183046737960458, 1.5663421562003612, 0) m
p11 = C + 2.5 × (p10 − C)
```

以下几何整体按 X/Y/Z 均匀缩放，包含自身尺寸及相对中心的空间距离：

| 节点 | 处理 |
|---|---|
| `/environment_Fangshan_02` | 根缩放从 `(1,1,1)` 改为 `(2.5,2.5,2.5)`，同时调整根平移；栏杆、标记物及其间距统一放大。内部天空灯通过单独补偿排除。 |
| `/FlatGrid/Environment` | 对可见网格地面的父节点应用同一缩放与平移，实际有限平面从 `100×100 m` 变为 `250×250 m`。 |
| `/FlatGrid/GroundPlane` | 对碰撞平面组应用同一变换；原无限水平碰撞平面仍位于世界 `Z=0`，不存在有限边长增加的问题。 |

环境根的新平移为 `(1.3720310583262314, -0.5385543934757115, 2.737092749355981) m`，原旋转保持不变。两个地面组的新平移为 `(1.774570106940687, -2.349513234300542, 0) m`。

只在新场景层覆盖变换，不改写环境源文件、顶点、纹理或共享资产。子节点不再重复施加 2.5 倍缩放。原隐藏及禁用内容保持原状态，没有自动启用 `changjing4`。

## 保持不变的内容

- `/World/Cube` 的所有属性保持原样，仍为 1 m 立方体；尺寸、位置和姿态均未变化。
- 挖掘机及全部传感器的父子层级、安装位姿、初始姿态和关节配置保持原样。五个部件内部的 GS/Mesh 配准缩放仍为 2.4，并未再乘以 2.5。
- `MyOS0_up` 继续保留原父子关系和安装位姿，没有重新解释其现实作用。
- 雷达量程、扫描参数、相机内参、RenderProduct 路径和采集管线保持原样。环境变远后，图像与点云覆盖范围自然变化。
- `/Environment/defaultLight` 和 `/FlatGrid/SphereLight` 保持原样；环境包内 `/environment_Fangshan_02/DomeLight` 添加父空间补偿矩阵，抵消环境缩放，使其世界位姿及所有灯光、天空贴图参数保持原样。
- 场景仍为 `metersPerUnit=1`、Z 向上。物理场景、底盘固定约束和原有物理参数未调整。
- 网格材质及纹理设置没有修改；视觉网格线受材质映射方式影响，不应直接把每一格当作缩放后的长度标尺。尺寸验收使用世界坐标和 1 m Cube。

## 验收与对比

结构检查对比实际加载后的两个场景：检查环境 Mesh 的世界包围盒、环境子节点世界变换、未缩放对象世界变换、全部设备参数与父子层级、灯光参数和世界变换。另对 Cube、挖掘机、约束、管线、物理场景和 Render 子树做完整 USD 定义比较，并对 74 个原有输入文件做 SHA-256 前后检查。

- `structural_validation.json`：127 个环境 Mesh 的前后尺寸和逐项误差，包括网格地面。
- `runtime_validation.json`：Isaac Sim 中重新打开、总览图、13 路雷达各至少 5 帧扫描、1280×720 相机输出及场景文件未被测试保存的检查。
- `final_validation.json`：文件哈希、保持不变的子树、缩放误差与验收总结果。
- `overview_before_same_camera.png`、`overview_after_same_camera.png`：使用完全相同的总览相机拍摄，便于直接比较围栏与不变的挖掘机、Cube。
- `boom_camera.png`：挖掘机上相机在新环境中的输出。
- `manifest.json`：精确缩放中心、节点范围、传感器路径和安装矩阵。
- `scene_changes.diff`：stage 10 到 stage 11 的场景层差异。

本次验证针对环境缩放后的加载、结构和短时传感器输出。原场景的地形贴合、物理参数及真实尺寸标定没有新增调整；运行环境已有的运动点云 Motion BVH 提示仍存在，本次没有把静态短测解释为运动畸变验证。

构建和 QA Python 文件仅用于复现、审计，不是打开该场景的前置步骤。
