# 3DGS、OpenUSD 与 Isaac Sim 开源资源整理

> 整理时间：2026-07-26  
> 适用方向：3D Gaussian Splatting（3DGS）资产转换、OpenUSD 表示、Isaac Sim 场景导入与仿真集成

## 1. 结论

目前，3DGS 的数据表示和导入转换链路已经具备较完整的开源实现：

```text
3DGS 训练或重建
    ↓
PLY / SPZ
    ↓
开源转换器 usd-convert-gsplat
    ↓
ParticleField3DGaussianSplat USD / USDZ
    ↓
作为 Reference 或 Payload 加入 Isaac Sim
    ↓
Omniverse RTX 原生渲染
```

其中：

- OpenUSD 核心、3DGS ParticleField Schema、PLY/SPZ 到 USD 的转换器、3DGRUT 和 Isaac Sim 应用层源码已经开放；
- Omniverse Kit SDK、Omniverse RTX 渲染组件等运行时依赖采用单独的 NVIDIA 许可证；
- 因此，“3DGS 数据生成、USD 表示、格式转换和 Isaac Sim 应用集成”可以研究和修改，但从 USD 到最终 RTX 画面的完整渲染栈并非全部开源。

## 2. 开源情况总览

| 环节 | 开源状态 | 简要说明 |
|---|---|---|
| OpenUSD 核心 | 开源 | 提供 USD 文件、Stage、Prim、Schema、Reference 和 Payload 等底层能力 |
| ParticleField Schema | 开源 | OpenUSD 中用于表达 3DGS、3DGUT 等粒子辐射场 |
| `ParticleField3DGaussianSplat` | 开源 | OpenUSD 26.03+ 提供的标准 3DGS Schema |
| `.ply/.spz → USD` 转换器 | 开源 | NVIDIA 官方 `usd-convert-gsplat`，源码采用 Apache-2.0 |
| 3DGRUT | 开源 | NVIDIA Research 的 Gaussian 训练、光栅化、光线追踪和导出项目 |
| Isaac Sim 应用层 | 开源 | Isaac Sim 仓库代码采用 Apache-2.0 |
| Omniverse Kit SDK | 单独授权 | Isaac Sim 构建和运行依赖，不属于 Isaac Sim 仓库的 Apache-2.0 源码 |
| Omniverse RTX 3DGS 渲染后端 | 非完整开源 | 作为 Omniverse Kit/RTX 运行组件提供 |

## 3. 核心开源资源

### 3.1 NVIDIA usd-convert-gsplat

- 项目地址：<https://github.com/NVIDIA-Omniverse/usd-convert-gsplat>
- PyPI：<https://pypi.org/project/usd-convert-gsplat/>
- 主要用途：将 3D Gaussian Splat 资产转换为 OpenUSD。
- 输入格式：
  - `.ply`
  - `.spz`
- 输出格式：
  - `.usd`
  - `.usda`
  - `.usdc`
  - `.usdz`
- 许可证：
  - 源码：Apache-2.0
  - 文档：CC-BY-4.0

转换器能够保留或写入以下 Gaussian 属性：

- 三维位置；
- 三轴尺度；
- 四元数方向；
- 不透明度；
- 球谐系数；
- Gaussian 椭球核所需数据。

#### 安装

```bash
python -m pip install "usd-convert-gsplat[usd]"
```

#### 基本转换

```bash
usd-convert-gsplat \
    -i scene.ply \
    -o scene.usdz
```

也可以通过 Python 模块运行：

```bash
python -m usd_convert_gsplat \
    -i scene.ply \
    -o scene.usdz
```

#### 普通 XYZRGB 点云的辅助转换

如果 PLY 只有位置和 RGB，缺少球谐系数或 Gaussian 尺度，可以使用：

```bash
usd-convert-gsplat \
    -i pointcloud.ply \
    -o scene.usdz \
    --generateSh \
    --generateScales
```

需要注意：这种方式只是估算并补齐显示需要的属性，不等价于经过多视角优化训练得到的 3DGS 模型。

#### Python API 示例

```python
from usd_convert_gsplat import read_ply, write_gaussian_splat_usd

splat_data = read_ply("scene.ply")

write_gaussian_splat_usd(
    splat_data,
    "scene.usdz",
    source_file="scene.ply",
)
```

### 3.2 Pixar OpenUSD

- 源码仓库：<https://github.com/PixarAnimationStudios/OpenUSD>
- 官方文档：<https://openusd.org/release/>
- 主要用途：提供 USD 场景描述、组合、文件读写和 Schema 系统。

与 3DGS 链路相关的能力包括：

- USD Stage 和 Prim；
- Reference、Payload、Layer 和 Variant；
- `UsdGeom` 和 `UsdVol` Schema；
- Python 与 C++ API；
- `usdview` 等查看和调试工具；
- ParticleField 和 3DGS 相关数据结构。

如果需要自己开发转换器、检查 USD 字段或者扩展 Schema，应优先参考 OpenUSD 源码和官方文档。

### 3.3 OpenUSD ParticleField Schema

- `ParticleField` 文档：  
  <https://openusd.org/release/user_guides/schemas/usdVol/ParticleField.html>
- `ParticleField3DGaussianSplat` 文档：  
  <https://openusd.org/release/user_guides/schemas/usdVol/ParticleField3DGaussianSplat.html>
- Schema 总目录：  
  <https://openusd.org/release/user_guides/schemas/index.html>

`ParticleField` 是一种通用粒子场表示，可以用于描述：

- 3D Gaussian Splatting；
- 3D Gaussian Unscented Transform；
- 其他基于粒子核和辐射属性的场。

`ParticleField3DGaussianSplat` 是面向 3DGS 的具体类型，相关 Applied API 包括：

- `ParticleFieldPositionAttributeAPI`
- `ParticleFieldOrientationAttributeAPI`
- `ParticleFieldScaleAttributeAPI`
- `ParticleFieldOpacityAttributeAPI`
- `ParticleFieldKernelGaussianEllipsoidAPI`
- `ParticleFieldSphericalHarmonicsAttributeAPI`

OpenUSD 26.03 及以上版本提供类型化的：

```python
UsdVol.ParticleField3DGaussianSplat
```

### 3.4 NVIDIA 3DGRUT

- 项目地址：<https://github.com/nv-tlabs/3dgrut>
- 许可证：Apache-2.0
- 主要用途：Gaussian 场景训练、渲染、评测和 USD 导出。

项目包含：

- 3DGRT：3D Gaussian Ray Tracing；
- 3DGUT：支持畸变相机的 Gaussian Rasterization；
- 3DGRUT：光栅化主射线与光线追踪次级射线的混合方案；
- COLMAP、NeRF Synthetic、Mip-NeRF 360、ScanNet++ 等数据集配置；
- PLY 到 USD/USDZ 的导出工具；
- 向 USDZ 加入 Mesh 和碰撞属性的辅助工具；
- Windows 和 Linux 支持。

#### 训练时启用 USD 导出

```bash
python train.py \
    --config-name apps/colmap_3dgut.yaml \
    path=data/scene \
    out_dir=runs \
    experiment_name=scene \
    export_usd.enabled=true
```

#### 旧版 PLY 到 USDZ 转换

```bash
python -m threedgrut.export.scripts.ply_to_usd \
    scene.ply \
    --output_file scene.usdz
```

3DGRUT 仓库中的部分说明仍涉及 Isaac Sim 5.0 使用的测试版自定义 `UsdVolVolume` 格式。面向 Isaac Sim 6.x 的新项目，应优先采用标准 `ParticleField3DGaussianSplat` 和 `usd-convert-gsplat`。

### 3.5 Isaac Sim

- 源码仓库：<https://github.com/isaac-sim/IsaacSim>
- 许可证文件：<https://github.com/isaac-sim/IsaacSim/blob/main/LICENSE>
- 官方文档：<https://docs.isaacsim.omniverse.nvidia.com/>

Isaac Sim 应用层源码包括：

- USD 场景和资产管理；
- 机器人、控制器与运动学接口；
- 物理仿真集成；
- RTX 和物理类传感器集成；
- Replicator 与合成数据生成；
- ROS 接口；
- Python 示例和 Kit 扩展。

Isaac Sim 仓库采用 Apache-2.0，但其许可证明确说明，构建或使用软件需要额外组件，包括 Omniverse Kit SDK、部分模型和纹理等。这些组件采用各自的许可证。

因此，应区分：

```text
Isaac Sim 仓库源码：开源
Omniverse Kit/RTX 完整运行时：单独授权，不是全部 Apache-2.0
```

## 4. 官方使用文档

### 4.1 Isaac Sim Neural Volume Rendering

- 文档地址：  
  <https://docs.isaacsim.omniverse.nvidia.com/6.0.0/assets/usd_assets_nurec.html>

文档展示了如何：

- 在 Isaac Sim 中打开 ParticleField 或 Gaussian Splat USD；
- 将机器人加入重建场景；
- 创建独立碰撞地面；
- 设置导航目标并运行仿真；
- 配置 NuRec 和 Gaussian 相关渲染选项。

文档中的示例也体现了一个重要事实：Gaussian 场景主要承担视觉呈现，机器人行驶和物理交互仍可能需要单独的碰撞几何。

### 4.2 Omniverse Gaussian Splats（Particle Fields）

- 文档地址：  
  <https://docs.omniverse.nvidia.com/materials-and-rendering/latest/particle-fields.html>

主要内容包括：

- 3DGS PLY 到 OpenUSD 的转换；
- ParticleField 的原生 RTX 渲染；
- Gaussian 与普通 Mesh 混合；
- 路径追踪；
- 反射和折射；
- 阴影；
- 色彩空间与色调映射；
- 当前限制。

### 4.3 Isaac Sim OpenUSD 基础

- 文档地址：  
  <https://docs.isaacsim.omniverse.nvidia.com/latest/omniverse_usd/open_usd.html>

适合了解：

- 如何创建和打开 Stage；
- 如何定义 Prim；
- 如何保存 USD；
- 如何添加 Reference 和 Payload；
- 如何遍历、查询和修改 USD 属性；
- 如何通过 Python 将转换后的 3DGS 资产加入 Isaac Sim。

## 5. Isaac Sim 5.0 与 6.x 链路差异

### 5.1 Isaac Sim 5.0 旧链路

Isaac Sim 5.0 时期，3DGRUT 使用测试性质的自定义 USDZ 表示，基于扩展的 `UsdVolVolume` Schema。

其特点是：

- 属于 Beta 工作流；
- 与特定版本的 Omniverse Kit 和 Isaac Sim 绑定；
- 官方曾提示 USD 和重建工作流未来可能发生变化。

### 5.2 Isaac Sim 6.x 推荐链路

新项目推荐采用：

```text
OpenUSD 26.03+
    +
ParticleField3DGaussianSplat
    +
usd-convert-gsplat
    +
Isaac Sim 6.x
```

优势包括：

- 使用 OpenUSD 标准 Schema；
- 不需要自行发明私有 Gaussian 属性；
- 支持 `.usd/.usda/.usdc/.usdz`；
- 可以作为普通 USD Reference 或 Payload 组合到场景；
- 便于后续版本迁移和跨工具处理。

## 6. 3DGS PLY 与普通点云 PLY 的区别

普通点云 PLY 通常只有：

```text
x, y, z
r, g, b
```

典型 3DGS PLY 还需要：

```text
scale_0, scale_1, scale_2
rot_0, rot_1, rot_2, rot_3
opacity
f_dc_*
f_rest_*
```

这些属性分别表示：

- Gaussian 椭球的空间尺度；
- Gaussian 椭球的方向；
- 不透明度；
- 球谐颜色及视角相关外观。

因此：

- 普通点云可以转换为 `UsdGeomPoints`；
- 也可以估算属性后写成 `ParticleField3DGaussianSplat`；
- 但它不会自动拥有经过多视角训练得到的 3DGS 视觉质量。

## 7. Isaac Sim 中的仿真限制

3DGS USD 首先是一种渲染资产，不是完整的 SimReady 仿真资产。

Gaussian ParticleField 通常不能直接代替：

- PhysX 碰撞 Mesh；
- 地面和承载表面；
- 导航网格；
- 带拓扑的可编辑几何；
- 语义分割标签层；
- 刚体或关节结构。

对于机器人、车辆或挖掘机仿真，推荐使用双层资产：

```text
ParticleField3DGaussianSplat
    └── 负责高真实感视觉背景

简化 Mesh / HeightField / Voxel Collision
    └── 负责碰撞、地面、导航和物理交互
```

还可以进一步加入：

```text
语义 USD Layer
    └── 负责类别、实例和数据采集标签
```

## 8. 推荐工程链路

```text
相机图像与相机位姿
      ↓
COLMAP / SLAM / 已知标定
      ↓
3DGRUT 或其他 3DGS 训练框架
      ↓
3DGS PLY / SPZ
      ↓
NVIDIA usd-convert-gsplat
      ↓
ParticleField3DGaussianSplat USD / USDZ
      ↓
作为 Reference 加入普通 Isaac Sim USD Stage
      ↓
叠加碰撞 Mesh、地面、语义 Layer 和机器人资产
      ↓
Isaac Sim 渲染、仿真与数据采集
```

建议不要直接把 `.usdz` 作为需要继续编辑的根 Stage。更稳妥的方式是：

1. 创建普通 `.usd` 或 `.usda` 根场景；
2. 将 Gaussian `.usdz` 作为 Reference 或 Payload 加入；
3. 在独立 Layer 中添加机器人、碰撞体和语义；
4. 保持 Gaussian 视觉资产和物理资产解耦。

## 9. 建议优先关注的四个仓库

1. [NVIDIA usd-convert-gsplat](https://github.com/NVIDIA-Omniverse/usd-convert-gsplat)  
   用于 PLY/SPZ 到标准 3DGS USD 的转换。

2. [Pixar OpenUSD](https://github.com/PixarAnimationStudios/OpenUSD)  
   用于理解 USD 数据模型、Schema 和底层 API。

3. [NVIDIA 3DGRUT](https://github.com/nv-tlabs/3dgrut)  
   用于 Gaussian 场景训练、渲染和导出。

4. [NVIDIA Isaac Sim](https://github.com/isaac-sim/IsaacSim)  
   用于机器人仿真、USD 场景集成和传感器数据生成。

## 10. 最终判断

如果目标是自行研究和修改以下内容：

- 3DGS 训练；
- PLY/SPZ 数据解析；
- Gaussian 属性到 USD 属性的映射；
- `ParticleField3DGaussianSplat` USD 生成；
- Isaac Sim 场景加载和机器人集成；

那么现有开源资源已经可以支持实施。

如果目标是完全脱离 NVIDIA 组件，从源码复现 Isaac Sim/Omniverse 中的 RTX 原生 3DGS 渲染，则目前仍不具备完整的开源链路，因为最终渲染依赖 Omniverse Kit 和 RTX 运行时组件。
