# SensorVisualizer：3DGS 对接装配资产

最新新增 **scene 16：Blender 起伏地面＋手动 Z 高度＋整机 Pitch/Roll 三模式控制**。使用 [TILT_TERRAIN_USAGE.md](TILT_TERRAIN_USAGE.md) 中的启动入口；scene 15 和其原资产保留。图片、点云及 TF 的保存方式沿用四路鱼眼版本。

**scene 15：四路鱼眼环视**，使用 sensor_set 中已有的 `fish_eye_camera.usda`，分别与 MyAiry 前/后/左/右雷达位置对齐。启动、四路预览和保存格式见 [SURROUND_USAGE.md](SURROUND_USAGE.md)。旧 scene 14 单相机用法继续兼容。

2026-09-21 新增 **scene 14：鱼眼相机 + 整机前后移动/转向**，并在本目录提供独立运行入口 `run_in_isaac.py`。使用流程、数据格式和模块顺序见 [FISHEYE_USAGE.md](FISHEYE_USAGE.md)。旧 scene 13 与旧 LiDAR 项目保留不变；ROS 话题沿用已有命名，尚未额外导出完整的同事端 TF 协议树。

本项目按同事文档装配挖掘机，并已新增与旧场景相同传感器的组合场景：7 台 MyAiry、6 台 MyNZ3 和 1 台大臂相机。资产配置版本：`3dgs_contract_v1`。ROS 和正式采集控制器尚未迁移到新合同定义。

新组合场景与使用说明见 [COMBINE_STAGE.md](COMBINE_STAGE.md)。远端可直接打开 `/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_13_3dgs_contract.usda`。以下内容描述独立挖掘机资产。

## 打开资产

远端预览场景：

```text
/root/gpufree-data/IsaacSim_Asset/excavator_module_set/Excavator_3DGS_Contract/Excavator_3DGS_Contract_preview.usda
```

在 Isaac Sim 的 File → Open 打开预览场景。它包含灯光、相机、地面、零重力 PhysicsScene 和固定底盘的预览锚点。可切换到 `/World/Camera` 查看整机。

作为 Payload/Reference 使用的主资产：

```text
/root/gpufree-data/IsaacSim_Asset/excavator_module_set/Excavator_3DGS_Contract/Excavator_3DGS_Contract.usda
```

主资产的 defaultPrim 为 `/Excavator`，默认已处于绑定姿态。加载不需要执行 Script Editor 代码。引用主资产时一起保留 `geometry/` 目录，根节点 Scale 保持 `(1,1,1)`。

需要查看关节运动时，在预览场景 Play 后选择 `/World/Excavator/Joints/boom` 等关节，在 Angular Drive 的 Target Position 中输入小角度。USD 面板单位为度，原生控制 API 单位为弧度。Stop 后恢复资产保存的零位。四个轴均无硬件标定限位，请先以 ±15° 查看运动。

## 模型定义

- 同事提供的五份 PLY 为唯一几何输入，指纹固定；无额外斗齿、旧 Mesh 或旧 URDF 覆盖层。
- PLY → GS USD 不居中、不旋转、不缩放点坐标。NVIDIA 转换器负责 log-scale、opacity、quaternion 与 SH 的格式转换。
- 公共 raw→base：平移 `(3.20352,-0.34217,2.04934)` m，RPY `(-103.98993,-5.69811,61.29154)`°，旋转顺序 `Rz·Ry·Rx`，缩放 2.4。
- 每个部件的固定素材变换为 `inverse(T_base_link_bind) @ T_base_raw`。
- 所有新关节角为 0 时，模型恢复原始重建姿态；不使用旧包中的绝对角度偏置。
- 回转轴 +Z，boom/arm/bucket 轴 +Y，所有固定关节旋转为单位阵。
- `platform_roll/pitch=0`：本版为四个旋转关节；文档允许的平台独立倾斜没有扩展成额外物理自由度。
- 2.4 倍缩放只在素材变换中出现。刚体、关节位置和未来的 TF 都用米，不能再次乘以 2.4。

## USD 路径与语义树

为了使用 PhysX 原生 Articulation，五个刚体在 USD 中是平级节点，由原生关节关系连接。`/Excavator` 本身表示语义 `base_link`：

```text
/Excavator
  /track_link                 ArticulationRootAPI，单位姿态
  /swing_link
  /boom_link
  /arm_link
  /bucket_link
  /Joints/{swing,boom,arm,bucket}
```

每个刚体下为 `Visuals/Splat`，Visuals 存固定素材矩阵，Splat 通过相对 Payload 引用对应原始坐标 GS USD。

语义父子关系独立记录在 `manifest.json` 和 prim 的 `parentFrame` 中：

```text
base_link
├── track_link
└── swing_link
    └── boom_link
        └── arm_link
            └── bucket_link
```

目前没有 ROS TF 发布器。物理连接仍然是 track→swing→boom→arm→bucket；不要把 USD 刚体层级或物理连接直接当作未来的 ROS TF 发布树。

## 本地与远端项目

- 本地：`D:\learning\IntelligentDepartment\CodesSet\Self\260707IsaacSIm\scripts\260920SensorVisualizer`
- 远端源码：`/root/gpufree-data/semantic/scripts/260920SensorVisualizer`
- 远端可加载资产：`/root/gpufree-data/IsaacSim_Asset/excavator_module_set/Excavator_3DGS_Contract`

```text
config/assembly.json          唯一装配配置
source_docs/                  同事文档快照；其中引用的图片/YAML未提供
sources/ply/                  五份未经修改的原始PLY
tools/                        构建、验证、同步和部署脚本
assets/Excavator_3DGS_Contract/ 独立可搬迁资产包
reports/                      构建记录、数值验收、Isaac日志与预览图
```

## 复现构建与验证

在远端项目目录依次运行（现有生成结果重建时给构建命令加 `--rebuild`）：

```bash
bash tools/run_cpu.sh build_asset.py
bash tools/run_cpu.sh validate_geometry.py
bash tools/run_isaac_validation.sh
bash tools/run_cpu.sh publish_asset.py
```

前两步使用系统 Python、NumPy、Isaac 安装内的 OpenUSD 和 NVIDIA `usd_convert_gsplat`，不启动 Kit。第三步启动独立的无窗口 Isaac 进程，不操作现有 GUI。依赖位置通过 `SV_ISAAC_ROOT` 配置，默认 `/root/isaacsim`。转换器版本与源代码指纹记录在 `reports/build.json`。

历史说明：旧实例首次启动曾报 `bad marshal data`，当时使用私有 Python 缓存路径绕过。后续排查发现旧实例存在异常动态库读过滤，不能再将当时现象直接归因为磁盘缓存损坏。旧验证记录仍保留；新组合场景在新实例运行，使用 `run_combine_validation.sh`，不使用该缓存绕过设置。

同步源码或拉回产物，可在本地安装有 Paramiko 的 Python 中执行：

```text
python tools/sync_remote.py push
python tools/sync_remote.py pull
```

默认连接已知远端，凭据交互输入或使用 `--key`，不保存在项目中。使用系统 known_hosts 校验服务器身份。

## 验证范围与使用限制

1. CPU 验证全部 395,003 个高斯的中心、尺度、不透明度、四元数、完整 SH，以及零位装配和关节锚点。
2. Isaac 验证原生 Articulation 的零位、四关节各自 ±15°、组合姿态，并保存渲染预览。
3. 发布前检查两份验证报告对应当前资产清单，发布后核对每个文件 SHA-256。

质量、惯量和驱动参数是运动验证用占位值；没有物理碰撞网格，也没有实车动力学标定。原生 GS 是本版唯一可见本体几何。此资产还没有进行 RTX LiDAR 采集或对方程序联调，视觉渲染预览不等于点云对齐验收。

验收以同事文档中的运动学定义为准。若运动时原始扫描接缝有缝隙，不擅自加平移补偿或拉伸部件。

## 2026-09-22：相机入包与性能监测

现有 scene16 可继续使用。重新运行 Script Editor 入口后，Stop Recording 会自动生成本轮 `bag_unified/`，包含原雷达消息和四路鱼眼图像、内参、位姿、相机 TF。原始 `bag/` 和相机文件保留。后方相机输出标识由 `rear` 改为 `back`，原场景安装节点兼容读取，位置不变。

资源监测随脚本运行启动，各轮 `performance_reference.json` 指向资源采样、阶段耗时及汇总。详细使用说明、话题定义和离线补打包命令见 [统一 MCAP 与性能监测](docs/unified_mcap_and_performance.md)。

## 报告与验收证据

正式报告、精选验收摘要和必要配图见 [报告索引](docs/reports/README.md)。原始采集、逐帧状态和性能追踪保留在原运行目录，由仓库忽略规则排除。
