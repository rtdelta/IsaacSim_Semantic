# 四路鱼眼部署与验证

时间：2026-09-21，北京时间。执行：Codex 经主机校验的 SSH；新实例 `120.209.70.195:30729`。

## 实现结果

- 新建 `/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_15_surround_fisheye.usda`，以 scene 13 为 sublayer。
- 四台 Camera 分别引用既有 `sensor_set/camera_set/fish_eye_camera/fish_eye_camera.usda` 的 `/World/FisheyeCamera`；仅在新场景覆盖安装刚体变换、tickRate 和旧外参屏蔽值。原内参、非零 OpenCV 畸变系数、曝光属性逐项一致。
- 四路位置复制自 MyAiry_front/back/left/right 的 sensor 原点，朝父坐标 +X/−X/+Y/−Y，俯视 10°。源资产的旧非单位缩放不进入新的安装姿态。
- CameraRig 统一分发逐帧运动状态；FrameGroups 汇集相同时间戳的四路图像。四张 PNG 全部写完后才提交 capture_index；缺失组记日志，不借用旧图像。
- 增加四方向预览选择、整组截图。保留仿真 10 Hz 保存和不高于 0.1 的真实时间倍率限制。
- 原单相机 scene 14 继续兼容；整机移动、关节控制、雷达发布、MCAP 保存链路保留。

## 验证证据

- `test_frame_groups.py` 四项通过：相机回调乱序、延迟帧不串帧、缺路缓冲上限、停止时保存末尾完整组。
- 独立 GUI 进程、ROS domain 139，验证 scene 15 初始化、实际渲染、预览、四路截图、整机前后/转向运动、保存、暂停/复位、同进程再次运行，以及切换 scene 14 后单相机继续出图。
- `result.json`：passed=true，rerun_passed=true，scene14_compatible=true。测试进程已退出。
- 正式验证会话：`reports/surround_fisheye/recordings/20260921_181528_054957_cdb6ab`。
- 11 组、每路 11 张，共 44 张 1920×1080 PNG；缺失组 0，图像位姿匹配失败 0。
- MCAP 解读核验：13 路雷达各 11 帧非空点云；每组四张图像对应相同时间戳，全部匹配 13 路点云（时间容差 1 微秒），四路记录的整机和关节状态一致。
- 运动中相机和对应雷达原点最大差约 1.20e-15 m；渲染 CameraParams 与保存相机矩阵最大元素差约 1.33e-15。
- 四路示例图已逐张查看，朝向合理，地面/环境可见，没有被传感器外壳整体遮黑。前向可见大臂、铲斗等正常几何遮挡，未隐藏车体或环境。
- 渲染日志没有 `[Error]` 或 Python traceback。保留既有 SDK 的音频、MotionBVH、Hydra 接口及 stage 关闭引用计数等警告，未通过系统修改压制。

## 文件和边界

新场景 SHA256：`a4973d82ae29434b559742c5c4ce81c6b3d40cc7eeba47f4d731aca44ee92a09`。

以下源文件在验证前后哈希未变：

- 相机源资产：`6734ada88db53b8c9310372ffd2c25df309fa63207f57029fa14e80c2c716b48`。
- scene 13：`780cab54e1067c3fef6c2a66b0e6b5776c06164645957f7716bbc159c9e8c4d6`。
- scene 14：`1438bd8d0baf3e682637735385920a58719873e7b089d479b28730e93a44831e`。

更新限定在 `260920SensorVisualizer` 项目内，修改前源码备份在本目录 before/。旧 `260907LidarVisualizer` 项目、雷达资产、挖掘机资产未修改。无依赖安装或升级，无系统 Python、驱动、SSH、桌面组件或系统服务改动。

本地与云端保存本次源代码和文档。本地另外保存 scene 15 副本、原相机源文件只读快照、验证报告和四张示例图；完整测试采集数据留在云端 reports 子目录。文件传输哈希清单见 deployment.json。

本次图像仍保存为 PNG/JSON，未发布 ROS Image/CameraInfo、未写入 MCAP。相机与雷达的位置只在装配时对齐，随后独立调整。源相机真实硬件标定来源未重新认证，本次复用资产中当前生效的参数。

回退：关闭项目会话，打开 scene 14 运行同一入口即可使用单相机；如需恢复全部旧源码，用 before/ 中备份恢复本次变更文件，新增代码可留存但不被旧版本引用。
