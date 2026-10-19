# 从 mesh 原始部件到当前挖掘机可视化资产：精确重建交接报告

版本：2026-10-12 / scene18_mesh_handoff_v1。交付对象：接手资产装配、坐标对接和验收的同事。

## 1. 交接结论与复现边界

**本报告配套交接包已经完成实际重建：从封存的五部件 mesh 输入出发，在独立目录生成的主 USDA 和五个几何 USDC，与当前远端使用的六个资产文件逐字节一致。** 不是依靠截图判断“差不多”，也不是仅比较包围盒。

本次采用的输入是 `inputs/waji_mesh_corrected.usdc`，SHA256：

```text
53098b1b4954c5fa88298569950941389e9a7c718584d23a85e379af477e28a0
```

重建验收记录见 [evidence/rebuild_verification.json](evidence/rebuild_verification.json)。其中 `composed_usda_identical`、`all_six_usd_files_byte_identical`、`passed` 均为 `true`；五个部件各 11 项原始数值属性共 55 项比较全部一致。

### 1.1 当前产物具体指什么

- **独立挖掘机资产**：`Excavator_Mesh_Contract/Excavator_Mesh_Contract.usda` 及 `geometry/` 五个文件。包含几何、顶点颜色材质、部件坐标系、刚体/关节声明。这是本报告的精确重建对象。
- **当前使用场景**：`combine_scene_18_terrain_fisheye_mesh.usda`，在 `/World/Excavator` 载入上述资产，并叠加世界位姿、传感器安装、相机、场景环境等内容。
- **运行时状态**：控制脚本施加的关节角度、整机姿态、Session 层修改、临时传感器调整不自动包含在磁盘 USDA 中。本报告冻结的是 2026-10-12 核验的磁盘资产与场景默认状态，不能据此还原未保存的临时操作。

本交接包完整包含第一项及其输入和重建方法，记录第二项的场景根层、依赖 USD 层清单、实际根位姿和传感器矩阵。背景、传感器所有外部资源没有完整打包，不能把它作为完整场景的离线发行包。相同资产也不意味着跨显卡、渲染器、灯光、随机采样设置得到逐像素一致图像。

### 1.2 “raw material”必须明确到哪一级

| 素材级别 | 文件与实际内容 | 本次用途及确定性 |
|---|---|---|
| 更早的合并 mesh | `sim_Fangshan_01/mechanic_parts_set/mesh_parts/拆分成五部分的mesh.usd`；实际只有 `/World/mesh_` 一个 Mesh | 历史溯源；尚未建立完全可重放的拆分、孤立点归属、顶点排序及全部属性转换记录 |
| 当前五部件 mesh 输入 | `Sim_Fangshan_02/waji_mesh_corrected.usdc`；五个 Mesh 已在同一 corrected 坐标系内 | **本包封存的正式重建起点；到当前资产的链路已逐字节复现** |
| 装配后资产 | `Excavator_Mesh_Contract` | 金标准及交付目标 |

更早合并 mesh 的 SHA256 是 `99d2a09768875f0ca16b21101e3a05177dc427aa518e7ca82b3e3c11bba37703`。其 metadata 为 Y-up、`metersPerUnit=0.01`；当前五部件输入为 Z-up、`metersPerUnit=1`。历史数值变换并非“按 metadata 缩放 0.01 再改为 Z-up”即可重现，不应凭文件名或单位标签重新导入转换。

旧的组件分类记录可辅助追溯，但不足以证明与当前 Blender 导出的顶点顺序、未被三角形引用的点、顶点分组、法线完全相同。因此，如果接手人手里**只有更早的合并文件**，不能承诺仅凭一组刚体矩阵就精确生成当前五部件输入。请直接使用本包封存的五部件 raw material；从扫描/重建软件到该素材的制作历史不在已验证闭环内。

## 2. 交付目录与文件职责

```text
handoff/
├─ MeshRawToExcavator_Reconstruction_Handoff.md  本报告
├─ README.md                                  最短操作流程
├─ package_manifest.json                      文件大小和 SHA256；不含自身
├─ verify_package.py                          接收端校验整个包
├─ rebuild.py                                 从五部件素材重建并自动验收
├─ launch_usd.py                              使用已有 Isaac USD SDK；不启动 Kit
├─ reconstruction.json                        全精度矩阵、原始路径、数组/关节定义
├─ kinematics_contract.json                   运动学的逻辑轴、关节平移和零位
├─ inputs/
│  ├─ waji_mesh_corrected.usdc                 原样封存的五部件输入
│  └─ rig_template.usda                       精确装配蓝图，无内嵌顶点数据
├─ reference/Excavator_Mesh_Contract/          当前部署资产的金标准
├─ scene_context/                            scene18 根层，非完整场景包
├─ evidence/                                 来源事实、旧验收、新重建验证
└─ provenance/                               最初转换/配准/验收源码及历史报告
```

`rig_template.usda` 原样保留六个目标文件中主 USDA 的所有结构、数值精度、xformOpOrder、关节属性、相对 payload 路径和历史 metadata。它是**装配蓝图**，不含几何数组；重建时另外五个 USDC 都从输入 mesh 重新生成。蓝图明确指定了各部件的原点，不能从 mesh 表面或包围盒唯一推导关节轴心。

`reconstruction.json` 是供其他语言/引擎实现时使用的机器可读数据字典；当前 Python 重建直接复用蓝图以避免再次进行欧拉角换算与数值舍入。两者的矩阵均由实际部署资产提取。若未来修改其中一份，应建立新版本并同步另一份，不可悄悄破坏本版本的精确复现含义。

`provenance/` 中旧脚本包含历史绝对路径和首次部署操作，仅作审计和理解依据；交接时执行 `rebuild.py`，无需再跑历史配准或首次部署脚本。

## 3. 原始 mesh 到目标部件的唯一映射

源文件中路径的末两级同名是实际 USD 层级，并非笔误：上一层是容器，下一层是 Mesh。

| 机械部件 | 正式 frame | 源 Mesh 路径 | 顶点数 | 三角面数 |
|---|---|---|---:|---:|
| 履带底盘 | `track_link` | `/root/track_mesh/track_mesh` | 101771 | 200806 |
| 上车/驾驶室 | `swing_link` | `/root/operator_cab_mesh/operator_cab_mesh` | 116099 | 229912 |
| 大臂 | `boom_link` | `/root/boom_mesh/boom_mesh` | 57635 | 114781 |
| 小臂 | `arm_link` | `/root/small_arm_mesh/small_arm_mesh` | 23764 | 47013 |
| 带完整斗齿铲斗 | `bucket_link` | `/root/bucket_only_full_teeth_mesh/bucket_only_full_teeth_mesh` | 18406 | 36356 |
| 合计 | | | **317675** | **628868** |

用户已明确选择完整斗齿 mesh 铲斗，故不按旧 3DGS 的 `bucket_without_teeth` 切除斗齿。这是允许的几何内容变化，并不是装配误差。

源 Mesh 及其祖先在当前输入中的总变换为单位矩阵，顶点直接位于共同的 corrected 数值坐标系；每个 Mesh 的数值原点并非相应关节原点。源文件附带的灯光/相机不进入新独立资产。

保留的原始数据包括：`points`（float32）、`faceVertexCounts`（int32）、`faceVertexIndices`（int32）、`normals`（float32，faceVarying）、`extent`、RGBA 顶点色 `primvars:Col`、五个 `primvars:Group_*` 浮点分组数组、`subdivisionScheme` 及 Blender 数据名。实际数组类型、形状和 SHA256 全部在 `evidence/source_facts.json → parts → source_attributes` 中。

禁止为了“整理模型”进行合并顶点、删除孤立点、简化三角形、重新三角化、重算法线、Apply Transform、Set Origin to Geometry 或颜色空间二次转换。这些操作都可能改变当前金标准。

## 4. 坐标、原点、缩放：完整数值链路

### 4.1 五种坐标含义

1. **corrected mesh 坐标**：输入 `points` 的数值坐标，共享同一个重建空间。
2. **raw reconstruction 坐标**：旧资产约定的重建坐标，作为历史装配标定中间空间。
3. **各部件 body 坐标**：`track_link`、`swing_link` 等，原点是装配定义的控制/连接原点。
4. **挖掘机根/base 坐标**：独立资产 `/Excavator`。未放入场景时根为单位变换，底盘 frame 与根重合；整体为右手坐标系。
5. **场景世界坐标**：场景 `/World/Excavator` 的父空间。scene18 中根既有平移又有轻微旋转，不能用单位旋转代替。

### 4.2 统一矩阵约定

本资产的 `Gf.Matrix4d` 采用**行向量、平移放最后一行**。齐次点计算为：

```text
p_world = p_corrected × C × V_i × B_i(q) × W

C       corrected → raw 的固定矩阵
V_i     raw → 第 i 个部件局部坐标的固定矩阵
B_i(q)  第 i 个部件 → 挖掘机根的姿态；零位时为 B_i(0)
W       挖掘机根 → 世界的姿态
```

对列向量库，完整等价式是：

```text
p_world_column = Wᵀ × B_i(q)ᵀ × V_iᵀ × Cᵀ × p_corrected_column
```

不能只倒转乘法顺序却不转置矩阵，也不能把 JSON 最后一行的平移误读为最后一列。

### 4.3 固定的 corrected → raw 矩阵 C

```text
[[ 0.44026025201894387,  0.22643141878703688, -0.8688496550487352,   0],
 [ 0.8896029756966128,   0.021008171853434232, 0.4562512491458061,   0],
 [ 0.1215625605355035,  -0.9738005284972211,  -0.19218500090950372, -0],
 [-0.6468378777800076,   0.39413573369728344,  1.6142118463398636,   1]]
```

历史生成时，使用同源 raw/corrected 3DGS 对应点作刚体配准：质心去中心、构造交叉协方差、SVD 求旋转并处理反射，求出平移后取逆得到 C。履带 70566 个对应点用于标定，驾驶室/大臂/小臂作为交叉核验；最大对应误差约 `1.66e-7` 源数值单位。合并 mesh 的旧验证为全量毫米网格对应及 128 个最近点抽查，不能把它写成全部顶点一一对应的证明。

**重建不要重新运行 SVD/ICP。** 当前目标就是已经采用这组浮点数的资产，不是重新求“更精确”的配准；本包冻结 C，运行时和重建时不再依赖任何 3DGS 文件。

### 4.4 raw → base 标定以及 2.4 倍缩放

逻辑标定输入如下，采用列向量 RPY：

```text
translation_m = [3.20352, -0.34217, 2.04934]
roll_pitch_yaw_deg = [-103.98993, -5.69811, 61.29154]
R = Rz(yaw) × Ry(pitch) × Rx(roll)
uniform_scale = 2.4
A_column = [ 2.4 × R   translation ]
           [ 0 0 0          1      ]
```

其行向量形式 A 就是 `track_link/Visuals` 的完整矩阵。对于其他部件：

```text
V_i = A × inverse(B_i(0))
```

五个 V_i 的左上 3×3 完全相同：

```text
[[ 1.1471508209952654,  2.094579558347602,    0.23828862256149497],
 [ 0.6199494079352975, -0.07590455015254771, -2.3173047341398183 ],
 [-2.014871639953911,   1.16917704947476,    -0.5773363850398934 ]]
```

平移在各 V_i 的最后一行：

| frame | tx | ty | tz |
|---|---:|---:|---:|
| track_link | 3.20352 | -0.34217 | 2.04934 |
| swing_link | 3.20352 | -0.34217 | 1.4493399999999999 |
| boom_link | 3.5775200000000003 | -0.07216999999999996 | 0.4953400000000001 |
| arm_link | -0.97248 | -0.006169999999999953 | -2.70266 |
| bucket_link | -2.19848 | 0.08683000000000007 | -0.04065999999999992 |

这 2.4 倍已经在 Visuals 矩阵里。新 mesh 的 points 不烘焙变换，MeshAlignment 只做上述固定配准，body/root 不再补一个 2.4 scale。零位下所有部件均满足 `C × V_i × B_i(0) = C × A`，因此仍在同一个装配位置；关节运动时改变 B_i，几何相对于正确的部件原点旋转。

法线保持原始 faceVarying 数组，由 USD/渲染链按几何变换处理。若自行烘焙到别的格式，应按逆转置规则处理法线；那是新格式导出，不属于此处已通过字节一致的重建流程。

## 5. USD 架构、零位和机械连接

### 5.1 实际层级

```text
/Excavator                              defaultPrim、component
├─ track_link                           底盘 rigid body / articulation root
│  └─ Visuals                           V_track
│     └─ MeshAlignment                  C
│        └─ Geometry                    payload ./geometry/track_link.usdc
│           ├─ Mesh                     原始点、拓扑、法线、颜色
│           └─ Looks/VertexColor        Surface + Color shaders
├─ swing_link                           上车 rigid body，同样的 Visuals 链
├─ boom_link                            大臂 rigid body
├─ arm_link                             小臂 rigid body
├─ bucket_link                          铲斗 rigid body
└─ Joints
   ├─ swing                            track → swing，Z
   ├─ boom                             swing → boom，Y
   ├─ arm                              boom → arm，Y
   └─ bucket                           arm → bucket，Y
```

五个 body 在 USD 中是**平级节点**。机械链由 `physics:body0/body1` 和关节局部坐标定义，不能把小臂直接拖到大臂节点下面并保留同样的 local transform，这会引入二次继承。`customData.parentFrame` 表示语义/运动学父坐标系，不等于 USD 父 prim。

根元数据：`metersPerUnit=1`、`kilogramsPerUnit=1`、`upAxis=Z`。独立资产根不带额外世界放置变换。

### 5.2 各部件零位原点（相对于挖掘机根，米）

| frame | translate XYZ | orient |
|---|---|---|
| track_link | `(0, 0, 0)` | `(w,x,y,z)=(1,0,0,0)` |
| swing_link | `(0, 0, 0.6)` | 同上 |
| boom_link | `(-0.374, -0.27, 1.5539999999999998)` | 同上 |
| arm_link | `(4.176, -0.336, 4.752)` | 同上 |
| bucket_link | `(5.402, -0.42900000000000005, 2.09)` | 同上 |

body 使用 `double3 xformOp:translate`、`quatd xformOp:orient`，顺序为 `[translate, orient]`。零角度定义为这套重建素材的 bind pose，不等于大臂水平、小臂竖直、斗底水平，也不补旧 URDF/bag_2 的角度偏移。

### 5.3 关节定义

以下是逻辑/装配十进制定义。USD `physics:localPos0` 的实际存储类型为 `point3f`，存在 float32 表示差异；完整实际值见 `reconstruction.json → joints`。不要用格式化成少量小数的文档替代该文件或蓝图。

| joint | body0 → body1 | axis | localPos0（body0 空间，米） |
|---|---|---|---|
| swing | track_link → swing_link | Z | `(0, 0, 0.6)` |
| boom | swing_link → boom_link | Y | `(-0.374, -0.270, 0.954)` |
| arm | boom_link → arm_link | Y | `(4.550, -0.066, 3.198)` |
| bucket | arm_link → bucket_link | Y | `(1.226, -0.093, -2.662)` |

四个关节均为 `PhysicsRevoluteJoint`；`localPos1=(0,0,0)`，`localRot0/1` 均为单位四元数，`jointEnabled=true`，`collisionEnabled=false`。正角遵守所列局部正轴的右手定则。数学/API 的 radians 与界面/此逻辑表的 degrees 应显式转换；USD angular drive 的 targetPosition/targetVelocity 使用度/度每秒。

运动学列向量递推为：

```text
T_track = I
T_swing(q)  = T_track × Translate(0,0,0.6) × RotateZ(q_swing)
T_boom(q)   = T_swing × Translate(-.374,-.270,.954) × RotateY(q_boom)
T_arm(q)    = T_boom  × Translate(4.550,-.066,3.198) × RotateY(q_arm)
T_bucket(q) = T_arm   × Translate(1.226,-.093,-2.662) × RotateY(q_bucket)
```

写入平级 USD body 的矩阵是这些根相对矩阵的转置，即 `B_i(q)=T_i(q)ᵀ`，不是只写该关节的单步局部变换。这样父关节转动时下游部件与其挂载传感器才能共同跟随。实际物理 Articulation 驱动与这种规定运动属于不同执行路径；本报告规定资产的坐标与关节含义，不把预定运动验证当作动力学验证。

当前采集策略保持 cab–track/swing 的初始角度是控制器行为；资产内该关节仍是可旋转关节。整机平移、Yaw/Pitch/Roll 在根位姿 W 上表达，不需要新增五部件内的关节。

### 5.4 物理属性的边界

每个 body 声明 `PhysicsRigidBodyAPI`、`PhysicsMassAPI`、`PhysxRigidBodyAPI`；`track_link` 另有 `PhysicsArticulationRootAPI`。质量 1、对角惯量 `(1,1,1)`、质心 `(0,0,0)`、重力关闭；angular drive stiffness 100000、damping 1000、maxForce 1000000，targetPosition/Velocity 为 0，type 为 force。

这些是历史控制/验证占位值，**不是实际挖掘机质量、惯量、碰撞或液压参数**。没有添加新的碰撞网格或实测硬件角限。这里的原点也不是通过质量计算得到的真实重心。

蓝图仍含 `version=3dgs_contract_v1` 及旧 `scope` 字符串，它们是沿用坐标契约的历史标签；不表示当前几何仍为 3DGS，也不代表运行脚本不能对根做 Pitch/Roll。保留它们是为保证当前文件逐字节一致；新版本如整理这些标签，应另立版本。

## 6. 几何与材质的生成步骤

重建程序按以下顺序执行：

1. 对输入 mesh 和蓝图进行 SHA256 校验；输出目录已存在则拒绝覆盖。
2. `Usd.Stage.Open` 打开输入，`Stage.Flatten` 得到可复制的已组合属性层。
3. 原样复制装配蓝图为 `Excavator_Mesh_Contract.usda`；其中相对 payload 指向将生成的五个几何文件。
4. 为每个部件创建 `geometry/<frame>.usdc`，定义 defaultPrim `/Geometry` Xform，Z-up，1 米单位。
5. `Sdf.CopySpec` 将唯一映射表中的源 Mesh 完整复制为 `/Geometry/Mesh`。不修改点坐标、索引、法线、原始颜色/分组等。
6. 从 `primvars:Col` 的 RGB 三列创建 `primvars:displayColor`，类型 Color3fArray，插值为 `vertex`；不对线性颜色再做 gamma 变换。原始 RGBA 的 Col 同时保留，已确认全部 alpha=1。
7. 创建 `UsdPreviewSurface` 材质，roughness=0.8、metallic=0；`UsdPrimvarReader_float3` 读取 `displayColor` 并连接 surface 的 diffuseColor；通过 `UsdShade.MaterialBindingAPI` 绑定 Mesh。颜色来自顶点，不依赖额外 UV/纹理图。
8. 保存五个 USDC，然后加载完整重建资产，对照金标准执行已组合 USD 全文、原始数值数组和六个文件字节校验，输出 `rebuild_verification.json`。

单个几何文件内的完整节点为 `/Geometry/Mesh`、`/Geometry/Looks/VertexColor`、`.../Surface`、`.../Color`。材质输出与 shader 输出连接类型也由重建代码固定。

## 7. 一条顶点和一次关节动作的数据流

以大臂某个原始顶点为例：

```text
输入 /root/boom_mesh/boom_mesh.points[k]（float32）
  → 不改数组，复制进 geometry/boom_link.usdc 的 /Geometry/Mesh.points[k]
  → payload 进入 /Excavator/boom_link/Visuals/MeshAlignment/Geometry/Mesh
  → C 将 corrected 数值映射回 raw 标定坐标
  → V_boom 将 raw 坐标转到大臂关节原点，且包含唯一的 2.4 倍缩放
  → B_boom(q) 应用回转及大臂关节姿态，得到根坐标
  → W 放置到 scene18 世界空间
  → 渲染器消费已组合的世界几何、法线和顶点色材质
```

若大臂角度改变，C、V、原始 points 和材质均不变；`B_boom`、`B_arm`、`B_bucket` 依次更新，三者围绕正确的连接链移动。安装在上车的传感器跟随 swing 和根；挂在大臂的相机还会跟随大臂。不能为“跟随父件”去逐帧改 mesh 的 points，也不能把 root/world 变换重复写进 body 变换。

对于 TF/外部可视化接收端，应明确使用的是上述 body frame 还是 corrected mesh frame。如果对方直接拿输入 mesh 顶点配 body TF，必须先应用 `C × V_i`；否则虽然双方 TF 一样，几何仍会错位。**本次 mesh 转换的核心就是把这段固定几何外参显式保留在 Visuals/MeshAlignment 下。**

## 8. 放回当前 combine scene 的方法

远端正式资产目录：

```text
/root/gpufree-data/IsaacSim_Asset/excavator_module_set/Excavator_Mesh_Contract/
```

远端当前场景：

```text
/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_18_terrain_fisheye_mesh.usda
```

scene18 由 scene17 根层复制而来，只对 `/World/Excavator` 的 payload 作显式替换，并新增转换记录 metadata。根层的 subLayer 仍为 `./combine_scene_15_surround_fisheye.usda`；不能只拷贝 scene18 文件就认为获得整个场景。

强层 payload 的目标为：

```text
../excavator_module_set/Excavator_Mesh_Contract/Excavator_Mesh_Contract.usda
```

若在同一旧场景上自行替换，使用 `payloadList.explicitItems` 替换原列表，不要简单 Add/Append 一个新 payload，让旧 3DGS 和新 mesh 同时组合进来。另存新文件，不覆盖同事的源场景。

scene18 的根世界平移是 `(-0.5734957041467448, 1.4685478977484074, 0.5559421923906651)`；根四元数 **wxyz** 为 `(0.9993614882264588, 0.021258424667840926, 0.01655695633207031, 0.023464066728874106)`。不要误当成 xyzw。完整 W 矩阵见后附数据表和 `reconstruction.json`。

原有 13 路 OmniLidar、4 路 Fisheye Camera、其他相机和安装节点均保留。四鱼眼的 USD 名称是 `FisheyeFront/FisheyeRear/FisheyeLeft/FisheyeRight`，其中历史 USD `Rear` 名称不能因为 ROS/display 使用 back 就顺手改掉。全部实际传感器路径、局部/世界矩阵见 `evidence/source_facts.json → scene → sensors`；其中 `body_relative_matrix_row` 明确统一相对于 swing_link，连 boom 上的普通 Camera 也按该空间导出，仅作对照。

`scene → dependencies` 记录当时参与组合的 20 个 USD 层及容器文件哈希。USDZ 内层用容器路径和容器 SHA256 识别；这是**USD 层依赖清单**，不是所有纹理、MDL 与引擎依赖的完备离线打包清单。要复现整个背景和所有传感器参数，应另行交付该清单对应的完整资源目录。当前包重点保证挖掘机五部件资产及其装配契约。

## 9. 同事实际操作流程

### 9.1 接收和校验

完整解压本交接包，不单独挑选几个脚本。先执行：

```bash
cd /path/to/handoff
python3 verify_package.py
```

要求 `passed: true`。文件哈希是本交接版本的一致性证据，不是安全来源认证。

### 9.2 重建

已验证环境：Linux 上现有 Isaac USD SDK，Python 3.12.13、OpenUSD 0.25.11、NumPy 2.3.1。不需要打开 Isaac GUI，不需要 GPU、Blender、ROS 或 3DGS 输入；不从外部下载任何库。

```bash
python3 -I -S -B launch_usd.py --isaac-root /root/isaacsim rebuild.py --output /root/gpufree-data/semantic/scripts/260920SensorVisualizer/mesh_scene18/my_reconstructed_excavator
```

输出目录必须不存在。若 Isaac 安装目录不同只改 `--isaac-root`；launcher 针对当前 Linux/Python 3.12 安装布局。另有已配好的 OpenUSD/NumPy 环境时可直接 `python rebuild.py --output 新目录`，不需要 launcher。其他 SDK 的数值/组合内容可以校验，但不能预先承诺不同版本的二进制序列化字节仍相同。

### 9.3 验收

检查新目录中的 `rebuild_verification.json`：

- `passed=true`：已组合 USD 内容与金标准相同，所有保留的源数值属性相同。
- `all_six_usd_files_byte_identical=true`：主 USDA 和五个 USDC 哈希/字节相同。本次实际重建已达到。
- 如果前者 true、后者 false，不能称文件字节相同；应核对 SDK 版本和序列化差异。
- 打开新主 USDA，再按第 8 节将其接入另存的场景；检查 root、传感器挂载和 Session 层状态。

`manifest.json` 是旧构建时的时间、绝对路径和备份记录，留在 reference 目录作溯源，重建不伪造一份“相同历史”。要直接取得整个部署目录连这份记录都字节相同，可复制 `reference/Excavator_Mesh_Contract/`；要证明 raw→资产生成则运行上述重建。

### 9.4 避免常见误差

| 错误操作 | 后果 | 正确依据 |
|---|---|---|
| 按更早 raw 的 0.01 单位再缩放当前输入 | 100 倍尺寸错误 | 使用封存 corrected 输入，2.4 只在 V 中出现一次 |
| 将每个 mesh 重心设为原点 | 关节旋转中心改变 | 保留原始 points，原点由 body/Visuals 定义 |
| 将平级 body 改成嵌套子级 | 位姿重复继承 | 保留五个平级 body 和关节关系 |
| 省略 C 或把 C 当 raw→corrected | 整机位置、方向错位 | 采用固定 corrected→raw 矩阵 |
| 欧拉角与四元数顺序混用 | 方向看似接近但无法严格对齐 | 直接使用冻结矩阵，明确 wxyz |
| 零位补上旧 URDF 角度偏移 | 所有关节绑定姿态改变 | 四关节 bind=0，使用本包逻辑契约 |
| 面色/点色插值方式改变、重新 gamma | 外观改变 | Col RGB → vertex displayColor，固定材质 |
| 用 UI 中四舍五入的位置数字手抄 | 破坏精确复现 | 蓝图/JSON 的完整 double、float 类型 |
| 把 bounds 尺寸当作重新缩放目标 | 用近似值重新拟合，改变几何 | bounds 只作核验，禁止反向拟合 |

## 10. 验证证据与尚未覆盖的事项

### 10.1 本次新做的重建验证

在远端新目录 `mesh_scene18/handoff_rebuild_validation/Excavator_Mesh_Contract/` 完成，未覆盖正式资产：六个 USD 文件均与金标准逐字节一致；组合后的 USD 全文一致；55 项输入数值数组全部一致。新重建脚本没有调用历史项目代码，不需要旧 GS 模板路径、配准程序或场景17作为输入。

### 10.2 上一次场景替换的验证（本包一并保留证据）

scene17 与 scene18 排除 Visuals 内部几何替换后的 889 个 prim 签名一致，343 个 Xform 的世界矩阵最大差值为 0，活动 Gaussian prim 为 0。9 个内存规定运动用例中保留节点世界矩阵一致，几何变换链最大误差约 `8.88e-16`。完整带齿铲斗按用户选择保留，不承诺它与无齿 GS 的表面完全一致。

上次还实际运行了 3 组采集（零位、正负15度关节及整机位移/旋转），产出 39 条点云、12 张 1920×1080 PNG、32 个 topic / 92 条消息，19 条 TF 边；TF/根位姿/关节角验收通过。它是已有部署资产的运行证据；本次重建六个资产文件完全相同，因此没有为生成报告再启动一轮图形引擎。详细日志和图片在项目 `mesh_scene18/evidence/smoke_20261012_094955/`，本包未重复放入体积较大的采集结果。

本次不把上述结果扩大解释成碰撞动力学、实测关节轴心/尺寸、照片级外观或任意不同渲染环境的验证。更早的单一合并 raw→corrected 五部件阶段也仍未完成严格的逐元素可重放证据链。

## 11. 底层 API 与关键作用

| API / 数据机制 | 本链路用途 |
|---|---|
| `Usd.Stage.Open/CreateNew` | 读取输入、创建分件几何层、加载组合后的资产验证 |
| `Usd.Stage.Flatten` | 获取已组合的属性快照，去除复制时对原层级组合的隐式依赖；验收时形成可比较的完整内容 |
| `Sdf.CopySpec` | 整体复制 Mesh prim 及原属性，避免重建数组时丢失法线、分组、插值等 |
| `UsdGeom.Xform` / `xformOp:transform` / `Gf.Matrix4d` | 分别表达部件原点、原始几何外参和刚体配准；明确行向量矩阵 |
| USD payload | 将主装配结构与五个几何文件分离；相对路径允许整个独立资产目录搬迁 |
| `UsdGeom.PrimvarsAPI` / `Vt.Vec3fArray.FromNumpy` | 原始顶点色映射到标准 displayColor，保留 float32 与 vertex 插值 |
| `UsdShade.Material/Shader/MaterialBindingAPI` | 生成顶点色材质连接并绑定到几何 |
| PhysicsRevoluteJoint、RigidBody/Articulation schemas | 声明关节轴、原点、连接关系及控制结构，不在此重建过程中执行动力学 |
| `UsdGeom.XformCache` | 提取实际组合的 local/world/relative 矩阵，测量原点与尺寸是否变化 |
| NumPy / SHA256 | 数值数组逐元素比较、矩阵核算、文件字节一致性验证 |

重建不需要 CUDA 算法或 RTX 渲染；它处理 USD 文件、数组及坐标组合。GPU 在后续打开场景、渲染图像和雷达扫描时使用。

## 12. 精确验收附表

以下数据由实际资产提取，不作为手工改造模型的输入。完整数值以 JSON 与蓝图为准。

### 12.1 六个金标准文件 SHA256

| 文件 | SHA256 |
|---|---|
| `Excavator_Mesh_Contract.usda` | `84b4ba451ce6aff8108a068b08788ec1619213ee4a2079512a108add86402c9c` |
| `geometry/arm_link.usdc` | `b0bccbb60fc31e8e0c6acc5cfc73700fe245e61668ebb01b9ff3f3e32748fbd1` |
| `geometry/boom_link.usdc` | `aecae49a382971ee31a345c74ce440c87f73923494e87fa2bad2e482bc48ee60` |
| `geometry/bucket_link.usdc` | `5ec52bc689ce3f55c60a722822942ebd73c6928ef80ade83e8b48b4ad040f526` |
| `geometry/swing_link.usdc` | `bf4d45a4e4ef614dc39ed771374dfc8b013d7acdb431ea2147239ae9526a5007` |
| `geometry/track_link.usdc` | `79f7c07929c318bd231a8025e7ad551b2f00013f7b77b2e5ba688bc93bd03f32` |

### 12.2 零位下根坐标系内的顶点 AABB 尺寸（米）

这是所有原始顶点经过固定变换后的轴对齐范围，不是沿部件主轴测量的实体长度；含未被面引用的顶点。表内仅展示 9 位小数，完整精度在 source_facts.json。

| frame | min XYZ | max XYZ | dimensions XYZ |
|---|---|---|
| track_link | (-2.811107849, -1.430557880, -0.471328578) | (1.591841783, 1.768217826, 0.686255338) | (4.402949632, 3.198775706, 1.157583916) |
| swing_link | (-3.597203117, -1.169478147, 0.431588587) | (0.952169338, 1.872430792, 2.985776135) | (4.549372455, 3.041908939, 2.554187548) |
| boom_link | (-0.717597210, -0.644871192, 0.832495578) | (4.501827999, 0.471334000, 5.556673837) | (5.219425209, 1.116205192, 4.724178258) |
| arm_link | (4.061083422, -0.665106271, 1.937356854) | (5.975283367, -0.065481634, 5.728428035) | (1.914199945, 0.599624637, 3.791071181) |
| bucket_link | (5.352488584, -1.039220124, 0.591917905) | (6.544245359, 0.088747962, 2.327320541) | (1.191756775, 1.127968086, 1.735402635) |

### 12.3 当前场景根世界矩阵 W（行向量）

```json
[
  [
    0.9983506095391216,
    0.0476021189098555,
    -0.0320951508511241,
    0.0
  ],
  [
    -0.04619421967419917,
    0.9979950339063691,
    0.04326668888321473,
    0.0
  ],
  [
    0.03409038723095214,
    -0.041712714770403565,
    0.9985478931553191,
    0.0
  ],
  [
    -0.5734957041467448,
    1.4685478977484074,
    0.5559421923906651,
    1.0
  ]
]
```

根自身不附加非单位 scale，左上 3×3 是旋转。不要用场景地面的缩放因子去修改挖掘机。

