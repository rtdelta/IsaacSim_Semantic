# MyAiry 组合场景与试采集

已从 `combine_scene_11_origin03.usda` 生成：

```text
/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_12_myairy.usda
```

七个 MyOS0 安装实例替换为 `MyAiry_back`、`MyAiry_backleft`、`MyAiry_backright`、`MyAiry_front`、`MyAiry_left`、`MyAiry_right`、`MyAiry_up`。父子层级和原有位置、旋转、缩放逐项保留；六个 MyNZ3 保留。原始 combine 场景没有改变。

新根层同步更新了图节点、cameraPrim 关系、Render Product 名称及相关路径。旧 os0_mesh 的覆盖设置已清理。MyAiry 不包含外壳 Mesh，且原场景的 MyOS0 外壳原本也是停用状态。位姿检查确认每个 MyAiry 发射节点与安装节点重合，`rangeOffsetM=0`。

## 采集位置

试采集任务目录：

```text
/root/gpufree-data/semantic/output/lidar_visualizer/myairy_trial/20260919_192951/
```

实际录制目录：

```text
/root/gpufree-data/semantic/output/lidar_visualizer/myairy_trial/20260919_192951/captures/20260919_193054_494141_5f3579/
```

实际录制目录内：

- `bag/`：MCAP 原始数据及 rosbag2 `metadata.yaml`。
- `session.json`：实际话题、完整传感器参数、安装位姿、TF 定义和运行配置。
- `qos_overrides.yaml`、`recorder.log`：录制 QoS 配置和日志。
- `inspection/summary.json`：从 MCAP 反序列化得到的统计和校验结果。
- `inspection/frames.csv`：全部点云的时间戳、点数、坐标系和 TF 可用性。
- `inspection/<雷达名>/local.pcd`：该雷达第一帧非空点云，保留传感器局部坐标。
- `inspection/<雷达名>/world.pcd`：同一帧按录制 TF 转到世界坐标。
- `inspection/<雷达名>/frame.json`：样本时间戳及具体变换矩阵。
- `inspection/pointcloud_overview.png`：两类雷达在 XY/XZ/YZ 平面的点云预览。

图中使用世界坐标轴，显示原点平移至挖掘机 swing 参考点；只显示距此原点各轴 ±12 m 范围内的点，并做抽稀。PCD 文件保留完整点集与真实坐标。预览用于查看覆盖和结构，不是几何真值误差评估。

本地 `reports/stage12/` 保存检查报告、日志和 26 个 PCD 样本。原始 MCAP 保存在云端，没有复制到本地。`scenes/` 下保存新根层快照；其相对资产引用依赖原有 IsaacSim_Asset 目录树，单独复制快照不构成完整场景包。

## 实际结果

| 项目 | 结果 |
| --- | --- |
| 雷达 | 7 路 MyAiry + 6 路 MyNZ3 |
| 定时采集区间 | 3.000 秒仿真时间 |
| 定时区间真实耗时 | 30.189 秒 |
| 实测仿真/真实倍率 | 0.09937 |
| 点云 | 每路 31 帧，共 403 帧 |
| 点云时间间隔 | 每路全部为 0.1 秒，即 10 Hz |
| 点数总计 | 16,405,066 |
| MCAP 字节数 | 197,562,583，约 198 MB / 188.4 MiB |
| 点云字段 | x、y、z |
| NaN/Inf、空帧、TF 查询失败 | 均为 0 |
| 关节角和车体位姿变化 | 0 |

31 帧包含区间端点及录制启动/结束边界的消息；不能简单把 31/3 当作发布频率。校验使用 `(帧数-1)/(末帧时间戳-首帧时间戳)` 及逐帧时间间隔。包内 Clock 跨度约 3.0167 秒，定时采集后的异步关闭还有少量时钟消息。

TF 结构为 `world → swing_horizontal_coordinate → swing_coordinate → 各雷达`。全部点云的时间戳都可查询到世界变换，与运行时 USD 位姿的矩阵差小于 2×10^-4；本轮没有使用 1 ns 的边界修正。关节消息为 `swing/boom/arm/bucket`，保持启动角约 `[0,38,-106,-5.87416]` 度。

在预览中可见地面、围栏、挖掘机大臂和小臂结构。MyAiry 的单帧有效点数随安装位置约为 3.3 万至 7.6 万；85,632 是采样数，不是每帧必然返回的点数。点云图不能单独证明所有遮挡都符合真实设备；本轮没有做实机强度或全场景遮挡真值标定。沿用资产 README 中说明的合成功率归一化。

Kit 日志没有 `[Error]` 或 Python Traceback，但仍有 47 条 Warning，包括 Motion BVH 关闭、SDK 资源释放/性能、音频设备以及被静默的 USD 诊断提示。录制正常退出、文件可完整读取。测试结束后自己的 Kit 和录制进程均已退出，GPU 回落至约 668 MiB、3% 使用率。

## 运行方式

普通交互使用：打开新的 `combine_scene_12_myairy.usda`，在 Script Editor 运行原 LidarVisualizer 的 `run_in_isaac.py`，再 Play。它会自动发现新的 `MyAiry_*` 名称并生成 ROS/RViz 配置。

本次自动试采集使用独立 ROS Domain **173**；生产项目默认 Domain 0 未修改，旧录制进程未干预。任务目录 `runtime/` 保存本轮实际传感器列表及 RViz 配置。

下面的命令使用已经创建好的新场景再次采集，须指定新的、尚不存在的 job 目录，并确保使用的独立 ROS Domain 未被其他任务占用：

```bash
cd /root/gpufree-data/semantic/scripts/260919MyAiryLidar
python3 tools/launch_capture.py \
  --reuse-stage \
  --job-dir /root/gpufree-data/semantic/output/lidar_visualizer/myairy_trial/another_trial \
  --domain 173 --seconds 3
```

从原场景首次生成时不加 `--reuse-stage`，并通过 `--stage` 指定尚不存在的同目录新文件。转换脚本拒绝覆盖已有场景。`launch_capture.py` 启动独立的无窗口 Kit 进程；完成后退出。结果在 `capture_result.json`，应检查 `passed`，不能仅依据 Kit 退出码判断。

录制结束后分析：

```bash
source /opt/ros/jazzy/setup.bash
/usr/bin/python3 tools/analyze_capture.py \
  /root/gpufree-data/semantic/output/lidar_visualizer/myairy_trial/another_trial
```

分析入口会新建 `inspection/`，拒绝覆盖已有导出。实现文件为 `tools/prepare_stage.py`、`tools/launch_capture.py`、`tools/capture_scene.py`、`tools/analyze_capture.py`；源码已同时保存本地与云端。
