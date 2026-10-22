# Isaac 原生采集基线

这是独立实验项目，用于在同一 USDA 下检验原生传感器生成、官方 ROS 发布和标准 MCAP 录制的成本。没有引用 v06/single06_lab 的 Python 模块，不替代可交互的 Sensor Visualizer 面板。

[完整实施方案](docs/implementation_plan.md) · [实测结果与限制](docs/20261011_execution_report.md)

## 云端启动

先正常关闭已运行的 Isaac GUI。脚本遇到现有 Isaac 进程会拒绝启动，不会帮你终止它。

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_baseline
python3 run.py --mode record --frames 60 --warmup 24
```

命令自行启动一个无窗口 Isaac 和标准 `ros2 bag record -s mcap`，完成指定引擎帧数后正常关闭，随后解码检查 MCAP。不要在 Script Editor 中执行 `run.py`。无需新增依赖、手工 source ROS 或启动 RViz。

输出默认位于 `/root/gpufree-data/semantic/output/native_capture_baseline/record_<UTC时间>/`。重复执行会新建目录。Ctrl+C 请求停止，等待当前引擎更新完成和录制器收尾，不要直接强杀录制器。

## 分层实验

```bash
# A：原生渲染与 GPU 侧传感器后处理，不发布、不读取数组
python3 run.py --mode render --frames 60
# B：官方发布，标准 rosbag2 保持订阅但暂停记录
python3 run.py --mode publish --frames 60
# C：官方发布及标准 MCAP 保存
python3 run.py --mode record --frames 60
# 输入已存在的参考轨迹，仅使用官方 Articulation 姿态/关节接口
python3 run.py --mode record --motion moving --frames 60
# 已安装 Nsight Systems 的原生时间线，不和普通运行混算性能
python3 run.py --mode record --trace --frames 24
```

`--multi-tick` 是额外的原生节拍实验，会改变原先关闭的 multi-tick 设置；不用于默认同配置对照。`--schedule frozen` 是零时间推进/18子帧的兼容性实验，能否产生完整新消息必须查看验证结果，不默认承诺其等价性。

本轮发现 Multi-tick 的相机重复时间戳，以及 frozen 没有新的可辨识传感器消息；这两个选项暂不用于正式采集。`tools/*_remote.py` 等启动/核查助手绑定本轮实验路径，属于调查证据，不是日常启动入口。通用启动用 `run.py`，通用采集后分析用 `python3 tools/analyze_results.py <输出目录>`。

## 数据链路

USD → Timeline/Kit 原生更新 → 持续存在的 Render Product → 官方 Helper/SDG Writer → DDS → rosbag2 → MCAP。

`capture_on_play=True` 保证官方 Writer 在播放时执行。传感器不会逐帧销毁、重新创建或切换启停。脚本没有取出点云、打包图像、传递共享内存或自定义录制 Worker。

## 文件与模块

| 文件 | 职责 |
|---|---|
| `config/baseline.json` | 锁定场景、渲染参数、数量、时间步与输出目录 |
| `run.py` | 启动已有 Kit/ROS 工具、资源观测、只管理自身进程、录制收尾 |
| `kit_entry.py` | 一次建立原生产品/ROS图、启动播放、计时、可选原生运动输入 |
| `tools/validate_bag.py` | 采集后用 ROS 标准解码，检查话题、消息、标定和 TF |
| `tools/build_deploy.py` | 限定新项目目录、按哈希部署并备份其自身旧文件 |
| `docs/implementation_plan.md` | 用户批准的完整实验方案，云端与本地保存 |
| `reports/` | 环境核查、审计及实验汇总，不能用配置值冒充测量结果 |

## 每次输出

- `bag/*.mcap`、`bag/metadata.yaml`：标准 ROS 2 bag。
- `spec.json`、`sensor_manifest.json`：本次配置、传感器、官方图和依赖 USD 哈希。
- `engine_events.jsonl`、`frames.jsonl`：主机时间与仿真时间、初始化/预热/测量/收尾边界；每次 await 的主线程 CPU 时间包含事件循环上其他任务，不能视为纯函数自身 CPU 成本。
- `resources.jsonl`：1 Hz 全卡 nvidia-smi 数据、Kit/录制器及各线程 `/proc` CPU 计数、RSS；低频采样无法区分短 GPU 脉冲。
- `engine.log`、`recorder.log`、`validation.log`：未经筛掉的引擎、录制和检查日志。
- `engine_result.json`、`result.json`、`validation.json`：测量、整个进程生命周期和数据检查结果；失败不伪装成功。
- `final_poses.json`、`expected_final_transforms.json`：采集后从 USD 读取的参考姿态，用于验证原生 TF。
- `*_first.png`：如果已有 Pillow 可用，解码第一张原生图像；不会为了导出安装依赖。
- `native.nsys-rep`、`native.sqlite`：仅 `--trace` 实验产生，保留原生 profiler 原始证据。

## 对照边界

13 路 LiDAR、4 路 1920×1080 鱼眼、同场景与渲染质量。原生链路保存无损 `sensor_msgs/Image`，旧项目保存 PNG `CompressedImage`，字节量和编码成本不同。原生连续更新也不同于旧项目每组冻结的 16+2 子帧；不能用引擎帧率直接宣称“同质量整组”加速倍数。

录制包含初始化播放和预热段，正式测量窗口由 `engine_result.json` 的仿真时间范围界定。原生发布滞后一帧，连续模式在测量后保留最后姿态再更新两帧，使测量窗口的最后消息发布完成；这两帧单独记录、计入总过程时间，不计入测量帧率。`validation.json` 单列测量窗口的话题数量。各原生话题独立发布，没有人为制造同步组；同 stamp 覆盖率、丢帧/重复、原生节拍都由采集后统计决定。

原包的自定义组索引、PoseStamped 和 horizontal 帧暂未复制。TF 相连、点坐标有限并不能证明 3DGS 与点云物理对齐。实验采用原先关闭 Motion BVH 的设置，运动畸变相关警告与影响需要单列。
