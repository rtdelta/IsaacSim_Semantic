# 四路鱼眼相机（scene 15）

新场景：`/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_15_surround_fisheye.usda`。

## 运行

远端桌面终端：

```bash
bash /root/gpufree-data/semantic/scripts/260920SensorVisualizer/tools/open_surround_stage.sh
```

在 Script Editor 打开并运行：

```text
/root/gpufree-data/semantic/scripts/260920SensorVisualizer/run_in_isaac.py
```

点击 **Play Simulation**。`Fisheye Cameras` 中选择 Front / Rear / Left / Right，再点 **Open Camera View**。可分别打开多个视图；每个方向重新打开会关闭它先前的预览窗口。

**Save All Camera Snapshot** 保存最近一组四路同时间戳图像。**Start Recording / Stop Recording** 管理四路图像和现有雷达 MCAP。停止后再暂停或 Stop 仿真。整机运动与关节面板用法保持原样。

RViz：

```bash
python3 /root/gpufree-data/semantic/scripts/260920SensorVisualizer/launch_rviz.py
```

## 相机来源和安装

四个 Camera 均通过 USD Reference 引用：

```text
/root/gpufree-data/IsaacSim_Asset/sensor_set/camera_set/fish_eye_camera/fish_eye_camera.usda
prim: /World/FisheyeCamera
```

只引用 Camera 子节点，保留内参、畸变、曝光；不导入资产的示例灯光和编辑器 RenderProduct。参考资产的原位姿和缩放在新场景覆盖为刚体安装变换，缩放为 1。旧 `aif:lidarToCamera` 外参在新场景被 USD value block 屏蔽，新外参从实际安装位置计算。源资产原文件不改。

四台均安装在 `/World/Excavator/swing_link` 下，向下俯视 10°，方向相对该父节点：

| ID | Camera 节点 | 初始位置参照 | 朝向水平分量 |
|---|---|---|---|
| front | FisheyeFront | MyAiry_front/sensor | +X |
| rear | FisheyeRear | MyAiry_back/sensor | −X |
| left | FisheyeLeft | MyAiry_left/sensor | +Y |
| right | FisheyeRight | MyAiry_right/sensor | −Y |

装配时从组合后的雷达感知节点读取原点，再转换到共同父节点。位置只复制一次；之后修改雷达安装位置不会自动移动相机。整机运动会使两者共同跟随车体。具体安装坐标见 `reports/surround_fisheye/assembly.json`。

分辨率直接读取资产的 `omni:lensdistortion:opencvFisheye:imageSize`，当前为 **1920×1080**。模型为 OpenCV Fisheye，使用已有的非零 k1…k4。视场由这些内参与畸变决定，不沿用 scene 14 理想鱼眼的视场设置。资产另有 `aif:fisheye:*` 原始描述，当前 RTX 渲染使用 `omni:lensdistortion:*` 参数。

## 同步及文件组织

默认仿真采样 10 Hz（0.1、0.2、0.3 秒……），主循环仍限制真实时间倍率不高于 0.1。四路完整分辨率渲染和 PNG 压缩可能降低实际倍率。

```text
/root/gpufree-data/semantic/output/sensor_visualizer/<会话>/
  bag/                         13 路点云、TF、Clock、关节、整机位姿 MCAP
  session.json
  capture_index.jsonl          完整四路采集组的提交索引
  capture_summary.json         组数、缺帧组数、错误
  capture_drops.jsonl           被丢弃的组及缺失相机
  cameras/
    front/
      calibration.json
      frames.jsonl
      summary.json
      images/<组号>_<仿真纳秒>.png
    rear/                      结构同上
    left/
    right/
```

优先读取 `capture_index.jsonl`，其中每行对应四张同时间戳的图片。图片文件名的组号和仿真时间四路一致。每台的 `frames.jsonl` 保留对应的实际关节、整机位姿、相机外参和雷达位姿。标定文件记录引用的资产、组装时源文件哈希、实际加载的内参和曝光。

图像必须同时满足渲染时间与缓存运动状态匹配、CameraParams 相机变换匹配。汇集器按时间戳等待四路，不使用上一帧补齐；最多缓存三组。缺帧超出缓存范围或录制停止时会记录缺失相机。落盘时先写齐四张图片，再提交采集组索引；若存储失败，以索引为准，不把未提交文件当成完整组。

独立四路截图位于 `camera_snapshots/<时间>/`，内含 front/rear/left/right 各自的 image.png、frame.json、calibration.json，以及公共 capture.json。

图像仍以 PNG/JSON 保存，未发布 ROS Image/CameraInfo，未写入 MCAP。点云按消息 header 仿真时间与图像关联；订阅启动、录制结束及通信异常可能造成边界缺失，不能用文件序号代替时间戳。

## 一帧和代码模块

1. `ArticulationMotion.tick()` 更新整机和关节并同步 USD/Fabric 变换。
2. `CameraRig.remember()` 统一接收一次状态，向四台 `CameraCapture` 分发同一个变换缓存和雷达位姿。
3. RTX 生成四路鱼眼 RGB 和 Instant LiDAR 数据。
4. 各 `FrameWriter` 返回图像及其渲染时间，`CameraCapture.receive()` 验证时间/姿态匹配。
5. `FrameGroups` 按时间戳汇集四路，`CameraRig._save_group()` 保存完整组；原 ROS 链路保存同节拍点云。

`config/sensors.json` 的 `cameras` 列表描述四路；原 `camera` 条目保留供 scene 14 使用。打开 scene 14 时自动选择单相机路径，输出格式维持单相机版本。scene 15 使用四相机列表，缺节点时明确报错。

scene 15 引用 scene 13 及原相机资产。旧 scene 13/14、旧 LiDAR 项目和相机源文件均保留，迁移时需携带被引用的资产。回退可打开 scene 14；完整源码修改前备份位于 `reports/surround_fisheye/before/`。
