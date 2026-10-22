# NZ3 简易外壳源文件

`NZ3_housing.blend` 是远端 Blender 5.1.1 生成的可编辑网格源文件。外壳导出为 `../../assets/NZ3/geometry/NZ3_housing.usda`，由标准入口 `MyNZ3.usda` 引用。运行资产不依赖 Blender。

整体尺寸来自规格书：宽71、高100、深86 mm。按资产坐标换算为 X=0.086、Y=0.071、Z=0.100 m。+X朝向正面窗，+Y向左，+Z向上。模型围绕现有扫描原点居中，底面Z=-0.05 m。外观采用圆角主体、顶部盖板、三个深色窗面、后盖和薄底座，共7个网格、1,076个三角形；使用基础USD Preview Surface材质，无贴图依赖、刚体和碰撞体。

封面图不提供详细机械结构，窗面、盖板和圆角比例为简化近似。光学中心相对外壳的位置未经过机械标定。外壳是视觉附件，不用于验证设备安装孔、内部结构、重量或材料的真实光学性能。

网格最大顶点半径为 `housing_manifest.json` 中记录的约0.071879 m。参数化脚本以该半径加5 mm余量后向上取整到5 mm，得到入口的 `rangeOffsetM = 0.08`。它忽略本雷达周围8 cm内的所有几何，保留 `nearRangeM = 0.2`；不是针对某个网格的排除名单。单独调整外壳、改变雷达原点或缩放资产后，需重新核对覆盖半径。

在本地制作目录执行：

```powershell
python tools/remote_build_housing.py
python build_asset.py --asset-only
python tools/deploy_reference_asset.py
```

脚本读取交互密码或临时环境变量 `NZ3_REMOTE_PASSWORD`，不会把密码保存到文件。远端建模命令使用 `env -u LD_LIBRARY_PATH /opt/blender/blender --background --factory-startup`，避免系统TBB库覆盖Blender自带库；不修改系统环境配置。

Blender预览和完整构建日志位于 `../../reports/housing_build/`，最新结果由其中的 `latest.json` 指向。源文件只保存资产本体；预览地面、灯光、相机在导出和保存之后添加，不进入资产。

RTX验收位于 `../../reports/reference_asset/`。验收包含关闭近距离忽略的反例、开启后的封闭房间点云、原资产对比、多雷达姿态、保存重开、相对路径搬迁和正式部署后检查。多雷达场景中的其他外壳参与正常求交，其黑色或掠射面允许缺少有效回波；报告区分这些回波与必须完整覆盖的环境射线。
