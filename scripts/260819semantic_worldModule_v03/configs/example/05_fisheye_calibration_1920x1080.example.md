# `05_fisheye_calibration_1920x1080.example.json` 参数说明

该文件用于在 v03 中**动态创建** OpenCV Fisheye Camera，或者明确覆盖传感器标定。示例数值来自已在远端通过 RealTimePathTracing 和 PathTracing 验证的 1920×1080 鱼眼相机。

已有鱼眼 Camera Prim 推荐使用 `read_and_validate` 直接读取 USD，不需要引用本文件。

## 顶层字段

| 顺序 | JSON 路径 | 类型 | 必填 | 含义与填写要求 |
|---:|---|---|---:|---|
| 1 | `model` | 非空字符串 | 建议 | 标定模型审计名称。本项目使用 `opencv_fisheye`。Camera 创建逻辑真正写入的是下面的 `schemas` 和 `attributes`。 |
| 2 | `schemas` | 字符串数组 | 是 | 要应用到新 Camera Prim 的 USD API Schema。OpenCV 鱼眼必须包含 `OmniLensDistortionOpenCvFisheyeAPI`。 |
| 3 | `attributes` | 非空对象 | 是 | 写到新 Camera Prim 的鱼眼标定属性。键必须使用当前 Isaac/Omniverse 支持的完整 USD 属性名。 |
| 4 | `warning` | 字符串 | 否 | 给使用者看的审计说明，驱动不会把它当作标定参数写入 Prim。 |

## `attributes` 字段

以下参数顺序与文件一致，内参和主点单位均为像素。

| 顺序 | 属性 | 类型 | 含义与填写要求 |
|---:|---|---|---|
| 1 | `omni:lensdistortion:opencvFisheye:fx` | 正数 | X 方向焦距 `fx`，单位像素。必须来自目标相机和目标分辨率的真实标定。 |
| 2 | `omni:lensdistortion:opencvFisheye:fy` | 正数 | Y 方向焦距 `fy`，单位像素。 |
| 3 | `omni:lensdistortion:opencvFisheye:cx` | 数字 | 主点 X 坐标 `cx`，以图像左上角为坐标原点。通常接近宽度的一半。 |
| 4 | `omni:lensdistortion:opencvFisheye:cy` | 数字 | 主点 Y 坐标 `cy`，通常接近高度的一半。 |
| 5 | `omni:lensdistortion:opencvFisheye:k1` | 数字 | OpenCV Fisheye 第 1 个角度畸变系数。可以为负数、零或正数。 |
| 6 | `omni:lensdistortion:opencvFisheye:k2` | 数字 | 第 2 个畸变系数。 |
| 7 | `omni:lensdistortion:opencvFisheye:k3` | 数字 | 第 3 个畸变系数。 |
| 8 | `omni:lensdistortion:opencvFisheye:k4` | 数字 | 第 4 个畸变系数。 |
| 9 | `omni:lensdistortion:opencvFisheye:imageSize` | 两个正整数数组 | `[width, height]`，示例为 `[1920, 1080]`。必须与主配置中该相机的 `resolution` 一致。 |

## 主配置引用方式

```json
{
  "type": "camera.fisheye_opencv",
  "source": {
    "mode": "create",
    "parent_prim": "/World/Sensors",
    "prim_name": "CreatedFisheye"
  },
  "resolution": [1920, 1080],
  "calibration": {
    "policy": "from_profile",
    "profile": "05_fisheye_calibration_1920x1080.example.json",
    "expected_model": "opencv_fisheye"
  }
}
```

使用前注意：

- `/World/Sensors` 必须已存在，新建目标路径不能已被占用。
- 不要仅按图像尺寸等比例猜测畸变参数；应使用真实标定结果。
- 如果改变分辨率，需要按标定流程重新获得或正确缩放内参，并同步修改 `imageSize` 和 `resolution`。
- 对已有 `/World/FisheyeCamera`，应优先使用 `policy: read_and_validate`，从 USD 自动读取 `fx/fy/cx/cy/k1...k4` 和 Camera Transform。
