# Isaac Sim LiDAR Data Capture

这组脚本用于从 Isaac Sim 的 ROS 2 Bridge 中采集 RTX LiDAR 点云。默认话题是 `/point_cloud`，默认导出目录是：

```text
D:\2510wyb\IssacSim\isaacProject\lidar_exports
```

## 前置条件

1. 启动 Isaac Sim，并启用 ROS 2 Bridge、RTX LiDAR、Action Graph 相关扩展。
2. 打开包含 LiDAR 和 ROS graph 的工程，例如：

```text
D:\2510wyb\IssacSim\isaacProject\1.usda
```

3. 确认 Stage 中有类似下面的内容：

```text
/World/body/Example_Rotary
/Graph/ROS_LidarRTX
```

4. 在 Isaac Sim 中点击 `Play`。

## 检查 LiDAR 话题

```powershell
powershell -ExecutionPolicy Bypass -File D:\2510wyb\IssacSim\scripts\lidar_capture\check_lidar_topic.ps1
```

如果想同时读取一帧 header：

```powershell
powershell -ExecutionPolicy Bypass -File D:\2510wyb\IssacSim\scripts\lidar_capture\check_lidar_topic.ps1 -ReadOneHeader
```

正常情况下应该看到：

```text
/point_cloud [sensor_msgs/msg/PointCloud2]
```

## 采集一帧点云

```powershell
powershell -ExecutionPolicy Bypass -File D:\2510wyb\IssacSim\scripts\lidar_capture\capture_lidar_once.ps1
```

输出文件包括：

```text
point_cloud_YYYYMMDD_HHMMSS_FULL.ply
point_cloud_YYYYMMDD_HHMMSS_first5000.csv
point_cloud_YYYYMMDD_HHMMSS_summary.json
```

`PLY` 适合用 CloudCompare、MeshLab、Blender 查看；`CSV` 适合快速检查坐标；`summary.json` 记录话题、帧名、点数、字段和文件路径。

## 常用参数

指定话题：

```powershell
powershell -ExecutionPolicy Bypass -File D:\2510wyb\IssacSim\scripts\lidar_capture\capture_lidar_once.ps1 -Topic /point_cloud
```

指定输出目录：

```powershell
powershell -ExecutionPolicy Bypass -File D:\2510wyb\IssacSim\scripts\lidar_capture\capture_lidar_once.ps1 -OutputDir D:\2510wyb\IssacSim\isaacProject\lidar_exports
```

只导出最多 100000 个点到 PLY：

```powershell
powershell -ExecutionPolicy Bypass -File D:\2510wyb\IssacSim\scripts\lidar_capture\capture_lidar_once.ps1 -MaxPoints 100000
```

把 CSV 预览点数改成 10000：

```powershell
powershell -ExecutionPolicy Bypass -File D:\2510wyb\IssacSim\scripts\lidar_capture\capture_lidar_once.ps1 -CsvLimit 10000
```

## 连续录制 rosbag

如果需要保留一段连续的 ROS 2 原始数据，用：

```powershell
powershell -ExecutionPolicy Bypass -File D:\2510wyb\IssacSim\scripts\lidar_capture\record_lidar_bag.ps1
```

默认保存到：

```text
D:\2510wyb\IssacSim\isaacProject\lidar_bags\point_cloud_YYYYMMDD_HHMMSS
```

录制时按 `Ctrl+C` 停止。

## 文件说明

```text
setup_ros2_jazzy_env.ps1   配置 Pixi/ROS 2 Jazzy 环境变量
check_lidar_topic.ps1      查看 /point_cloud 是否存在，以及发布者信息
capture_lidar_once.ps1     PowerShell 包装脚本，一条命令完成单帧采集
capture_lidar_once.py      真正订阅 PointCloud2 并导出 PLY/CSV/JSON 的脚本
record_lidar_bag.ps1       连续录制 rosbag
README.md                  本说明文档
```

## 常见问题

如果没有 `/point_cloud`：

1. 确认 Isaac Sim 正在 `Play`。
2. 确认 Stage 里有 `/Graph/ROS_LidarRTX`。
3. 确认 graph 里的 topic name 是 `/point_cloud`。
4. 确认 Isaac Sim 是用 ROS 2 环境启动的，且 `ROS_DOMAIN_ID` 一致。

如果有 `/point_cloud` 但采集超时：

1. 在 Isaac Sim 里暂停再重新 `Play`。
2. 运行 `check_lidar_topic.ps1 -ReadOneHeader` 看能否读到 header。
3. 如果 QoS 不匹配，可以尝试：

```powershell
powershell -ExecutionPolicy Bypass -File D:\2510wyb\IssacSim\scripts\lidar_capture\capture_lidar_once.ps1 -BestEffort
```
