# NC-003 原生连续调度、逐张高采样PT

独立实验项目，保留NC-002和Sensor Visualizer旧版本。详见 `docs/NC-003_implementation_plan.md`。运行器使用云端Linux现有Isaac与ROS环境，本地Windows仅保存源码和证据。

**当前测试状态：连续PT高采样渲染通过；严格MCAP组校验失败。** 首轮4组生成16张原生最终图，但ROS Helper只发布后三组，且sensor header与物理仿真时钟偏移。不能把此版本作为已验证同步的数据交付链路。128SPP/2组的Preview初始化控制仍复现问题。详见 `docs/NC-003_execution_report.md`。

## 运行

先正常关闭正在运行的Isaac GUI，启动器发现其他Kit会退出，不终止其他项目。

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_continuous_pt_003
python3 run.py --frames 4
```

默认每张请求1024SPP、每迭代32SPP、8反弹；四组对应每路鱼眼四张图像。当前测试大臂0/15/-15/0度，其他关节为零，整机保持原始安装位置。输入源、传感器资产和USD磁盘文件不改动。

`config/baseline.json` 的 `pt_total_spp`、`pt_spp` 指定每张预算；total必须是spp的正整数倍。`measure_frames` 指逻辑采集组，不是PT子帧数量；默认4组对应16张RGB。

## 调度和数据

一次 `rep.orchestrator.run_async(num_frames=N)` 连续场景，原生引擎完成每张32个PT子帧后恢复时间，再进入下一张。子帧期间引擎暂缓仿真推进，避免一张累积图混入不同姿态；连续不代表真实时间实时运行。

每张开始重置累积，同时启用时间变化重置，关闭adaptive和motion blur。ROS Helper、原生发布节点和标准MCAP录包链路保留，不改接图、不改写header。官方BasicWriter另外异步写最终PNG与CameraParams作参考证据，不是MCAP图像编码路径。

输出在 `/root/gpufree-data/semantic/output/native_capture_continuous_pt_003/`：`bag/`标准MCAP，`native_basic_images/`参考图，`groups.jsonl`完整组及字节/位姿证据，`native_updates.jsonl`逐引擎更新，`native_cycles.json`原生帧/子帧，`resources.jsonl` GPU/CPU/RSS采样，原始warning与校验结果。

只有 `result.json` 的state为completed、`group_validation.json` 的ok为true，且每组 `continuous_pt_budget_validation` 通过，才算有效。要求每张MCAP图像/current观察/BasicWriter参考字节一致，当前点云字节、TF、关节、渲染位姿一致；要求当前原生时间戳及组间不同。

SPP证据包括生效预算、每张累积重置、原生子帧完成数，不等同于直接读到硬件逐像素射线计数。测试结果另写 `docs/NC-003_execution_report.md`。
