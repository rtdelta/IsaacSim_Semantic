# NZ3 实测校正采样雷达

本目录按要求命名为 `260910NV3Lidar`；规格书型号和资产名称使用 **NZ3**。

这是一个模型：**bag 中可靠观测到的射线方向，加上缺失位置的插值和手册补全**。模型提供标称水平240°、垂直80°、96×480（46,080个）独立采样方向，保留非均匀垂直扫描线以及左右半视场差异。

当前范围是视场角与采样位置。采集采用瞬时整帧；没有宣称复现真实逐点时序、运动畸变、反射率标定、测距误差、IMU或厂家UDP协议。近远距离、10Hz等为让传感器工作的基础配置，不作为本版已完成的设备性能标定。

已在目标远端 **Isaac Sim 6.0.1-rc.7 / NVIDIA L40** 上通过实际RTX验证：封闭房间与增加障碍物两个场景均取得46,080个独立射线回波；输出方向与角度表的最大偏差约0.000030°，距离与解析几何的最大差约0.000013米。加入障碍物后2,002条射线按预期变短。这些是仿真计算一致性结果，不代表实机精度。

查看 [采样分布](docs/reports/calibration_overview.png) 和 [实际RTX点云验证图](docs/reports/isaacsim/render_validation.png)。

## 使用哪个资产

标准入口是 **`assets/NZ3/MyNZ3.usda`**。它引用同目录下的 `config/NZ3_scan.usda` 与 `geometry/NZ3_housing.usda`；复制资产时保留整个 `assets/NZ3` 文件夹。旧名称 `NZ3.usda` 保留为本地兼容入口，引用的是同一个模型。

远端正式部署位置：`/root/gpufree-data/IsaacSim_Asset/sensor_set/lidar_set/NZ3/MyNZ3.usda`。资产根节点含 `sensor` 和带外壳的 `geometry`。外壳由远端Blender 5.1.1制作，宽71、高100、深86 mm，沿用扫描原点，按距原点8 cm排除近处几何以避免自遮挡。外壳相对光学中心的位置为近似；使用时保持单位缩放。使用方法见 [资产说明](assets/NZ3/README.md)。

组织方式参考远端 Rotator360_90 的“入口USD + 自定义传感器配置”，生成资产使用自包含 OmniLidar，不依赖在线Ouster外壳或外部资产下载。真正的传感器位于入口根节点下的 `sensor`。

| 路径 | 内容 |
|---|---|
| `assets/NZ3/MyNZ3.usda` | 可引用的标准雷达入口 |
| `assets/NZ3/config/NZ3_scan.usda` | 46,080束射线的实际RTX配置 |
| `assets/NZ3/geometry/NZ3_housing.usda` | 简易外壳网格与材质，随入口引用 |
| `source/housing/NZ3_housing.blend` | 可编辑的Blender外壳源文件 |
| `source/housing/housing_manifest.json` | 尺寸、网格计数、包围半径与原点近似说明 |
| `tools/build_housing_blender.py`、`tools/remote_build_housing.py` | 参数化建模、远端Blender执行及成果下载 |
| `reports/housing_build/latest.json` | 最新Blender建模结果与预览位置 |
| `calibration/rays.npz` | 完整角度表、方向向量、ring/列索引、来源与观测支持 |
| `calibration/manifest.json` | 输入校验值、算法假设、参数、来源数量及留出验证 |
| `calibration/frame_observations.npz` | 从bag提取的逐帧角度观测，不包含场景距离学习 |
| `calibration/frames.json` | 每帧话题、时间、零点剔除和视场外剔除统计 |
| `build_asset.py`、`nz3_model.py` | 可复现的提取、拟合、补全和USD生成脚本 |
| `isaac_utils.py` | 向当前Isaac Sim场景加载雷达的函数 |
| `isaac_demo.py`、`run_isaac.sh` | 独立进程验证和交互演示入口 |
| `tools/remote_verify.py` | 上传验证副本、运行独立测试、取回结果；不保存密码 |
| `tools/deploy_reference_asset.py` | 标准引用验收、正式部署、部署后检查与文件校验 |
| `tools/validate_reference_asset.py` | 仅用USD引用和标准RTX输出，验证多雷达、姿态、保存重开和目录搬迁 |
| `docs/reports/reference_asset/latest.json` | 最新正式部署清单及各阶段验证报告位置 |
| `tools/plot_render_validation.py` | 从实际RTX点云生成验证图 |
| `tools/probe_renderer.py` | 排查远端版本参数的诊断脚本，不是另一版雷达模型 |
| `tests/test_model.py` | 坐标变换、空回波、分区拼接、缺失补全和几何真值测试 |
| `inputs/` | 原始bag和PDF副本，便于整个目录独立重建 |
| `reference/` | 原有Rotator360_90模板及NVIDIA安装中的相关参考文件；不是生成资产的运行依赖 |
| `docs/reports/calibration_overview.png` | 完整采样分布、来源、观测支持和垂直角度曲线 |
| `reports/local_validation.json` | 全表检查及40帧训练/10帧留出验证 |
| `reports/isaacsim/validation.json` | 远端实际渲染验证；只有通过时才生成 |
| `reports/isaacsim/chamber.pcd`、`with_target.pcd` | 两种场景的实际RTX点云，含ring |
| `reports/isaacsim/verified_scene.usda` | 已验证场景的自包含快照；持续读取点云仍需运行脚本 |

## 在远端当前场景中使用

像使用MyOS0一样，在Isaac Sim中引用正式入口，并在场景的RTX输出流程中选择它下面的 `sensor`。也可以在Script Editor中添加引用：

```python
import omni.usd
from pxr import UsdGeom, Gf
stage = omni.usd.get_context().get_stage()
path = '/World/Vehicle/Sensors/NZ3'  # 选择尚未占用的节点路径
root = stage.DefinePrim(path, 'Xform')
root.GetReferences().AddReference(
    '/root/gpufree-data/IsaacSim_Asset/sensor_set/lidar_set/NZ3/MyNZ3.usda')
UsdGeom.XformCommonAPI(root).SetTranslate(Gf.Vec3d(0, 0, 1.5))
```

引用资产只添加雷达定义，点云读取、显示与发布由场景控制。日常使用不需要bag、NPZ或NZ3专用加载函数。原有 `isaac_utils.py` 和 `isaac_demo.py` 继续保留，供独立演示使用。

资产坐标为 **+X向前、+Y向左、+Z向上**。bag坐标通过 `(X,Y,Z)资产=(y,-x,z)bag` 转换。这是基于当前数据采用的方向约定，不代表已经标定雷达到车辆的安装外参。

NPZ角度采用数学逆时针方位角；目标版本RTX的方位角为顺时针，因此生成USD时已取负号。不要再额外镜像坐标。配置文件的 `channelId` 为1–46080；目标版本GMO输出的 `emitterId` 和 `channelId` 均为0–46079。由 `ring=emitterId//480`、`column=emitterId%480` 得到采样位置，无需运行时查NPZ。

标准资产验收逐束比较输出方向和场景求交距离。单雷达封闭房间要求覆盖全部46,080个位置；RTX可能筛掉少量回波，因此必要时对固定场景/姿态累计多帧，报告保留每帧实际回波数。多雷达场景中，另一台雷达外壳参与求交，黑色或掠射表面可能缺少回波；这部分单独记录，所有环境射线仍要求完整覆盖。返回的外壳点用CPU三角网格求交核对。各重新打开与搬迁检查在独立新进程中进行。

## 独立运行验证或演示

在Linux远端进入本目录：

```bash
bash run_isaac.sh
# 需要一个独立可视窗口时：
bash run_isaac.sh --gui
```

默认模式启动独立headless Isaac Sim，在封闭测试几何中验证46,080个回波；加入一个近处物体，再验证输出随场景改变。结束后退出，不操作原先运行中的Isaac Sim。结果和点云写入 `reports/isaacsim/`。

`run_isaac.sh` 默认使用 `/root/isaacsim`；其他安装位置可设置 `NZ3_ISAAC_ROOT`。目标远端的系统动态库路径优先于Kit，因此直接使用python.sh曾误载系统libpython 3.12.3，导致启动崩溃。启动脚本只为当前子进程将Kit自带Python库放在前面，使用匹配的3.12.13，不修改系统文件或用户环境配置。

启动脚本还补充雷达校验库搜索路径；加载函数会显式加载校验库并在生成传感器前检查配置。独立演示采用与远端现有实例相同的静态渲染路径，关闭motion BVH和多频率渲染。当前瞬时模式按渲染帧产生完整扫描，配置中的10Hz不作为实际输出频率保证。运动/逐点时序不在本版范围内。

## 在本地重新生成

在Windows进入本目录，使用已有Python或独立环境：

```powershell
python -m pip install -r requirements.txt
python build_asset.py
# 仅重新封装已有校准表，不重新拟合bag：
python build_asset.py --asset-only
python -m unittest discover -s tests -v
```

已使用Python3.9.18、NumPy1.26.4、rosbags0.9.23、matplotlib3.8.0重建。脚本默认读取本目录inputs，所有生成文件写回本目录。重新生成不会触碰原始Materials目录。

可选重新执行远端验证：

```powershell
python tools/remote_verify.py
# 验收并部署标准资产到正式NZ3资产目录：
python tools/deploy_reference_asset.py
# 重新制作外壳并取回Blender源文件、网格和预览：
python tools/remote_build_housing.py
# 外壳生成后，重新封装入口再部署：
python build_asset.py --asset-only
python tools/deploy_reference_asset.py
```

脚本会交互询问SSH密码，也可以从临时环境变量 `NZ3_REMOTE_PASSWORD` 读取；源码和配置不保存密码。远端副本只用于验证，交付内容及结果保留在本地本目录。

## 角度表如何得到

1. 以96行、480列建立完整采样框架；水平采样单元宽0.5°，垂直理想单元宽80/96≈0.8333°。
2. 从50帧PointCloud2剔除零XYZ/非有限值，转换为方向。超过标称±120°/±40°的少量观测单独计数，不硬夹成边界射线。
3. 按bag的ring和0.5°方位单元归并。列索引是推断采样位置，不冒充厂家原始发射编号；每帧每格只贡献一个中位观测。
4. 至少3帧支持，并且角度中位绝对偏差满足阈值的位置使用实测中位角度。
5. 对左右半视场分别插值；未观测到的分区边缘延续相邻校正，缺失整行在相邻行与手册边缘锚点间补全。未观测的分区端点方位使用理想单元中心，避免拼接处推定出重合射线。
6. 按行优先展开为46,080个RTX采样槽位；转换方位角正方向，并使用1起始的channelId。真实ring需查NPZ映射。

每束射线都保留。观测次数仅用于判断校正可信度，**不会作为仿真回波掩码**。bag里的物体距离没有写入资产，仿真距离来自当前场景的真实求交。

| source代码 | 数量 | 含义 |
|---|---:|---|
| 0 | 30,910 | 多帧稳定实测 |
| 1 | 6,003 | 同一半视场内部的水平插值 |
| 2 | 7,247 | 未观测分区边缘的校正延续 |
| 3 | 960 | 缺失ring插值 |
| 4 | 960 | 手册锚点/理想补全 |

这不是完整工厂标定。特别是缺失的0/1/94/95行、观测不到的方位区域和安装坐标，仍依赖已记录的补全假设。

标称240°×80°表示采样单元覆盖；边界射线位于单元内部，不要求首末射线角度差恰好240°和80°。生成表的水平射线中心约−119.8853°到119.9403°，垂直中心约−39.5833°到39.5833°。

40帧拟合、10帧独立留出对比中：已有实测支持位置的方向误差95分位约0.0700°；全部留出有效观测为约0.1023°。这反映对该短录制的角度一致性，不是雷达测距精度，也不是补全区域的实测真值。

## 读取角度表

```python
import numpy as np
rays = np.load('calibration/rays.npz', allow_pickle=False)
azimuth = rays['azimuth_deg']       # (96,480), degree
elevation = rays['elevation_deg']   # (96,480), degree
unit_vectors = rays['directions']  # (96,480,3), asset frame
origin = rays['source']            # 0..4 provenance
support = rays['observation_frames']
```

## 参考

输入规格来自 `inputs/NZ3&5_Specification V4.0_20260521.pdf` 第2–3页，原始bag的SHA-256保存在manifest中。参考目录中的NVIDIA源文件保留其原始许可声明；旧模板中的注释和未使用属性不是本资产的规范来源。

- [NVIDIA Isaac Sim 6.0 RTX Lidar](https://docs.isaacsim.omniverse.nvidia.com/6.0.0/sensors/isaacsim_sensors_rtx_lidar.html)
- [NVIDIA experimental RTX API](https://docs.isaacsim.omniverse.nvidia.com/6.0.0/py/source/extensions/isaacsim.sensors.experimental.rtx/docs/index.html)

本资产按目标机器的6.0.1-rc.7接口开发，不保证旧版Isaac Sim兼容。

## 报告与验收证据

正式报告、精选验收摘要和必要配图见 [报告索引](docs/reports/README.md)。原始采集、逐帧状态和性能追踪保留在原运行目录，由仓库忽略规则排除。
