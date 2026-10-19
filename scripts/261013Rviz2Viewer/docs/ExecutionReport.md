# Scene18 自制链路 300 组采集与独立 RViz2 工具交付报告

日期：2026-10-13。运行实例：单卡 L40，使用现有 Isaac Sim、ROS 2 Jazzy、RViz2、NumPy、Pillow、Xvfb，没有新增、下载或更新依赖。

## 完成内容

使用 single06 自制冻结采集链路完成 300 组。独立 RViz2 工具在指定本地目录完成，并已部署远端同名项目目录。回放不依赖 Isaac 进程或旧项目代码，采集使用保留来源哈希的隔离源码副本。

本地：`D:\learning\IntelligentDepartment\CodesSet\Self\260707IsaacSIm\scripts\261013Rviz2Viewer`。

远端源码：`/root/gpufree-data/semantic/scripts/261013Rviz2Viewer`。

场景：`/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_18_terrain_fisheye_mesh.usda`。

场景 SHA-256：`e44ff38c21caaaccf20aa44a9b834e33d7109407e737df27198a63ad95e9fb79`。

## 实际采集参数

直接复用昨天原生包的 300 行原始轨迹，整机 X 速度 0.1 m/s，Yaw/Pitch/Roll 为 ±15°、3°/s 周期运动；boom/arm/bucket 为 ±15°、3°/s，cab-track 关节保持初始角度。末组 X 偏移 2.99 m。逻辑采样 10 Hz，0～29.9 s。

RTX 设置为 RealTimePathTracing（RT2），DLSS=2，AA=3，帧生成关闭，16 预热子帧加 2 正式子帧；传感器保持 `persistent_gated + keepalive`。13 路 Instant LiDAR 和 4 路 1920×1080 鱼眼保持原场景配置。

一组顺序：推进原生仿真时钟 → 暂停并冻结 → 设置本组轨迹姿态 → 预热和正式渲染 → 接受并复制传感器数据 → 读取实际 USD 刚体位姿 → 后台 PNG 编码 → 单写者 MCAP 保存。位姿观察钩子只增加组索引中的五部件世界变换及独立 JSONL，不改变已有运动、扫描或渲染策略。

## 数据位置与结构

正式外层目录：

```text
/root/gpufree-data/semantic/output/261013Rviz2Viewer/20261013_142507_300/
├── motion_parameters.json
├── input_spec.json
├── trajectory/
└── capture/
    ├── result.json
    ├── system_resources.jsonl
    ├── engine.log
    ├── body_poses.jsonl
    ├── viewer_model_validation.json
    ├── viewer_assets/                   # 五部件 STL，单位缩放；锚点及来源 manifest
    └── captures/20261013_142524_685978_f13b03ee/
        ├── bag_unified/
        │   ├── metadata.yaml
        │   ├── bag_unified_0.mcap
        │   ├── bag_unified_1.mcap
        │   └── bag_unified_2.mcap
        ├── viewer_cache/               # 回放 SQLite 和时间审计
        └── viewer_logs/                # 每次播放的发送/接收/调度/RViz 日志
```

3 个 MCAP 文件共同构成一个 ROS 2 bag，按 100 组分段，不是三个不同实验。总大小 **4,185,301,627 字节，约 4.19 GB / 3.90 GiB**。300 组、32 话题、9006 消息；完整话题计数在本地与远端 `reports/bag_topic_counts.json`。

| 内容 | 话题模式 | 消息数量 |
|---|---|---:|
| 13 路点云 | `/lidar/<name>/points` | 各 300，共 3900 |
| 4 路 PNG 图像 | `/camera/{front,back,left,right}/image_raw/compressed` | 各 300，共 1200 |
| 4 路相机参数 | `/camera/<direction>/camera_info` | 共 1200 |
| 4 路相机位姿 | `/camera/<direction>/pose` | 共 1200 |
| TF / 关节 / 整机位姿 / Clock / 逐组索引 | `/tf`、`/joint_states`、`/excavator/root_pose`、`/clock`、`/sensor_visualizer/frame_index` | 各 300，共 1500 |
| 运行及相机元数据 | `/sensor_visualizer/run_metadata`、`/sensor_visualizer/camera_metadata` | 各 3，共 6 |

逻辑组间隔恰为 100,000,000 ns，ROS 消息时间从 133,333,333 ns 到 30,033,333,333 ns。初始化偏移没有算入轨迹逻辑时间。

实际采集耗时 **931.92 s，约 15.53 分钟，3.106 s/组**；进程初始化、采集及关闭合计 989.94 s。10 Hz 是包中仿真时间采样节拍，并非此次离线生成速度。

## 验证结果

3 组试采集、完整 300 组验证均通过，13 路点云与 4 路图像每组齐全，TF 每组 19 条关系。写入数据摘要一致。轨迹根位置最大误差约 1.16e-7 m，关节角最大误差 1.30e-8 rad，TF 矩阵误差约 1.20e-14。

回放采用导出的真实 mesh，原始缩放及 mesh 到刚体的对齐已经烘焙到 STL。五个实际 USD 刚体矩阵与按原始关节锚点重建的运动学比较，300 组全部通过；最大矩阵元素误差 4.73e-6，限值 2e-5。STL 是诊断着色，没有复制原始材质。

真实 ROS 集成测试通过：前进、后退、跳转、两种回放时间模式、模型偏移 ±1 组、HTTP 控制、13 路点云接收。接收到的点云数据哈希匹配源消息发布数据。自制试采集包、自制正式 300 组包与原生 300 组包均进行了这些操作测试；操作集成测试抽查第 0～2 组，不代表整包每一组都做了视觉检查。正式包完整 300 组另有连续发送测试。

| 回放测试 | 发送间隔中位数 | 95% 分位 |
|---|---:|---:|
| 完整 300 组，无 RViz | 99.53 ms | 104.12 ms |
| 完整 300 组，桌面 RViz 启用一路点云 | 99.15 ms | 104.25 ms |

桌面测试最大间隔 105.11 ms，单组发送耗时中位数 11.78 ms，计划发送迟到量 95% 分位 5.01 ms。初始组已经定格发布，播放推进剩余 299 组。统计对应发布器开始发送，**没有测量 RViz 完成绘制、网页远程桌面传输或显示器刷新**，也不是启用全部 13 路显示的性能承诺。

RViz 在既有桌面 `:20` 正常启动，日志报告 OpenGL 4.6；无插件或 mesh 加载错误。该显示服务的 XWD 截图返回黑图，无法用作像素证据。额外使用已有 Xvfb 创建独立 `:88` 显示并以软件 OpenGL 验证了真实画面，确认 Global Status=Ok、五部件 mesh、点云、逐雷达列表及导航工具；此测试不改变桌面和驱动配置。截图保存在 `reports/rviz_isolated_frame150.png`，是第 150 组的隔离显示结果。

启动脚本首次测试时因 `set -u` 与 ROS 环境脚本未定义变量不兼容而退出，已经在本工具的启动脚本中修正，仅在 source ROS 环境时临时取消 nounset。RViz 窗口布局采用本实例已安装的默认布局，修正了初次启动时左侧属性面板占用过宽的问题。

## 时间错位与尚未验证项

新自制包的回放相关消息 **录制时间与消息时间差为 0**，无缺组。对照原生包，在点云、TF、关节及 Clock 的索引范围中发现 29 条消息、19 个组的时间差，最大 100 ms；此统计不含相机图像。与以前包含图像的 30 条/20 组统计范围不同。

同步模式按消息时间重新归组；原始模式按保留的录制时间顺序回放。源 MCAP 和索引里的源 CDR 未被改写。ROS 发布时经过官方反序列化和重新序列化，接收测试核对的是点云数据内容及消息时间，不把 DDS 传输后的完整 CDR 填充字节视为相同。

**时间一致及 mesh 位姿一致还不能证明 RTX 点云几何更新及时。** 工具中的模型 ±1/±2 组偏移用于观察错帧是否改善贴合，并不会修改原始数据。真正的“滞后一帧”仍须定格对照或逐组点到 mesh 表面的定量误差分析才能确认。

跨话题 DDS 发布和 RViz 绘制不是原子事务，连续播放的瞬间可能显示不同话题的新旧数据。严格贴合比较应暂停后查看。后退和重新从头播放导致 Clock 回跳，RViz 提示清空 TF 缓冲属于正常行为。10 Hz 轨迹没有插值，动作仍可能有离散感。

当前工具只回放点云、模型、TF、关节和 Clock，包内鱼眼图像保留但没有图像回放面板。RViz 不加载整个背景 mesh；背景由雷达点云呈现。

## 保护范围与启动

原采集项目 70 个文件及场景依赖 19 个文件的 SHA-256 对照全部一致，旧代码、旧输出和资产未改。原件 ZIP 及哈希在本项目 `backups/` 和 `source_provenance.json`，测试证据在 `reports/`。测试进程结束后只关闭本项目拥有的 viewer、RViz 和隔离 Xvfb。

在云端桌面终端运行：

```bash
cd /root/gpufree-data/semantic/scripts/261013Rviz2Viewer
bash launch_viewer.sh
```

云端浏览器打开 `http://127.0.0.1:8767`。先按下一组定格核对，RViz 的 LiDAR 列表独立勾选各传感器；再播放，默认 10 组/真实秒。退出用启动终端 Ctrl+C。SSH 启动时使用 `DISPLAY=:20 bash launch_viewer.sh`。完整使用与原生包切换命令见 `README.md`。

本地已保存完整源码、方案、报告和小体量证据；本轮 4.19 GB MCAP 保存在远端，没有下载到本地 output。
