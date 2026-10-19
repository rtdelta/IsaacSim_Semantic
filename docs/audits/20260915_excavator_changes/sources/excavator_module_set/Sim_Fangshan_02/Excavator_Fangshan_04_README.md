# Excavator_Fangshan_04：URDF 规则与尺寸参考版

04 是新建的 USD Payload 资产。默认使用 03 的分件 3DGS 外观，关节坐标、零位、旋转正方向和关节中心距按选定 URDF 重建。没有修改旧的 01/02/03、原始 GS、Mesh、PLY 或 combine 场景文件。

## 加载哪一个文件

**作为 Payload 引用：**

```text
/root/gpufree-data/IsaacSim_Asset/excavator_module_set/Sim_Fangshan_02/Excavator_Fangshan_04.usda
```

默认 Prim 为 `/Excavator`，场景单位为 m、Z 向上。通过 Isaac Sim 的 Payload 功能选择该文件即可，不需要执行 sh、Python 或 OmniGraph 启动逻辑。也可以在目标 Xform 的 Property / Metadata 中添加 Payload。[Property Panel 的 Payload 入口](https://docs.omniverse.nvidia.com/extensions/latest/ext_core/ext_property-panel.html)

**直接打开查看整机：**

```text
/root/gpufree-data/IsaacSim_Asset/excavator_module_set/Sim_Fangshan_02/Excavator_Fangshan_04_preview.usda
```

这是额外的新预览场景，通过 Payload 加载 04，包含相机、灯光、零重力 PhysicsScene 及预览用底座固定关节。Payload 本体没有相机、灯光、PhysicsScene 或世界固定关节。预览场景与资产文件的用途不同。

04 以相对路径引用同目录已有 `3dgs_usd`、`waji_mesh_corrected.usdc`，以及新增的 `Excavator_Fangshan_04_data`。若搬迁，请一起保留这些依赖，不能只复制主 USDA。

## 三种显示方式

选择加载后的挖掘机根节点，在 Variants 中切换 `visualization`：

| 取值 | 显示内容 |
|---|---|
| `3dgs`，默认 | 15 个原始 3DGS 部件，经局部变换和分部件缩放后装配 |
| `source_mesh` | 配套扫描 Mesh，使用与 GS 相同的装配变换，用于检查结构 |
| `urdf_reference` | 从选定 URDF 的五份 STL 转成的参考 Mesh，含原 visual origin 变换，便于对照 |

三种显示共用同一套关节。切换显示不会改变关节零点、正方向或中心距。已在远端 Isaac Sim 6.0.1-rc.7 中完成三种显示的实际渲染。

## 关节规则

保留部件路径 `track_prim/cab_prim/boom_prim/arm_prim/bucket_prim`，对应显示名为 URDF 的 `base_link/swing_link/boom_link/arm_link/bucket_link`。四个关节位于根节点下的 `Joints`，名称为 `swing/boom/arm/bucket`。

| 关节 | 父 → 子 | 在父 link 中的安装 xyz / m | 安装 rpy / rad | 关节局部轴 |
|---|---|---|---|---|
| swing | base → swing | (0,0,0.6) | (0,0,0) | +Z |
| boom | swing → boom | (0.53,0,0.77) | (1.5707,0,0) | +Z |
| arm | boom → arm | (5.715,0,0) | (0,0,0) | +Z |
| bucket | arm → bucket | (2.95,0,0) | (0,0,0) | +Z |

零位下，回转正轴在 base 中为 +Z；后三个关节的共同正轴为约 `(0,-0.999999995,+0.000096327)`，与原 URDF 的 1.5707 rad 安装旋转一致，没有取整成精确 π/2。正向旋转遵守右手规则。

四个关节 q=0 时，base 中的关节位置依次为：

```text
swing  (0,     0, 0.6)
boom   (0.53,  0, 1.37)
arm    (6.245, 0, 1.37)
bucket (9.195, 0, 1.37)
```

大臂、小臂的两端轴心连线沿 +X；弯曲的大臂外形不因此变成直杆。铲斗的参考 Mesh 使用 URDF 的原始外观旋转，GS 铲斗则根据铰点到远端几何边缘方向进行装配配准，并保留扫描外形。

URDF 四个关节均为 continuous，因此 04 使用无有限角度限位的 RevoluteJoint，没有复制 URDF 内反置的 lower/upper 和零 effort/velocity。

## 尺寸对齐的具体含义

**严格对齐的部分：** 五个 link 的零位坐标、四个关节帧、转轴、正方向、父子关系，以及 5.715 m 和 2.950 m 等运动学尺寸。

**分部件配准的部分：** 扫描部件外观。03 与 URDF 不是同一个几何模型，不能靠一个全局 scale 完成装配。因此 04 将大臂、小臂的原始两端锚点精确映射到 URDF 位置；其他方向的外观尺度根据 URDF STL 范围校正。底盘、平台、铲斗同样分别处理。

最终使用的尺度参数如下；大臂和小臂的数值是在销轴连线建立的局部坐标中表达，不是世界 XYZ：

| 部件 | 三个局部方向的缩放 |
|---|---|
| 底盘 | (2.211002, 2.550158, 1.946645) |
| 回转平台 | (1.745227, 1.872521, 1.024989) |
| 大臂 | (2.385015, 1.624461, 0.678465) |
| 小臂 | (2.423101, 2.413326, 0.381046) |
| 铲斗及全部斗齿 | (1.828379, 1.986555, 1.980027) |

原始高斯数据没有被改写，缩放与安装变换写在 04 自己的显示节点上。表中的外观范围以高斯中心坐标作标定，实际渲染边缘还受高斯椭球尺度和透明度影响。

**这不是把扫描外形变成与 URDF STL 逐点相同的 CAD。** 两套素材的驾驶室、油缸、臂形和斗形仍有差异，扫描轮廓及局部接口可能与参考网格不完全重合。可用 `urdf_reference` 直接看出这些差异；关节计算的对齐不依赖它们是否具有相同轮廓。

## 如何试转

打开预览场景，选择 `Joints/swing`、`boom`、`arm` 或 `bucket`，在 Angular Drive 中设置 Target Position；USD 属性界面中的角度单位为 degree。例如输入 +10，表示正向 10°。运行时读取和控制关节的 Python 接口需按对应接口要求使用 rad。

四个关节增加了用于姿态预览的 Drive，初始目标均为 0。质量和惯量采用未校准的占位值，驱动参数也只用于查看动作，不代表真实挖掘机液压系统。未添加碰撞体或校准接触参数。

在自己的场景中引用 Payload 后，场景需提供自己的物理设置；是否固定底盘由该场景决定。若引用到已有 combine 场景中，请检查其更强的节点变换、显隐、限位和旧控制脚本覆盖，避免把旧规则重新覆盖到 04 上。

## 验证与证据

- 以不同命名的两处 Payload 引用进行合成测试，关节 body0/body1 均正确重映射到各自实例，没有指向别的实例。
- 29 组零位、单关节正负角度和组合角度，与独立 URDF 运动学结果比较，最大矩阵元素误差约 `5.18e-7`；其中米制平移误差小于 1 微米，属于 USD 浮点关节字段精度范围。
- 零位转轴最大向量误差约 `7.33e-8`，各关节未出现符号反转。
- 15 个 GS 部件及三种显示配置均可解析，实际渲染无资产合成错误。
- 独立 PhysX 场景中，通过 USD Angular Drive 对四个关节分别输入 +10°、−10°，共八项检查全部通过。实际 DOF 顺序为 `[swing, boom, arm, bucket]`，最大稳态角度误差约 `8.03e-7 rad`（约 `0.000046°`）。这验证预览驱动和正负方向，不代表实机动力学精度。
- 创建前的 29 个既有文件均做了 SHA-256 对照，未被本次构建修改。

远端数据目录 `Excavator_Fangshan_04_data` 中保存 `build_config.json`、`validation.json`、`runtime_validation.json`、`physics_validation.json`、`final_validation.json` 和三张 `preview_*.png`。其中 Python 文件是一次性的构建/验证资料，资产加载和显示不依赖它们。

渲染捕获流程里的物理读取曾因该流程未挂接 PhysX stage 而失败；随后通过独立的 PhysX stage 挂接完成了上述八项测试。原诊断保留在日志中，最终验收以 `final_validation.json` 和 `physics_validation.json` 为准。

URDF 基准 SHA-256：`244a441c78f5793026cbaa760fc22866790acbccdd894c6058067cf0b52fcbb7`。
