# 鱼眼相机与整机移动（scene 14）

## 场景和入口

新场景：`/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_14_fisheye.usda`。

它以 scene 13 为 sublayer，仅增加鱼眼相机。原 scene 13、挖掘机资产、雷达资产没有被修改。新场景仍依赖 scene 13 及其资产文件，迁移时应一起保留。

在远端桌面的终端启动：

```bash
bash /root/gpufree-data/semantic/scripts/260920SensorVisualizer/tools/open_fisheye_stage.sh
```

在 Script Editor 打开并运行：

```text
/root/gpufree-data/semantic/scripts/260920SensorVisualizer/run_in_isaac.py
```

选择 Scripted，点击 Play Simulation。启动初始状态为整机停止、关节 Hold。再次运行入口会先关闭上一次项目会话，包括旧 LiDAR 项目会话。

## 面板操作

- **Whole Excavator Motion**：World X / Y 是世界坐标（米）；Heading 是车体前向轴在世界 XY 平面的方位角（度）。填写后 Apply Pose 立即生效。只改变平面位置和方位，保留初始高度与倾斜。
- **Start Move**：Speed 单位 m/s，正值沿车体前向的水平投影前进，负值后退；Yaw rate 单位 deg/s，绕世界 +Z 正向旋转。两者可同时执行。速度以仿真时间计。
- **Hold Base** 停止整机运动；**Reset Base** 恢复初始位置和方向。二者不复位大臂等关节。Pause 冻结时间；恢复 Play 后继续先前速度。Stop 或关闭会话恢复整机和关节初始状态。
- **Joint Control** 继续支持直接角度、目标角度+速度、周期运动。cab–track 关节维持初始角度。调整关节不会覆盖已经设置的整机方位。
- **Fisheye Camera → Open Camera View** 打开相机视图；**Save Image Snapshot** 保存最近一个完成时间/位姿匹配的图像及元数据，暂停时可保存已有帧。
- **Start Recording / Stop Recording** 同时管理 MCAP 和鱼眼图像。应先 Stop Recording，再 Pause/Stop。暂停期间不重复保存静止帧。
- LiDAR Mount Adjustment 保持原用法。开始调整会结束当前录制，恢复后开始新的录制会话。

RViz 在另一个远端桌面终端运行：

```bash
python3 /root/gpufree-data/semantic/scripts/260920SensorVisualizer/launch_rviz.py
```

RViz 查看雷达点云；相机通过 Isaac 相机视图查看。本版未向 ROS 发布 Image/CameraInfo，图像不写入 MCAP。

## 保存结构

默认输出：`/root/gpufree-data/semantic/output/sensor_visualizer/<会话>/`。

```text
<会话>/
  session.json                  现有雷达、场景和录制元数据
  bag/                          ROS 2 MCAP，点云/TF/Clock/关节/整机位姿
  recorder.log
  qos_overrides.yaml
  cameras/fisheye_front/
    calibration.json            分辨率、内参、畸变模型、坐标/时间定义
    frames.jsonl                每行对应一个成功保存的 PNG
    summary.json                保存数量、无法匹配数量、错误（如有）
    images/000000_<仿真纳秒>.png
```

独立截图放在输出目录下 `camera_snapshots/<时间>/`，含 image.png、frame.json、calibration.json。

JSONL 包含实际图像仿真时间、整机位姿、实际关节角度、相机相对父节点/根参考系及世界坐标的矩阵、各雷达对应世界矩阵。矩阵采用 **USD/Gf 行向量**：`p_world = p_local @ local_to_world`。光学坐标为 X 向右、Y 向下、Z 向前；USD 相机为 X 向右、Y 向上、-Z 向前。两者矩阵分别明确保存。

图像时间来自同一 render product 的 `IsaacReadSimulationTime` annotator。运动模块逐帧缓存姿态，按渲染时间匹配，并与 `CameraParams.cameraViewTransform` 独立核对。匹配失败不拼接伪造的图像/姿态组合，计入 unmatched。MCAP 按消息 header 时间关联，不能用文件顺序关联。

当前 SDK 的 `CameraParams.cameraModel` 仍返回基础投影模型 `pinhole`，它不是现代镜头畸变模型。本项目将其另存为 `renderer_projection_model_legacy`，实际镜头记录为 `lens_distortion_model=opencvFisheye`；鱼眼畸变已经在 PNG 中实际渲染。

## 相机和运动约定

- `/World/Excavator/swing_link/FisheyeFront`：相对 swing_link `(0.6, -0.9, 2.2)` m，朝父节点 +X，俯视 10°。
- 1024×1024，理想等距 OpenCV fisheye：fx=fy=1024/π，cx=cy=512，k1…k4=0。覆盖约 180°，本机渲染输出为圆形有效视野、四角黑色。
- 参数是仿真模型，尚未对任何实物鱼眼镜头标定。
- 图像默认按仿真 10 Hz 保存，可在 `config/sensors.json` 修改 save_rate_hz。采集频率需要整除 60 Hz 仿真频率，例如 5/10/15/20/30 Hz；图像与雷达按零时刻对齐的时间网格采样，默认 0.1、0.2、0.3 秒……。开始录制不重置采样相位。分辨率必须与 USD 内参的 imageSize 一致。
- 相机安装位姿在新 USD 的相机 transform 中编辑。脚本不会自动将运行时变化保存到磁盘 USD。
- 当前只接受 `instantLidar=true` 的雷达，不改动源雷达发射参数；`scanType=SOLID_STATE` 与 Instant 是两个不同属性。场景和传感器在一次姿态更新后进入渲染；PNG 和点云通过各自实际时间戳关联。
- 继续保留仿真时间步长 1/60 秒及不高于 0.1 的真实时间倍率限制。增加相机可能让实际倍率更低。
- 整机采用规定运动，不包含履带动力学、地形贴合、碰撞推挤或打滑。

## 模块与一帧顺序

1. `ArticulationMotion.tick()`：按仿真 dt 更新 `JointController` 和 `BaseController`。
2. `_apply_controlled_base()` / `_apply()`：写入整机和 DOF，刷新 articulation kinematics / USD 链接变换。
3. `snapshot()` / `CameraCapture.remember()`：缓存本次仿真状态，现有图节点发布 TF、Clock 和关节/整机状态。
4. RTX 在该场景状态下计算 Instant LiDAR 和鱼眼 RGB。
5. `FrameWriter.write()` / `CameraCapture.receive()`：读取同一相机 render product 的 RGB、渲染时间和 CameraParams，匹配状态。
6. 相机保存 PNG+JSONL；现有 `CloudPublishers` 发布点云，`Recorder` 使用 rosbag2 保存 MCAP。

代码来源：原 `260907LidarVisualizer/lidar_visualizer` 的独立复制版本，改名为 `sensor_visualizer`，源文件校验记录在 `reports/fisheye_motion/source_provenance.json`。新入口使用新包，不改旧项目。

## 验证与回退

纯数学检查：`python3 tools/test_base_control.py`。

完整验证脚本 `tools/validate_fisheye_motion.py` 应在单独 Kit GUI 进程中通过本项目 launcher 运行；使用私有 DDS domain 138 和 reports 下的输出，不在用户运行窗口直接执行。报告为 `reports/fisheye_motion/result.json`。

回退只需关闭新会话，重新打开 scene 13 并使用旧项目入口。无需恢复系统库、驱动或桌面环境。
