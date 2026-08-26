# SG1-OX01F10C-GMSL-H60F 相机参数与 Isaac Sim 仿真修改说明

## 1. 现实相机 SG1-OX01F10C-GMSL-H60F 的参数

以下参数来自已提供的《SG1-OX01F10C-GMSL-Hxxx 摄像模组产品规格书》中 H60F 型号对应行及该系列通用参数。

### 1.1 成像与传感器参数

| 参数 | 数值或说明 |
|---|---|
| 相机型号 | SG1-OX01F10C-GMSL-H60F |
| 图像传感器 | OmniVision OX01F10RGGB，1.3 MP |
| 传感器规格 | 1/3.55 inch CMOS |
| 输出分辨率 | 1280H × 720V |
| 像元尺寸 | 2.8 μm |
| 像元结构 | BSI（背照式） |
| 输出帧率 | 1280 × 720 @ 30 fps |
| HDR | 最高 120 dB |
| 输出数据 | Parallel / YUV422 8-bit |
| ISP | 规格书标注为“/”，未给出独立 ISP 参数 |

根据输出像素数和像元尺寸，可推算输出像素区域约为：

- 水平尺寸：`1280 × 0.0028 mm = 3.584 mm`
- 垂直尺寸：`720 × 0.0028 mm = 2.016 mm`

以上 `3.584 mm × 2.016 mm` 是根据输出像素区域推算的尺寸，不等同于厂家正式提供的完整传感器有效感光面标定值。

### 1.2 H60F 镜头参数

| 参数 | 数值 |
|---|---:|
| 水平视场角 HFOV | 59° |
| 垂直视场角 VFOV | 32° |
| 有效焦距 EFL | 3.6 mm |
| 光圈 F.No | 1.2 |
| 防水等级 | IP67 |

### 1.3 接口和结构参数

| 参数 | 数值或说明 |
|---|---|
| 串行器 | MAXIM MAX96705 |
| 相机接口 | 同轴 |
| 供电 | 5～16 V PoC |
| 工作电流 | < 200 mA |
| 连接器 | 安费诺 Z Type Fakra |
| 工作温度 | -40～+85 ℃ |
| 模组尺寸 | 30 mm × 30 mm × 22.5 mm |
| 重量 | < 50 g |

规格书没有提供以下相机标定数据：

- 光心坐标 `cx、cy`
- 相机内参矩阵 `K`
- 径向畸变系数 `k1、k2、…`
- 切向畸变系数 `p1、p2`
- 其他薄棱镜畸变系数

因此，仅依靠当前规格书可以确定分辨率和标称视场角，但不能还原真实 H60F 镜头的完整畸变效果。

## 2. 远端 Isaac Sim 仿真相机应该修改的参数

### 2.1 修改对象

远端基础场景：

```text
/root/gpufree-data/stage_material_set/combine_stage/Combine_Scene_02.usda
```

目标 Camera prim：

```text
/Fangshan_Excavator_01/boom_prim/Camera
```

该 Camera prim 当前能够正常组合和加载。现有 RenderProduct 已指向该 Camera，输出分辨率已经是 `1280 × 720`。

### 2.2 优先目标

本次仿真修改优先保证：

1. 输出分辨率为 `1280 × 720`。
2. 水平视场角为 `59°`。
3. 垂直视场角为 `32°`。

为了直接控制输出图像的视场角，应在 Camera prim 上使用 Isaac Sim 6.0.1 支持的 OpenCV Pinhole 相机模型，而不是只修改 USD 的 `focalLength`。

### 2.3 必须增加或修改的参数

#### 2.3.1 应用 OpenCV Pinhole API Schema

在目标 Camera prim 上应用：

```text
OmniLensDistortionOpenCvPinholeAPI
```

并设置镜头模型：

```text
omni:lensdistortion:model = "opencvPinhole"
```

#### 2.3.2 设置相机模型使用的图像尺寸

```text
omni:lensdistortion:opencvPinhole:imageSize = (1280, 720)
```

同时保持目标 RenderProduct：

```text
resolution = (1280, 720)
pixelAspectRatio = 1.0
```

当前 RenderProduct 的 `resolution` 已经是 `(1280, 720)`，因此只需确认，不需要重复修改。

#### 2.3.3 设置与 59° × 32° 视场角对应的 fx 和 fy

OpenCV 相机模型使用像素焦距 `fx、fy` 控制水平和垂直视场角：

```text
fx = 图像宽度 / (2 × tan(水平视场角 / 2))
fy = 图像高度 / (2 × tan(垂直视场角 / 2))
```

将 `1280 × 720` 和 `59° × 32°` 代入后得到：

```text
omni:lensdistortion:opencvPinhole:fx = 1131.196
omni:lensdistortion:opencvPinhole:fy = 1255.469
```

这两个值是根据已知分辨率和标称视场角计算得到的仿真目标值，用于优先保证最终渲染图像的视场范围；它们不是厂家提供的真实相机标定结果。

#### 2.3.4 光心 cx、cy 暂不填写最终值

还需要设置：

```text
omni:lensdistortion:opencvPinhole:cx
omni:lensdistortion:opencvPinhole:cy
```

但规格书没有提供真实光心坐标，因此当前不能给出最终值。若要按真实相机配置，需要补充以下任一资料：

- H60F 厂家标定文件；
- 相机内参矩阵 `K`；
- 明确的 `fx、fy、cx、cy`；
- 真实相机拍摄标定板后得到的标定结果。

在没有这些资料前，不应把图像中心假定值当作真实相机标定值写入最终场景。

#### 2.3.5 畸变参数暂不填写最终值

OpenCV Pinhole 模型还支持：

```text
k1、k2、k3、k4、k5、k6
p1、p2
s1、s2、s3、s4
```

规格书没有提供这些畸变系数，因此当前不能恢复真实 H60F 镜头的边缘弯曲效果。获得厂家或实物标定数据后，再写入对应参数。在没有标定资料时，不应自行编造畸变系数。

### 2.4 应同步修改的物理镜头描述参数

为了让 USD Camera 中显示的物理镜头信息不再保留当前通用 Kit 相机值，可同步修改：

| USD Camera 参数 | 当前生效值 | H60F 物理值 | 当前米制 Stage 中应写入的 USD 值 | 说明 |
|---|---:|---:|---:|---|
| `focalLength` | 18.147562 | 3.6 mm | 0.036 | 来自 H60F 规格书 EFL |
| `horizontalAperture` | 20.955，USD 默认值 | 3.584 mm | 0.03584 | 由 1280 像素和 2.8 μm 推算 |
| `verticalAperture` | 15.2908，USD 默认值 | 2.016 mm | 0.02016 | 由 720 像素和 2.8 μm 推算 |
| `horizontalApertureOffset` | 0 | 无标定值 | 暂不修改 | 真实光心未知 |
| `verticalApertureOffset` | 0 | 无标定值 | 暂不修改 | 真实光心未知 |

当前 Stage 的 `metersPerUnit = 1`。OpenUSD Camera 的 `focalLength` 与 aperture 属性使用“十分之一个场景单位”，因此这里不能直接写入毫米数值 `3.6、3.584、2.016`。例如 `3.6 mm = 0.0036 m`，对应的 USD 属性值为 `0.0036 / 0.1 = 0.036`。

需要注意：按 `3.6 mm` 焦距和推算的 `3.584 mm × 2.016 mm` 成像面建立无畸变针孔模型时，计算得到的视场角约为 `52.93° × 31.28°`，与规格书标称的 `59° × 32°` 不完全一致。因此，最终视场角应以 OpenCV 模型中的 `fx、fy` 和实际渲染验证结果为准，不能只依靠 `focalLength` 与 aperture 参数。

### 2.5 当前阶段不应修改的参数

以下参数不决定本次优先要求的分辨率和视场角，当前阶段保持原值：

| 参数 | 原因 |
|---|---|
| Camera 的平移、旋转和父子关系 | 决定安装位置和朝向，不决定镜头视场角 |
| `clippingRange` | 决定可见距离范围，不决定视场角 |
| `focusDistance` | 决定对焦距离，不决定视场角 |
| `exposure:fStop`、`exposure:time`、`exposure:responsivity` | 决定画面亮度，不决定视场角 |
| `timeCodesPerSecond` | 是 USD 时间轴速率，不是相机输出帧率 |

H60F 的 `F.No = 1.2` 可以在后续景深和曝光标定阶段用于设置标准 `fStop`。当前不应直接把 RTX 的 `exposure:fStop` 从 5 改成 1.2，因为这会显著改变画面亮度，而规格书没有提供与 Isaac Sim 曝光系统对应的完整参数。

### 2.6 不属于 Camera prim 光学参数的规格

以下真实相机规格不能通过修改 Camera prim 的视场角参数直接实现：

- 30 fps：应在采集脚本中设置每 `1/30` 秒采集一帧。
- 最高 120 dB HDR：需要单独设计曝光、色调映射或多曝光仿真。
- YUV422 8-bit：需要在 Writer 或输出后处理阶段转换。
- MAX96705、GMSL、同轴接口、PoC：属于真实硬件传输链路，不是 USD Camera 光学属性。

### 2.7 推荐实施方式

不直接修改基础场景和挖掘机 payload 文件。建议新建一个只包含 Camera 参数覆盖的场景，例如：

```text
/root/gpufree-data/stage_material_set/combine_stage/Combine_Scene_02_H60F.usda
```

该新场景引用原 `Combine_Scene_02.usda`，只覆盖目标 Camera prim 的相机参数。这样能够保留原场景，并可随时切回修改前的相机配置。
