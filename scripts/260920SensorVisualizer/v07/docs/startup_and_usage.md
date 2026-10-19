# v07 双卡启动和操作

以下使用已经迁移的双 L40 实例，不需要重启单卡源实例，也没有新增依赖安装。网页保持标准库后端，三维场景仍在 Isaac Sim 中。

## 1 启动交互窗口

在云端桌面的终端执行：

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v07
python3 run_capture.py --interactive --job config/interactive.json --gpu 0
```

GPU 0 负责视口与关节／整机控制。默认保持正式画质，试用异步交互渲染；运动时间推进不高于 0.1x。首次场景初始化等待完成后再操作。已有 Isaac GUI 也可以打开对应场景后在 Script Editor 运行 `run_in_isaac.py`，但这种方式不能补设 GUI 进程启动前的 CPU／设备配置，因此推荐独立命令行入口。

## 2 启动网页

另开云端终端：

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v07
python3 run_web.py --port 17875
```

在云端浏览器打开 `http://127.0.0.1:17875`。服务仅监听 loopback。若从本地访问，用 SSH 隧道转发该端口；不用开放新的公网网页服务。

## 3 操作与记录

1. 确认控制器已就绪，点击 Play Simulation。使用关节 Direct／Target／Periodic、整机 XYZ／Yaw／Pitch／Roll 和传感器安装位姿面板。
2. 开启键控；网页输入框获得焦点时只编辑参数。键盘映射沿用原版，松键和窗口失焦停止键控输入。
3. 仅记录运动时，Start Trajectory → 操作 → End Trajectory，等到 applied 回执再导出 ZIP 或进行离线采集。
4. 可先点击 Prepare Capture Service，让 GPU 1 完成场景与传感器预热。首次直接 Start Recording 也会排队等待服务加载。
5. 选择离线轨迹、live_latest 或 live_complete，填写最多组数、采样率和 ROS 预览开关，再 Start Recording。GPU 留空默认使用 GPU 1，填写 UUID 可明确指定物理卡。
6. Pause Capture 在完整组边界停下；Resume 继续；Stop + Drain 等待当前组和记录管线排空。等到任务结束且服务回到 idle，可以直接开始下一轮。

`live_latest` 优先最新状态，明确记录跳过的采样网格。`live_complete` 保存完整轨迹网格，采集可能落后于操作。离线不受 0.1x 限速。

关节键控使用当前配置的上下限，默认初始角 ±15°；若 Direct 把角度放在区间外，按键只允许以设定速度朝区间内移动，不会跳变。Direct／Target／Periodic 的有效硬边界同时受资产限制和 PhysX Revolute 原生目标范围约束。超界命令或轨迹会明确报错，不把角度偷偷取模。

## 4 常驻服务和退出

结束一轮采集后，GPU 1 服务保留场景与 RenderProduct，空闲时关闭传感器更新。服务占有的内存和显存不等于仍在扫描。Close Idle Capture Service 完整释放服务；需要时再次 Prepare。

Stop / Restore 复位控制状态后仍可 Play。Exit Controller 释放交互场景，之后 Reinitialize Controller → Play。网页与控制器保留熟悉的分类和按钮。

网页重启不会自动终止采集；读取 tasks 和持久提交恢复状态。若 worker 意外退出且遗留 pending task，先看 `runtime/capture_service.log`，确认进程已退出，再在异常任务恢复中 Recover Pending Task。没有确认退出的活进程不会被此按钮强行结束。

## 5 文件、配置与回退

- 源码：本地与远端同名 `260920SensorVisualizer/v07`。
- 正常产出：`/root/gpufree-data/semantic/output/sensor_visualizer/v07/`。
- 日志说明：[logging_contract.md](logging_contract.md)。
- `config/capture_policy.json` 设置采集资源策略；`runtime` 配置设备、线程预算与异步交互开关。
- 关闭本项目拥有的 v07 服务和窗口后，可按 v06 原来的命令运行。v06 及资产原文件保持原样，并保留源码备份与哈希清单。

Fabric 变换、池化 CUDA 异步回读和双卡离线分片尚不作为默认启用功能。先以实际诊断和数据校验决定是否接入，不能把硬件能力当作已经实现的加速。
