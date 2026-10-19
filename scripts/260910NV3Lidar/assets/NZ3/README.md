# NZ3 标准 RTX 雷达资产

在 Isaac Sim 中引用 **MyNZ3.usda**。保留 `config/NZ3_scan.usda` 和 `geometry/NZ3_housing.usda` 与入口的相对位置，复制整个 NZ3 目录即可搬迁。

默认根节点为 `NZ3`，内部包含：

- `sensor`：OmniLidar，完整的实测校正扫描配置。
- `geometry`：Blender 制作的简易 NZ3 外壳，含网格与基础材质。整体宽71、高100、深86 mm；7个网格、1,076个三角形。不含刚体和碰撞体。

扫描模型为标称水平240°、垂直80°、480列×96行，共46,080个采样位置；采用 bag 实测稳定方向与缺失区域补全。边界射线位于采样单元内部。只有这一套扫描配置。

根节点以射线发射原点为基准，单位为米，+X向前、+Y向左、+Z向上。通过根节点设置安装位置和旋转；传感器局部位姿为单位变换。外壳中心与扫描原点重合，外壳底面为局部Z=-0.05 m。手册只有整体尺寸和外观图，窗面形状及光学中心相对外壳的位置均为近似，尚未机械标定。

入口在 `sensor` 上固化 `omni:sensor:Core:rangeOffsetM = 0.08`，使距发射原点8 cm以内的几何不遮挡本雷达。外壳最远顶点约7.188 cm，完整处于该范围内；原有 `nearRangeM = 0.2` 保持不变。这是按距离排除全部近处几何，不是按外壳对象编号排除；该范围内其他物体也会被忽略。外壳仍可见，其他雷达可以探测它。请保持资产根节点缩放为(1,1,1)，改变外壳尺度或位置时需重新核对它是否完全处于8 cm内。

扫描角度、数量、编号和必要运行属性都保存在USD中；使用资产不需要 bag、NPZ、`build_asset.py` 或 `load_nz3()`。点云读取、显示和ROS发布由场景连接标准RTX输出流程。资产不创建输出图、不自动显示点云。

例如，在已经打开的场景中添加引用：

```python
import omni.usd
from pxr import UsdGeom, Gf

stage = omni.usd.get_context().get_stage()
path = '/World/Vehicle/Sensors/NZ3'  # 选择尚未占用的节点路径
asset = '/root/gpufree-data/IsaacSim_Asset/sensor_set/lidar_set/NZ3/MyNZ3.usda'
root = stage.DefinePrim(path, 'Xform')
root.GetReferences().AddReference(asset)
UsdGeom.XformCommonAPI(root).SetTranslate(Gf.Vec3d(0, 0, 1.5))
# 在场景的标准RTX输出流程中选择 path + '/sensor'。
```

输出的 `emitterId` 对应行优先采样位置：`ring = emitterId // 480`，`column = emitterId % 480`。配置文件的channelId为1–46080；目标版本的GMO输出将channelId转换为0–46079，与emitterId一致，两者都不是96行ring。不要对输出点云再应用方位角镜像；RTX符号转换已固化在配置中。

46,080是配置的采样位置数。有效回波数量会受到场景命中及RTX自身回波筛选影响；本资产不保证每一帧都返回46,080个有效点。

当前为瞬时整帧采集。只验证视场角和采样几何，配置中的10Hz不作为瞬时模式实际输出节奏的保证；缺失区域补全、真实时序、噪声与反射率的设备级一致性均不属于本版验证结论。

运行环境为目标机器的Isaac Sim 6.0.1-rc.7，需要启用标准RTX雷达相关扩展。目标机的库搜索路径需能找到Kit自带Python库和NVIDIA雷达校验实现库；这是应用环境要求，USDA本身不修复动态库路径。制作目录中的 `tools/run_reference_validation.sh` 给出了仅对独立测试进程生效的环境设置。

本地制作、校准依据与完整验收报告保存在 `scripts/260910NV3Lidar`。`source/housing/NZ3_housing.blend` 为可编辑源文件，`tools/build_housing_blender.py` 为参数化建模脚本，`reports/housing_build/latest.json` 指向Blender预览；`docs/reports/reference_asset/latest.json` 指向最新RTX验收与部署记录。本地目录中旧名称 `NZ3.usda` 是兼容入口，新场景使用 `MyNZ3.usda`。
