# 鱼眼相机与整机运动交付记录

日期：2026-09-21，北京时间。目标：新实例 `120.209.70.195:30729`，项目 `/root/gpufree-data/semantic/scripts/260920SensorVisualizer`。执行渠道：Codex，经既有主机校验的 SSH，项目范围部署与独立 GUI 验证。

## 改动

- 新建 `combine_scene_14_fisheye.usda`，引用 scene 13，显式保留米制、Z up、60 Hz、默认 prim 及原渲染设置，添加 swing_link 下的 OpenCV 鱼眼相机。
- 新建 `sensor_visualizer` 包，源于旧 LiDAR 包的可信本地副本；来源哈希见 source_provenance.json。旧项目文件未改。
- 新增平面整机位姿/速度控制、相机预览、截图及 PNG/JSONL 保存，仍由原 ArticulationMotion 统一写入状态。
- 新包的雷达发布与相机保存使用零时刻对齐的采样节拍。源雷达 USD 不改；默认仍为仿真 10 Hz。
- 新增运行入口、项目启动器、验证脚本与 FISHEYE_USAGE.md。启动器仅在子进程选择空白初始模板，禁用本次 Kit 偏好持久化，避免初始默认环境加载影响；安装文件不改。

## 实测

- `tools/test_base_control.py`：6 项通过，包含倒车、圆弧积分、保持初始倾斜、直接跳转/复位、非法输入原子性、不同启动时间的采样相位一致性。
- 独立 GUI 进程验证了新场景加载、面板创建、直接整机位姿、前进/后退和转向、关节调整不覆盖整机方向、暂停、复位、截图、录制结束及同进程关闭后重新运行。
- result.json：passed=true，rerun_passed=true。测试进程已退出，用户原 Isaac 进程未结束。
- 正式测试会话：`reports/fisheye_motion/recordings/20260921_155135_299321_2ea51f`。
- MCAP 读取验证：13 路雷达各 10 帧非空点云；10 张 PNG 都有 13 路同时间戳点云（容差 1 微秒），范围仿真 0.3–1.2 秒。
- 图像位姿匹配失败为 0；保存索引唯一且递增，文件完整。渲染 CameraParams 和保存相机矩阵的最大绝对差约 8.88e-16。
- PNG 已人工查看：圆形鱼眼视野、地面网格弯曲、挖掘机及环境可见。SDK 的旧 cameraModel 字段仍为 pinhole，不能据此判定畸变没开启；实际镜头模型单独标记为 opencvFisheye。
- 最终 Kit 日志没有 `[Error]` 或 Python traceback。仍有已有 SDK 警告，包括 MotionBVH 关闭、Hydra 接口释放/性能提示、音频不可用及关闭 stage 的引用计数提示。本次没有改动驱动或系统来压制它们。

## 原文件与范围

- scene 13 SHA256 始终为 `780cab54e1067c3fef6c2a66b0e6b5776c06164645957f7716bbc159c9e8c4d6`。
- 最终 scene 14 SHA256 为 `1438bd8d0baf3e682637735385920a58719873e7b089d479b28730e93a44831e`，验证前后未变。
- 场景13、挖掘机资产、雷达资产及旧项目均未覆盖。新文件的开发中间版本/初次验证日志保留在本报告目录。
- 未安装/升级依赖；未修改系统 Python、ROS 安装、驱动、SSH、桌面组件或系统服务。
- 测试使用私有 DDS domain 138；交付配置仍为 domain 0。测试数据单独位于 reports。
- 源代码、文档、场景14副本和验证报告同步本地；完整验证 MCAP 留在远端，本地只保存报告与示例图。

## 限制和回退

相机是理想仿真镜头，未做实机标定；整机采用规定平面运动，无履带动力学/地形响应。相机图像保存到 PNG/JSONL，不发布 ROS Image/CameraInfo，也不写入 MCAP。录制开始/结束时仍可能受到 ROS 订阅建立或退出的边界影响，关联数据应使用实际时间戳。

回退：关闭新会话，重新打开 scene 13，运行旧项目入口。无系统级恢复步骤。
