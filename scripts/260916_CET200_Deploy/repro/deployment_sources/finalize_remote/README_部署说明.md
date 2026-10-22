# CET200 云端 Isaac Sim 资产

部署目录：`/root/gpufree-data/IsaacSim_Asset/excavator_module_set/CET200/`

本次部署来自 https://github.com/vmc-motion/cet200 ，固定版本为
`8ce4c1428d615079c480185eeef77c54f00d5c6a`，Apache-2.0 许可。
验证环境：Isaac Sim `6.0.1-rc.7+release.42383.32955d8d.gl`。

## 如何打开

### 直接查看完整预览场景

在已经启动的 Isaac Sim 中选择 File → Open：

```text
/root/gpufree-data/IsaacSim_Asset/excavator_module_set/CET200/usd/CET200_preview.usda
```

该场景包含挖掘机 Payload、地面、灯光、相机和 PhysicsScene。
若视角没有自动切换，选择 `/World/Camera`，或选中 `/World/CET200` 后按 F 聚焦。
预览场景使用零重力、固定底座，方便检查关节；按 Play 后不会自动执行动作。
不需要通过 shell 脚本启动模型，也不需要运行上游 AGX 示例。

### 在自己的场景中作为 Payload 使用

在 Stage 中创建或选中承载资产的 Xform，使用 Add → Payload / Add Payload，选择：

```text
/root/gpufree-data/IsaacSim_Asset/excavator_module_set/CET200/usd/CET200.usda
```

默认根节点为 `/CET200`。该文件是资产入口，不包含地面、灯光或 PhysicsScene。
宿主场景负责提供 PhysicsScene、重力和照明。
它通过相对路径引用同目录下 `imported_normalized/` 的几何、材质和物理层。
复制或传递资产时必须保留整个 `usd/` 文件夹，不能只复制入口 usda。

也可在 Isaac Sim Script Editor 中执行下面的代码添加 Payload；这只是可选加载方式：

```python
import omni.usd
from pxr import UsdGeom
stage = omni.usd.get_context().get_stage()
robot = UsdGeom.Xform.Define(stage, "/World/CET200").GetPrim()
robot.GetPayloads().AddPayload(
    "/root/gpufree-data/IsaacSim_Asset/excavator_module_set/CET200/usd/CET200.usda"
)
```

## 目录

- `source/`：完整上游 Git 仓库；原文件未修改。
- `source/cet200_description/urdf/`：原始 URDF / Xacro。
- `source/cet200_description/meshes/`：原始分部件 DAE / STL。
- `source/exchange_formats/`：STEP、整机 GLB、分部件 GLB。
- `source/docs/cet200_spec.xlsx`：上游规格表。
- `prepared/cet200_description/`：供当前导入器使用的 DAE 兼容副本。
- `usd/CET200.usda`：供 Reference / Payload 使用的资产入口。
- `usd/CET200_preview.usda`：直接打开查看的预览场景。
- `usd/imported_normalized/`：导入器生成的 USD 依赖层。
- `tools/`：本次转换、检查脚本；日常打开资产无需执行。
- `reports/`：转换配置、源版本、几何校验、运动测试、截图和日志。
- `DEPLOYMENT.json`、`SHA256SUMS.json`：部署索引及文件校验清单。

## 尺寸、零位与关节

采用上游 CET200 的规则，所有整体缩放为 1，不套用方山 05 资产的 2.4 倍缩放。
单位为米、千克，Z 向上。模型是虚构的 20 吨级挖掘机，不能直接视为真实方山挖掘机的尺寸标定结果。

四个主要关节默认角度为 0。零位是上游 URDF 定义的姿态，并非四节完全水平伸展。

| 关节 | 含义 | URDF 关节坐标系中的正轴 | 范围 |
|---|---|---|---|
| Hinge_Slew | 上车回转 | +Z，右手定则 | 连续旋转 |
| Hinge_Boom | 动臂 | +Y，右手定则 | -25.382° 至 64.572° |
| Hinge_Arm | 斗杆 | +Y，右手定则 | -80.214° 至 37.128° |
| Hinge_Bucket | 铲斗 | +Y，右手定则 | -70.818° 至 101.414° |

在预览场景中的关节路径为 `/World/CET200/Physics/<关节名>`。
按 Play 后，可在关节属性的 Angular Drive → Target Position 中输入角度（USD 界面单位为度）。
例如给 Hinge_Slew 输入 10，可观察正向回转；停止仿真后恢复初始姿态。
输入值应保持在上表范围内；URDF 内的角度单位为弧度。

该资产有 27 个刚体、26 个转动关节，后者包含 4 个主要关节和履带轮系关节。
导入时合并固定关节，原始 32-link / 31-joint 拓扑保留在源 URDF 中供查阅。
底座刚体是合并后的 `Geometry/TF_Origin`，预览中的 articulation 根为 `/World/CET200/Geometry`。
履带带体沿用源 URDF 的固定可视模型，不是可独立运动的履带板链。

## 本次适配与边界

1. 保留源几何和 URDF 零位、转轴、限位，导入时合并固定节点并固定底座。
2. 当前版本内置 DAE 转换代码对嵌套节点采用 `local @ parent` 累积，
   与这些 DAE 列向量矩阵的 `parent @ local` 顺序不同，直接导入会导致部件偏移。
   在 `prepared/` 中将源 DAE 节点展开为单层、写入正确累计矩阵，未更改几何顶点和材料。
   原始仓库和 Isaac Sim 安装目录均未修改。
3. 四个主要关节增加临时 acceleration 位置驱动：stiffness=1000、damping=100、maxForce=∞。
   这些值用于关节观察，不代表真实液压系统，也不用于验证源 URDF 的力矩上限。
4. 预览场景重力为 0，资产本身没有覆盖宿主场景的重力；固定底座、自碰撞关闭。
5. 沿用源 URDF 的 23 个 collision 定义，未为缺少 collision 的上车、动臂、斗杆等补制碰撞体。
   后续做全机接触或防碰撞，需要另外检查并补齐碰撞几何。
6. 未迁移 AGX 的液压、履带链、土壤与颗粒系统；未添加你的 13 个雷达、ROS 2 / TF / MCAP 发布逻辑。
   现有方山场景和采集脚本未替换。

## 已验证

- 资产默认根节点、Payload 组合以及全部 USD 依赖解析成功。
- 与原始 URDF / DAE 对比，可见顶点数均为 300,505；整体可见几何包围范围最大差异约 6.9e-8 米。
- 四个主要关节的零位轴心、正向轴与源 URDF 一致，轴心差异低于 2.1e-7 米。
- 在原生 Kit / PhysX 中运行，四个关节两组正负目标角测试通过，最大目标误差小于 0.008°。
- 运动测试中的关节连接点误差小于 0.002 毫米。
- 实际渲染预览见 `reports/CET200_preview.png`。

测试覆盖几何导入和短时关节运动，不代表完成了真实动力学、液压或地形接触验证。
