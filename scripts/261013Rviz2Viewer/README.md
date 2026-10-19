# 独立 RViz2 回放工具与 Scene18 自制链路 300 组采集

本地源码：`D:\learning\IntelligentDepartment\CodesSet\Self\260707IsaacSIm\scripts\261013Rviz2Viewer`。

远端源码：`/root/gpufree-data/semantic/scripts/261013Rviz2Viewer`。

运行位置是已安装 ROS 2 Jazzy / RViz2 的单卡云实例。回放不需要启动 Isaac Sim，不导入旧 Sensor Visualizer 模块。`capture_runtime` 只用于重新采集，保存了旧链路的隔离源码副本及原件备份。

## 快速启动

在云端桌面的终端执行：

```bash
cd /root/gpufree-data/semantic/scripts/261013Rviz2Viewer
bash launch_viewer.sh
```

启动后在**云端浏览器**打开 `http://127.0.0.1:8767`。网页控制回放，RViz2 显示挖掘机和点云。默认暂停在第 0 组，默认勾选一路雷达，避免初次显示 13 路重叠点云影响判断。

若从 SSH 终端启动，当前实例桌面显示号是 `:20`：

```bash
cd /root/gpufree-data/semantic/scripts/261013Rviz2Viewer
DISPLAY=:20 bash launch_viewer.sh
```

若需要在本地浏览器控制，可从本地终端建立 SSH 转发（认证使用已配置密钥或交互式凭据，不把密码写进命令）：

```powershell
ssh -p 30729 -L 8767:127.0.0.1:8767 root@120.209.70.195
```

然后打开本地 `http://127.0.0.1:8767`；三维窗口仍在云端桌面。

## 操作顺序

1. RViz 的 `LiDAR` 分组中勾选要看的雷达；`Excavator Mesh` 是车体，`Sensor Frames` 是坐标轴。
2. 网页点击“下一组”，整机、各部件、传感器 TF 和点云按组推进。
3. 先在“按消息时间归组同步播放”模式下定格查看贴合关系，再试 ±1 组模型偏移。偏移只改变诊断模型的显示姿态，不改点云和 TF。
4. 点击播放，默认 10 组/真实秒。可暂停、上一组、跳转组号、修改透明度和速度。
5. 切换“按原始录制时间回放”，观察录制时间差的影响；模式切换会暂停。原始模式不支持模型偏移。
6. 在终端按 `Ctrl+C` 结束工具，它会关闭由自己启动的 RViz，并保存回放日志。

界面快捷键：空格播放/暂停，左右方向键单步。输入框拥有焦点时快捷键不接管输入。

`Decay Time=0` 避免历史点云累积；固定坐标系是 `world`，RViz 使用 `use_sim_time=true`，工具使用独立 `ROS_DOMAIN_ID=43`。不要同时在同一 domain 发布另一套 `/clock` 或 TF。

一组包含多个 ROS 话题，它们不是原子显示事务。工具先发布 TF，再发送点云；严格贴合判断以暂停定格后的画面为准。10 Hz 本身有离散跳动感，默认不做视觉插值。

## 切换到先前的原生包

```bash
source /opt/ros/jazzy/setup.bash
cd /root/gpufree-data/semantic/scripts/261013Rviz2Viewer
DISPLAY=:20 /usr/bin/python3 run_viewer.py \
  --capture /root/gpufree-data/semantic/output/native_scene18_capture_005/capture_20261012_111643/delivery_300 \
  --assets /root/gpufree-data/semantic/output/261013Rviz2Viewer/20261013_142507_300/capture/viewer_assets \
  --cache /root/gpufree-data/semantic/output/261013Rviz2Viewer/native_reference_cache/index.sqlite \
  --rviz
```

两个包的初始化时间偏移不同，比较时对齐逻辑组号；不要直接把它们的绝对消息时间当成相同姿态。同步模式的原生模型依据记录根姿态、关节和真实 USD 关节锚点重建；新自制包直接使用记录的刚体位姿。

## 数据及日志

正式采集外层目录：`/root/gpufree-data/semantic/output/261013Rviz2Viewer/20261013_142507_300`。具体 session 见项目 `reports/latest_capture.json` 对应目录下 `capture/result.json` 的 `capture.session`。

- `capture/captures/<session>/bag_unified/`：标准 ROS 2 MCAP，13 路点云、4 路 PNG 压缩鱼眼图像、相机参数/位姿、TF、根位姿、关节、Clock、运行元数据和逐组索引。
- `capture/viewer_assets/`：五部件二进制 STL 与 manifest，mesh 原点/缩放/对齐已烘焙到实际刚体坐标系；RViz 使用诊断颜色，未复制 USD 材质。
- `capture/body_poses.jsonl`：每组五部件的实际 USD 世界变换。
- `capture/viewer_model_validation.json`：关节锚点重建与实际部件变换的误差。
- `capture/system_resources.jsonl`、`capture/engine.log`、`capture/captures/<session>/diagnostics/`：原采集链路资源、引擎及细分阶段日志。
- `capture/captures/<session>/viewer_cache/`：仅用于回放的 SQLite 缓存与时间审计；默认不索引图像，节省读盘、内存和通信成本。MCAP 原件不变。
- `capture/captures/<session>/viewer_logs/<run>/`：`playback_events.jsonl` 记录计划/实际发送、单调时间、UTC 时间、话题、原始两种时间戳、点云数据哈希及本机 ROS 接收回调；`rviz.log` 保存 RViz 状态；`summary.json` 保存间隔统计。

首次启动会生成缓存，随后可以直接跳转。缓存用文件路径/大小/mtime 检查复用条件；各索引消息另有 CDR SHA-256。此缓存复用检查不是整包可信认证。

## 文件模块

| 文件 | 用途 |
|---|---|
| `run_viewer.py` / `launch_viewer.sh` | 回放入口及 ROS 环境初始化 |
| `rviz_viewer/index.py` | 官方 rosbag2 读取、消息时间归组、SQLite 缓存和时间审计 |
| `rviz_viewer/model.py` | 列向量变换、四元数与 USD 关节锚点运动学 |
| `rviz_viewer/player.py` | 整组回放、原始时间回放、预读、消息发布、单步/跳转/日志 |
| `rviz_viewer/web.py` / `web/index.html` | 本机网页控制，不依赖 FastAPI 或外部 CDN |
| `make_rviz_config.py` | 生成逐雷达勾选的 RViz 配置 |
| `capture_observer.py` | 在自制链路接受数据后读取实际部件位姿，并导出 mesh |
| `kit_capture_entry.py` / `prepare_capture.py` | 隔离采集入口，复用上轮准确轨迹和安装位姿 |
| `capture_runtime/` | 原自制链路副本；正式旧项目不修改 |
| `verify_model.py` / `tests/` | 坐标、运动学与真实 ROS 回放验证 |
| `operations/` | 本次经过审阅的启动、状态和测试操作；不应批量执行 |
| `backups/` / `source_provenance.json` | 原件备份和来源哈希 |

## 重录及限制

可通过 `prepare_capture.py` 创建新目录，再从 `capture_runtime` 使用 `lab.runner` 启动。操作脚本拒绝覆盖旧输出，拒绝已有 Isaac 渲染进程时并发采集。此次启用 `persistent_gated + keepalive`，沿用 16 预热 + 2 正式子帧及现有质量设置；没有新增或更新依赖。

自制包的所有同组消息时间统一，不能单凭这一点证明点云中的全部几何均已更新。本工具提供错帧对照和证据日志；最终几何延迟结论仍需要逐组图像/点云与 mesh 表面的定量评估。

本轮实测结果及证据见 [ExecutionReport.md](docs/ExecutionReport.md)。正式包已保存远端，未下载 4.19 GB MCAP 到本地。本地保存完整源码、实施方案、报告及小体量测试证据。当前回放工具显示 mesh、TF 和点云，鱼眼图像保留在包中，但不在本工具播放。
