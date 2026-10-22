# NC-003 原生连续 Path Tracing 测试报告

日期：2026-10-12。对应用户要求：原生链路连续采集、Path Tracing、每张指定高采样画质并实测。代码独立保存于 `native_capture_continuous_pt_003`，本地与云端均部署；此前代码保留。

## 1. 结论与验收状态

**连续PT调度、高采样预算完成和最终图像检查通过；完整MCAP同步组验收失败。** 不把渲染成功等同于同步采集成功，也不把此次MCAP交付为已验证的数据集。

首轮四个原生逻辑帧，每帧四路1920×1080鱼眼，产生16张官方BasicWriter最终PNG。四帧均记录独立累积重置、PathTracing/1024SPP/每迭代32SPP、adaptive关闭，以及capture事件处32个原生子帧完成。16张PNG全部与原生RGB最终观察数组逐字节一致。

但每路ROS图像、CameraInfo和点云均只有3条，缺少第0组。第1/2/3组传感器消息字节与对应最终RGB/XYZ观察完全一致，但消息header不等于同组物理仿真时间；因此严格组校验失败，`result.json.state=failed`。这不是图像未生成或录包进程崩溃。

## 2. 环境、参数与执行方式

| 项目 | 本轮设定 |
|---|---|
| 环境 | 已安装Isaac Sim 6.0.1 rc7、ROS Jazzy、单张NVIDIA L40 |
| USD | `/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_16_terrain_fisheye.usda` |
| 根USD SHA-256 | `ab2a2ef736030adba3420450f916420e705952a04fec163c05b545655fc7f0ae` |
| 传感器 | 4路1920×1080鱼眼、13路Instant LiDAR |
| 渲染 | `PathTracing`，每张1024SPP，每迭代32SPP，8次反弹 |
| 图像处理 | OptiX空间降噪开启；时间降噪、adaptive及motion blur关闭 |
| 调度 | 一次 `rep.orchestrator.run_async(num_frames=4, start_timeline=False)`，普通Kit更新驱动官方调度 |
| 每帧质量 | 帧开始调用 `UsdContext.reset_renderer_accumulation()`；时间变化重置也开启；按SDK完成计数验收32子帧 |
| 姿态变化测试 | 大臂0/+15/-15/0度，其余受控关节为0，cab–track保持初始值；整机保持首个轨迹状态，无接触动力学 |
| 数据保存 | 官方ROS Helpers及发布节点，标准 `ros2 bag record -s mcap`；BasicWriter额外存最终RGB/CameraParams作独立参考 |

连续的含义是单次原生scenario持续执行。SDK在一张图的PT子帧期间暂缓timeline自动推进，完成后恢复，进入下一张。没有调用原有每组六次物理更新、warm/formal两次step_async调度，也没有替换传感器数组、修改header或串入旧版本运行时代码。

私有SDK帧/子帧计数与BasicWriter计数仅作只读诊断；实际SPP硬件计数并未直接读取。预算、累积重置、SDK完成及最终图像证据支持“每张按1024SPP请求完成”，不声称直接测得每个像素恰好执行1024条射线。BasicWriter PNG的额外导出是此次诊断开销的一部分。

## 3. 高采样实测耗时与资源

主测试输出目录：

```text
/root/gpufree-data/semantic/output/native_capture_continuous_pt_003/continuous_pt1024_20261012_060128/
```

| 组 | 物理仿真时间 / s | 帧开始至原生capture事件 / s | 帧开始至最终载荷观察完成 / s |
|---|---:|---:|---:|
| 0 | 0.300000000 | 75.147 | 80.677 |
| 1 | 0.316666667 | 75.855 | 80.948 |
| 2 | 0.333333333 | 76.181 | 81.229 |
| 3 | 0.350000000 | 73.767 | 78.774 |

- 四组原生scenario含初始化/完成等待：328.315秒；帧开始至最终观察平均80.407秒。每组同时对应四张图，不能把80秒理解为每张相机单独串行耗时。
- 监督进程从启动引擎、录包到引擎退出和录包收尾：401.279秒；不包含后处理校验耗时。
- 正式measurement窗口的1Hz采样：GPU利用率均值96.92%，P95=100%；显存约9.6GiB（平均9831MiB、峰值9933MiB）；平均功耗292.07W。
- 同窗口Kit进程CPU平均约1.25个逻辑核当量；不是整机CPU占用1.25%，也不是纯主线程计算耗时。
- SDK触发和最终数据完成之间相差约4.89–5.42秒。原生允许下一帧工作与上一帧观察/写盘交错，逐组区间有重叠，不能直接相加作为总时长。

这里GPU高利用率对应长时间PT渲染，未出现此前大量低利用率等待的整体形态。没有对本轮运行Nsight，不能从NVML利用率推导SM occupancy、Tensor Core或RT Core单元利用率；CPU的thread_time也不能细分驱动忙等与实际业务计算。

此前NC-002的PT1024约91.6秒/组包含不同的组六次运动更新及双step调度。本轮没有这些准备阶段，因此两者不构成严格单变量速度比较；此次长耗时仍主要落在高SPP累积本身。

## 4. MCAP失败的直接证据

| 最终载荷所属组 | 对应物理仿真时间 / ns | MCAP sensor header / ns | 图像/XYZ字节与该组匹配 |
|---|---:|---:|---|
| 0 | 300000000 | 无对应消息 | 无法匹配；PNG已存在 |
| 1 | 316666667 | 332812499 | 是，4路RGB与13路XYZ全匹配 |
| 2 | 333333333 | 349479166 | 是，4路RGB与13路XYZ全匹配 |
| 3 | 350000000 | 366145833 | 是，4路RGB与13路XYZ全匹配 |

偏移约16.145833毫秒，接近 `1/60 × (1-1/32)`。SDK的trigger/capture参考时间是Fabric rational reference time，数值约3.13/4.17等，并不是物理仿真秒。原生 `IsaacReadSimulationTime` annotator通过render-product Fabric reference映射时间；原生 `IsaacSimulationGate` 又依赖物理更新，WriterSyncGate依赖Fabric完成，两个时域需要区分。

**已证实：** 原生输出有效；ROS发布首组缺失；同一载荷存在确定的时间偏差；现象随PT子帧设置改变。**尚未证实：** 是哪一个C++时间转换或门控节点首次丢失/插值偏移，及完整的根因。不能仅凭偏移公式断定引擎某一行源码错误。没有采用事后统一平移header、增加匹配容差或伪造TF/关节时间来让检查通过。

`/clock`、`/joint_states`、`/tf`继续在物理时间发布，冻结期间出现重复时间戳；因此“话题都有数据”的通用检查不足以证明同组同步。该次通用 `validation.json.ok=true`，严格 `group_validation.json.ok=false`，最终总状态正确保持failed。另有2812条PoseTree warning；数值TF检查没有因此失败，但warning具体原因本次未深入验证。

首轮 `groups.jsonl.native_time_after_s`曾直接复用capture时间，不能作为真实读取后时间或冻结证明；本轮冻结判断来自逐update及SDK逻辑，诊断版已把该字段改为实际update后的SimulationManager时间。首轮原始证据不覆盖改写，每次源码哈希保存在该次 `source_manifest.json`。

## 5. 补充控制实验

控制目录：

```text
/root/gpufree-data/semantic/output/native_capture_continuous_pt_003/diagnostic_preview_pt128_20261012_062027/
```

采用2组、128SPP/32SPP，即4个PT子帧。增加原生 `preview_async()` 初始化，并直接观察官方 `IsaacReadSimulationTime` annotator。此实验仅定位同步，不作为1024SPP高采样验收。

- 两组8张BasicWriter最终图与观察字节一致，4子帧预算完成。
- ROS每路仍只1条，首组仍缺失。
- 传感器时间与物理时间分别为0.3625 vs 0.35、0.379166667 vs 0.366666667，偏移12.5毫秒，接近 `1/60 × (1-1/4)`。
- 说明简单补一次Preview初始化不能解决；该控制实验不能证明单一根因。当前默认配置不启用额外Preview。

本轮没有再追加会改变原生基准性质的门控改接或自定义发布调度。后续要把连续PT用于严格同步MCAP，应独立验证原生时间annotator、SimulationGate与WriterSyncGate的对应关系，再决定采用兼容修正还是保留已验证的显式step采集链路。

## 6. 产物、运行与范围

- 本地/云端项目：`scripts/260920SensorVisualizer/native_capture_continuous_pt_003`；云端父目录为 `/root/gpufree-data/semantic/scripts/260920SensorVisualizer`。
- `native_basic_images/`：4相机 × 4最终PNG及CameraParams；`bag/`：标准MCAP，仍按失败数据保留。
- `continuous_analysis.json`：只报告渲染预算/最终图像成功；明确不覆盖严格MCAP失败。
- `groups.jsonl`、`native_updates.jsonl`、`native_cycles.json`：完成事件、时间域、原生子帧、当前载荷哈希与姿态；`resources.jsonl`、`engine.log`、`recorder.log`：资源和原始日志。
- 本地 `reports/runs/`已保存原始日志、参考图及传输哈希；MCAP留在上述云端bag目录，本轮没有把MCAP下载到本地output。
- 每次启动、部署、读取、传输有本地Skill工具审计；部署前旧版本源码备份，云端323份旧文件每次部署均校验未改变。本地NC-002原有40份文件保持哈希。未下载/更新依赖或工具，未修改磁盘USD、系统或桌面配置。

在云端先正常关闭其他Isaac进程，然后：

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_continuous_pt_003
python3 run.py --frames 4
```

按需修改本新项目 `config/baseline.json` 的 `pt_total_spp` 与 `pt_spp`；要求total为spp的正整数倍。默认1024/32。`measure_frames`为逻辑组数，不是子帧数。当前版本是问题复现实验，必须查看严格校验结果；不得因为PNG生成就视为MCAP同步成功。
