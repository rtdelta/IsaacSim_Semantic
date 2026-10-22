# NC-004 执行结果与分析

日期：2026-10-12。实验：`comparison_20261012_070140`。

环境来自本轮 engine.log：单卡 NVIDIA L40，驱动 580.126.09，Vulkan；Isaac Sim 6.0.1-rc.7，Ubuntu 24.04.4。引擎报告 CPU 为 Xeon Platinum 8358、容器 Core Usage Quota=14，内存 122880 MB；宿主机逻辑核数不等于容器可用核数。四路 1920×1080 鱼眼、13 路 Instant LiDAR，固定 combine_scene_16_terrain_fisheye.usda，视口更新关闭。本轮测量离线采集，不是操作面板响应延迟。

已完成 **24/24 次独立运行**：8 种配置 × 3 轮 × 6 个目标组。**21 次录包通过，3 次未通过**。从实际 MCAP 导出 **564 张 PNG**，其中 504 张有效、60 张诊断图片。目标总数为 576；缺失图片不补渲染、不伪造。

[完整统计报告](reports/results/comparison_20261012_070140/analysis/NC-004_report.md) · 图片浏览器（本地原始证据：`scripts/260920SensorVisualizer/capture_comparison_004/results/comparison_20261012_070140/analysis/gallery.html`） · 逐轮 CSV（本地原始证据：`scripts/260920SensorVisualizer/capture_comparison_004/results/comparison_20261012_070140/analysis/comparison.csv`） · 逐图指标（本地原始证据：`scripts/260920SensorVisualizer/capture_comparison_004/results/comparison_20261012_070140/analysis/image_metrics.csv`）

## 最重要的结果

1. **首先保留传感器资源常驻。**相同 v06 基线、RT2 16＋2 子帧下，整组观察范围中位数从 9.111 秒降至 4.670 秒，缩短 48.7%。三轮 capture 窗口分别缩短 39.2%、36.6%、41.0%。这是本轮最直接的同框架变量对照。

2. **默认 Helper 足以完成本轮冻结采集。**原生冻结 RT2 与 PT 的默认/诊断门控均通过；本场景静止条件下，没有证据支持必须改接 Helper 执行边。耗时差异需看三轮范围，不能以一次小差值认定显著优势。

3. **原生连续 RT2 很快，但工作量不同。**它没有逐组 16＋2 预热/正式子帧，也没有冻结组的完整载荷哈希观察范围。这里只能作为低等待、不同累积预算的对照，不能宣布同画质几十倍提速。

4. **高采样 PT 主要在持续计算。**1024 目标 SPP 的冻结 PT 明显增加耗时，GPU busy 长时间保持高位。提高利用率不等于提高有效数据产出速度。

5. **原生连续 PT 仍不能作为合格交付链路。**原生调度/预算检查和最终 MCAP 对齐是两件事。其失败结果保留为诊断证据，未修改消息时间或放宽容差使其通过。

## 一组与一轮分别用了多久

| 配置 | 通过轮次 | 一组观察/更新中位数 s | 首组 s | 后续组 s | 6 组 capture 窗口中位数 s |
|---|---:|---:|---:|---:|---:|
| v06 gated RT2 16+2 | 3/3 | 9.111 | 8.869 | 9.127 | 55.283 |
| v06 keepalive RT2 16+2 | 3/3 | 4.670 | 8.943 | 4.658 | 33.605 |
| native continuous RT2 | 3/3 | 0.162 | — | — | 0.992 |
| native frozen RT2 diagnostic | 3/3 | 4.452 | 7.585 | 4.426 | 31.970 |
| native frozen RT2 default | 3/3 | 4.523 | 7.931 | 4.496 | 32.286 |
| native frozen PT diagnostic | 3/3 | 95.448 | 102.537 | 95.397 | 582.322 |
| native frozen PT default | 3/3 | 96.979 | 103.063 | 95.850 | 584.162 |
| native continuous PT | 0/3 | 81.027 | 81.457 | 81.018 | 490.585 |

v06 的观察范围为推进时钟开始至独立载荷持有完成；原生冻结为准备开始至 RGB/XYZ 哈希观察完成，两者数据持有和校验成本不同。连续 RT2 列的是单次应用更新；连续 PT 范围可能交叠且录包失败，其数字只表示诊断成本。窗口不包含相同的尾部工作，因此另保存进程总耗时，详见完整报告。

每项只有三次独立进程运行；18 个组内样本不是 18 次独立实验。静止测试的初始化、时域累积及资源历史会影响首组和后续组，不能忽略首组成本。

## 时间消耗落在哪些阶段

| 配置 | 阶段 | 阶段墙钟中位数 s | 阶段内 GPU busy 样本均值 % | Kit CPU 样本均值 % |
|---|---|---:|---:|---:|
| 01_v06_gated | lab.SceneStepper.advance_clock | 0.445 | 36.000 | — |
| 01_v06_gated | lab.SceneStepper.apply_snapshot | 0.007 | — | — |
| 01_v06_gated | lab.SensorDrivers.warm_cameras | 7.900 | 23.865 | 153.166 |
| 01_v06_gated | lab.SensorDrivers.acquire | 0.819 | 56.500 | — |
| 01_v06_gated | lab.RecordPipeline.submit | 0.040 | 40.000 | — |
| 02_v06_keepalive | lab.SceneStepper.advance_clock | 1.110 | 61.706 | 305.636 |
| 02_v06_keepalive | lab.SceneStepper.apply_snapshot | 0.007 | — | — |
| 02_v06_keepalive | lab.SensorDrivers.warm_cameras | 2.866 | 49.968 | 184.298 |
| 02_v06_keepalive | lab.SensorDrivers.acquire | 0.669 | 55.417 | — |
| 02_v06_keepalive | lab.RecordPipeline.submit | 0.141 | 56.000 | — |
| 05_native_frozen_rt_default | advance | 0.933 | 62.750 | 184.915 |
| 05_native_frozen_rt_default | warm | 2.958 | 59.536 | 203.676 |
| 05_native_frozen_rt_default | formal | 0.513 | 58.900 | — |
| 05_native_frozen_rt_default | evidence | 0.123 | 67.667 | — |
| 07_native_frozen_pt_default | advance | 12.228 | 95.424 | 124.171 |
| 07_native_frozen_pt_default | warm | 79.814 | 96.830 | 123.574 |
| 07_native_frozen_pt_default | formal | 4.770 | 61.370 | 212.685 |
| 07_native_frozen_pt_default | evidence | 0.118 | — | — |

上表为不同链路自身的阶段，名称相似不保证内部工作相同。GPU 是约 1 Hz 的整卡 busy 样本，不是 CUDA/RT/Tensor Core 利用率；CPU 100% 表示一个核，只统计差分区间完整落在阶段内的样本。短阶段无可靠 CPU 样本时留空，不推断为零。

v06 常驻的主要收益出现在预热范围；首组仍承担初始化，而后续组缩短。常驻也会让推进阶段发生额外渲染，故个别阶段变慢不矛盾。本轮对照支持资源启停影响总耗时，但没有新增驱动调用栈或 GPU 指令级跟踪，不能把所有节省时间都断言成模块卸载/重载。

冻结 PT 的 advance 阶段也有明显 GPU 工作，准备步骤包含引擎更新，不能把整个 advance 都叫作 CPU 更新变换。SDK step 的完成范围也不是纯 GPU kernel 时间。

## 资源占用与间歇问题

| 配置 | 三轮 GPU 均值范围 % | GPU≤5% 的样本比例范围 | GPU≥90% 的样本比例范围 | 显存峰值 GiB | Kit RSS 峰值 GiB |
|---|---:|---:|---:|---:|---:|
| 01_v06_gated | 24.8–31.0 | 53.1–59.6% | 3.7–8.2% | 10.700 | 11.048 |
| 02_v06_keepalive | 51.1–55.2 | 15.6–18.8% | 9.4–18.8% | 10.446 | 11.257 |
| 03_native_continuous_rt | 42.0–87.0 | 0.0–0.0% | 0.0–0.0% | 7.851 | 9.365 |
| 04_native_frozen_rt_diagnostic | 55.7–64.2 | 3.4–7.4% | 7.1–17.2% | 7.899 | 9.508 |
| 05_native_frozen_rt_default | 56.5–63.1 | 3.4–3.7% | 0.0–24.1% | 7.899 | 9.503 |
| 06_native_frozen_pt_diagnostic | 94.6–95.1 | 0.4–0.7% | 88.0–88.4% | 9.725 | 9.711 |
| 07_native_frozen_pt_default | 94.3–95.9 | 0.2–0.4% | 87.8–89.1% | 9.730 | 9.763 |
| 08_native_continuous_pt | 96.7–97.7 | 0.0–0.2% | 93.5–94.5% | 9.708 | 9.708 |

连续 RT2 的六组窗口不足或接近一秒，约 1 Hz 监控只有极少样本，其均值和比例不能用于判断持续利用率；完整报告和曲线标注了样本数。PT 的较长窗口较容易观察持续负载。这里没有 SM occupancy、RT Core 活跃周期或 PCIe 全链路带宽实测，不能从 busy 推算这些指标。

## 图片、公共输入与数据组织

全部有效采集的 17 路传感器实际 MCAP TF 与公共雷达参数对照结果：**True**。相机内参、光学世界变换和受控关节另外逐图核对。最大矩阵误差：8.01364934e-07。不同链路的时间原点与步长保持原样；同组号表示同一静止输入，并非同一绝对仿真时间。

全部 PNG 来自实际 MCAP，没有重新渲染替代数据。图片浏览器包含四方向原图和三轮并排图；局部裁剪保留原像素，没有锐化。选定的前向地面/机体区域中，PT 与 RT2 的亮度差异明显，而地面仍保留类似的模糊纹理。1024 SPP 不能保证补回资产本身的细节；该观察也不足以确认 3DGS 未加载完成，需要专门的加载完成信号、纹理/3DGS 层级和相机对照实验。

图像 MAE/PSNR 是相对于 05 默认冻结 RT2 的差异，并非绝对画质分数。与自己比较为零也不能证明“最好”。四路鱼眼黑边参与整图指标；局部对照用于辅助肉眼判断。

原生使用 ROS Image，v06 使用 PNG CompressedImage；原生可能录到预热、正式和尾部的额外发布。因此相同 24 张选定图片不等于 MCAP 大小相同。额外发布量、CDR 字节数与点数范围见每项 decoded.json。

```text
results/comparison_20261012_070140/
  01_v06_gated/ … 08_native_continuous_pt/
    round_01/ … round_03/
      images/<front|back|left|right>/       # 通过校验的图片
      diagnostic_images/...              # 失败链路证据
      frames.csv / frame_metadata.json    # 时间、内参、TF、关节
      decoded.json                        # 消息计数、点数、解码校验
      timing.csv / phase_timing.csv        # 逐组、逐阶段时间与采样
      capture/                            # 原始日志、配置、资源采样
  analysis/                              # 汇总、差分、图片索引、资源曲线
  final_integrity.json                    # 旧代码及根 USD 哈希和进程检查
```

MCAP 保留在云端同名输出目录，每个原生 capture/bag/ 内，v06 在 capture/captures/<session>/bag_unified/ 内。本地下载的是解码图片和分析证据，未额外复制全部 MCAP。

## 数据量对照

| 配置 | 三轮 MCAP 大小范围 MiB | 每路相机实际消息数范围 | 每轮选定 PNG 数范围 |
|---|---:|---:|---:|
| 01_v06_gated | 102.00–102.29 | 6–6 | 24–24 |
| 02_v06_keepalive | 104.26–104.43 | 6–6 | 24–24 |
| 03_native_continuous_rt | 512.62–512.62 | 17–17 | 24–24 |
| 04_native_frozen_rt_diagnostic | 332.09–332.09 | 11–11 | 24–24 |
| 05_native_frozen_rt_default | 332.09–332.09 | 11–11 | 24–24 |
| 06_native_frozen_pt_diagnostic | 332.73–332.73 | 11–11 | 24–24 |
| 07_native_frozen_pt_default | 332.73–332.73 | 11–11 | 24–24 |
| 08_native_continuous_pt | 151.26–151.26 | 5–5 | 20–20 |

逐项字节数、消息数见 data_volume.csv；各路雷达点数范围见 point_counts.csv。点数统计覆盖包内该话题全部消息，包括可能存在的预热/尾部消息；它不是按相同目标组逐点匹配的误差指标。

## 点云一致性仍有一项未解释

录包时序通过不等于跨链路几何结果逐点相同。v06 与原生链路的部分 NZ3 点数存在稳定差异；以下是第一轮第一目标组的实际 MCAP XYZ 距离统计：

| 配置 / MyNZ3_left | 总点数 | 距离≤0.5 m | 距离≤1 m | 距离≤2 m |
|---|---:|---:|---:|---:|
| 01_v06_gated | 35297 | 1139 | 5012 | 7712 |
| 02_v06_keepalive | 35297 | 1139 | 5012 | 7712 |
| 05_native_frozen_rt_default | 27711 | 22 | 185 | 1438 |

对 v06 gated、keepalive、原生默认冻结 RT2 的三轮首组，共 117 个传感器样本检查：非有限点 0，零 XYZ 点 0，缺失样本 `[]`。逐路分位数见 lidar_ranges.csv。

差距主要集中在近距离，但本轮尚不能确定是近处几何在 RTX 中的状态、射线发射/噪声时序，还是 CPU/GPU 提取路径的行为不同。已发布 TF 相同也不能单独证明 RTX 内部所有遮挡几何完全相同。不要把这一差异直接称为随机噪声，也不要将原生更少的点自动判成更准确。

后续应固定发射状态与时钟，核对 RTX 传感器的实际变换及近场遮挡几何，再同时比较 CPU/GPU 提取器的同一次原始结果。上表第一轮首组的 v06 gated/keepalive 距离统计一致，但第二轮也有差异；本轮未固定噪声随机种子，不宣称逐点一致。跨链路点云的完全等价性仍未证明。

## 未通过的连续 PT

- 第 1 轮：通过=False，导出 20 张诊断图片；消息相对目标时间偏移 [16145832, 16145833] ns；缺失项 `[{"group": 0, "missing_images": ["front", "back", "left", "right"]}]`。
- 第 2 轮：通过=False，导出 20 张诊断图片；消息相对目标时间偏移 [16145832, 16145833] ns；缺失项 `[{"group": 0, "missing_images": ["front", "back", "left", "right"]}]`。
- 第 3 轮：通过=False，导出 20 张诊断图片；消息相对目标时间偏移 [16145832, 16145833] ns；缺失项 `[{"group": 0, "missing_images": ["front", "back", "left", "right"]}]`。

约 16.145833 ms 的偏移在数值上接近 (31/32)×(1/60 s)，提示原生子帧与 ROS 发布的时钟相位值得追查，但数值吻合不是根因证明。不能只改 header 让图像与 TF 看似对齐；后续应对照最终渲染回调、IsaacReadSimulationTime、发布执行边和 ROS 录包顺序。

## warning 的处理结论

- `omni.hydratexture.plugin` 接口重复获取/释放警告：保留原始计数，结合常驻 A/B 结果支持继续研究资源生命周期；它不等价于每组 pip 安装/卸载插件。
- ROS PoseTree `getObjectType eInvalid`：默认和诊断原生配置均出现；本轮实际 TF 数值可核对，但不能据此忽略警告。应将 Fabric/目标 Prim 解析与发布数据来源分开确认。
- `getSimulationTimeMonotonicAtTime ... returning current sim time`：涉及时间映射回退，连续 PT 对齐问题中应优先追查；目前只有关联证据。
- `rendervar copy from texture directly to host buffer is counter-performant`：原生读回路径的性能提示，本轮保留该原生行为，没有擅自替换其 GPU→CPU 拷贝实现。
- MotionBVH 关闭提示：本轮是静止姿态、Instant LiDAR，测试不覆盖运动畸变效果。PerfSDK 不可用等启动提示也原样记录，没有下载组件或改系统消除警告。

## 保留与复现

远端检查：保留的 348 份旧源码变更列表 `[]`；本次运行 engine/suite/config/decoder 变更列表 `[]`；根 USD 未改：True；剩余实验自有进程：`[]`。这只是指定文件和进程的核对，不是整机安全审计。

旧源码 ZIP 和哈希清单在项目 backups/ 与 reports/。未新增下载或更新依赖。短暂 SSH 断连仅影响本地读取，远端独立 supervisor 持续运行，恢复连接后继续取回已有结果，没有重复启动矩阵。首次轨迹适配错误在正式矩阵启动前修正，失败日志保留。

下一步优先保留 v06 资源常驻这一已验证优化；将原生默认 Helper 冻结采集作为替代候选，完成点云等价性核对后再决定是否切换。连续 PT 的发布时序需要单独实验。若目标是交互流畅，仍须另测控制输入延迟，不能用离线每组时间代替界面体感验收。
