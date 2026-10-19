# NC-006：Scene18 点云一致性测试报告

日期：2026-10-13。环境：远端 single 实例，单张 NVIDIA L40，使用已安装 Isaac/ROS/Warp。完整方案见 [测试方案](NC-006_scene18_lidar_equivalence_plan.md)，过程与失败记录见 [执行记录](execution_decisions.md)。

## 1. 结论

**Scene18 的全 mesh 静止场景仍复现了差异；目前最明确的触发条件是冻结策略及其对应的引擎执行时序。差异已经出现在 SDK 可见的 GenericModelOutput（GMO）中，不是 CPU/CUDA 复制、PointCloud2 序列化或 MCAP 存储丢点导致的。**

原生冻结链路保持 timeline 为 Playing、关闭 auto-update 时，NZ3_left 两米内只有约 32–35 个点；改成真正 Pause 的冻结策略后，恢复到约 6,000 个点，与自制链路接近。增加预热到 128 个子帧没有消除缺口。

**不能直接把正式项目改成 Pause 就算修复。** 默认原生 ROS Helper 在三组 Pause 对照中没有录到雷达和相机消息，虽然内存中的传感器数据正常生成。点云生成与发布调度必须分别解决。

本次没有修改正式项目或磁盘场景。已完成三轮基线、两条链路的同帧读取验证、几何归属核对和冻结策略对照。尚未定位 NVIDIA 内部造成有效返回不同的具体函数/条件，也未实施生产修复。

## 2. 固定条件与实验边界

| 项目 | 实际条件 |
|---|---|
| 场景 | `/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_18_terrain_fisheye_mesh.usda` |
| 场景 SHA-256 | `e44ff38c21caaaccf20aa44a9b834e33d7109407e737df27198a63ad95e9fb79` |
| 根节点世界平移 | `[-0.5734956861, 1.4685479403, 0.5559421778]` m |
| 根节点四元数 XYZW | `[0.0212584255, 0.0165569563, 0.0234640675, 0.9993614882]` |
| 关节 | 初始化后实际 boom/arm/bucket 均为 0°；保持该状态，未擅自重定义零点 |
| 传感器 | 13 路 Instant LiDAR：7 MyAiry＋6 MyNZ3；4 路 1920×1080 鱼眼相机 |
| 基线画质 | RT2（RealTimePathTracing）、DLSS Quality=2、AA=3、关闭帧生成；每组 16 预热＋2 正式子帧 |
| 基线进程 | 每条链路 3 个独立进程，每次 3 组；次序 legacy/native、native/legacy、legacy/native |
| 正式冻结期间 | 时间与姿态不推进；组间推进仿真，物体保持同一静止目标姿态 |
| GPU/依赖 | 单卡；无新增下载、依赖安装或升级 |

九个对应组的 135 个 Mesh：已记录的世界矩阵最大差为 **0**；顶点和面索引哈希、有效可见性、purpose 一致；最终生效的 `omni:sensor:*` 属性一致。首个正式组的传感器姿态也通过原有渲染矩阵校验。

保留两条链路各自的初始化历史；绝对仿真时间、GMO 时间起点、渲染帧编号及随机/缓存状态并未强行等同。因此跨进程不以字节完全一致作为唯一正确性标准。USD 矩阵相同不等于证明引擎内部 Fabric/Hydra/TLAS 状态相同。

## 3. 基线差异与重复性

首轮第 0 组，距离指雷达局部 XYZ 到原点的欧氏距离：

| 雷达 | 自制总点数 | 原生总点数 | 自制 ≤2m | 原生 ≤2m |
|---|---:|---:|---:|---:|
| MyNZ3_left | 32,688 | 25,504 | 6,031 | 32 |
| MyNZ3_right | 30,799 | 27,868 | 5,796 | 3,140 |
| MyNZ3_front | 32,860 | 32,719 | 6,190 | 6,294 |
| MyAiry_left | 33,217 | 33,185 | 0 | 0 |

NZ3_left 九个配对组中，自制 ≤2m 点数为 **6,022–6,062**，原生为 **32–35**，缺口不是某一帧偶发少量噪声。第一组自制→原生最近邻距离 P95 约 **1.636m**。

重复性检查：原生第 1 轮与第 2/3 轮的 78 个对应样本全部字节一致；自制第 1 轮对第 2/3 轮不完全一致，最大点数差 104。进一步检查，第 2 与第 3 轮在两条链路上各 **39/39** 字节一致。不能把自制首轮变化直接归因为随机噪声，初始化/缓存历史同样是候选因素；其规模仍远小于跨链路约七千点的缺口。

![基线点云与车体几何](figures/NZ3_left_baseline_comparison.png)

## 4. 差异出现在数据链路的哪里

```text
RTX 内部求交、材质响应、回波有效性处理（未直接观测）
                  ↓
GenericModelOutput / GMO —— 最早已观测到差异的位置
                  ↓
IsaacExtractRTXSensorPointCloud
                  ↓
CPU / CUDA 读取 → 自有 NumPy 副本
                  ↓
PointCloud2 → MCAP 解码
```

证据如下：

1. **基线 234/234 份正式 XYZ 在各自 MCAP 中找到完全相同哈希的消息。** 匹配同时使用源时间戳和 XYZ 哈希；不取“同时间戳第一条”。点布局按字段 offset、point_step、row_step 和端序解码。
2. 两条链路各 39 个同帧诊断样本，**CPU/CUDA XYZ 39/39 一致**，连续读取前后原始 GMO 帧号和 XYZ 哈希不变，期间没有 Kit 更新、渲染或仿真步进。
3. 两条成功诊断各 39 个样本，**GMO 的 CARTESIAN x/y/z 与正式点云 39/39 完全相同**。两条诊断的正式 XYZ 也全部与自己的 MCAP 对应。
4. 同一 RenderProduct 的图连接证明提取节点从 `GenericModelOutputPtr` 接收数据。原始数组使用已安装官方 `parse_generic_model_output_data()` 解析。

这里的“原始”严格指 **SDK 导出的 GMO**。GMO 可能已经完成内部有效返回筛选；本次没有拿到 RTX 内部每一条射线的未过滤命中记录，因此不能把问题进一步武断地定为“BVH 求交漏命中”或某个内部过滤函数。

### 发射器配对

当前 BASIC 附加数据提供 emitterId、channelId、echoId、tickId。NZ3_left 的组合键在单帧内唯一，按键配对而非按数组行号比较：

- 同帧探针第 0 组：双方共同保留 **24,570** 条返回；方向差 P95 约 `1.21e-6°`，距离差 P95 约 `5.26e-7m`。
- 自制独有的返回中有 **6,029** 个落在两米内。
- 共同返回中没有“自制两米内、原生两米外”的射线。

因此主要现象是 **某些返回在原生输出中缺失**，而非大批共同返回被变换到不同位置。跨进程组合键只标识发射通道/时序槽，不证明绝对发射时间或随机状态一致。

### 探针的影响

增加原始输出 observer 后，原生各样本相对无探针基线的点数变化为 -156～+124；自制相对首轮为 -72～+104。不能声称探针对跨运行逐字节结果无影响。不过，探针没有改变 NZ3_left 约 6,000 对约 33 的结构性差异；同次输出的 CPU/CUDA/GMO 一致性检查不依赖跨进程字节相等。

## 5. 差异点对应的真实几何

从正式静止状态导出可见三角网格，用现有 Warp 创建独立 BVH，调用 `mesh_query_point_no_sign`、`mesh_eval_position` 和 `mesh_query_ray`。共检查 **768,172 个三角形**；分析核先通过已知平面的距离及射线解析验证。

首轮 NZ3_left 自制链路的 6,031 个两米内点：

| 归属 | 点数 |
|---|---:|
| `/World/Excavator/swing_link/Visuals/MeshAlignment/Geometry/Mesh`（上车体） | 5,810 |
| `/World/Excavator/track_link/Visuals/MeshAlignment/Geometry/Mesh`（履带） | 221 |

这些点全部距对应 Mesh 表面不超过约 **1.22 微米**，沿相应射线到已导出网格的首个命中距离也全部在 1cm 内一致。其几何位置有明确支持，不能视为没有实体依据的幽灵点。原生对应 32 个近点中，上车体 24、履带 8。

NZ3_right 的近点同样主要属于上车体和履带：自制 4,210＋1,586，原生 1,556＋1,584。差异最集中在上车体表面。

限制：独立 BVH 不模拟 RTX 材质/透明度/回波能量筛选；导出未纳入 Cube、Plane 分析基元；非三角面采用扇形三角化，挖掘机部件本身为三角形、subdivision=none。因此“点落在真实车体表面”证据很强，但不能由此断言全部应被实际光学模型保留，也不能证明任何点都没有其他未纳入遮挡。NZ3_front 存在少量不能由当前导出表面解释的点，本轮未据此宣称整套数据已达到几何真值。

## 6. 冻结方式与预热对照

![冻结策略对照](figures/NZ3_left_freeze_policy_control.png)

| 对照 | NZ3_left 总点数 | ≤2m | 结论 |
|---|---:|---:|---|
| 原生 auto-update 冻结，16+2，无原始探针 | 25,504 | 32 | 基线缺口 |
| 同策略，16+2，有原始探针 | 25,572 | 33 | 探针未消除缺口 |
| 同策略，128+2，有原始探针 | 25,566 | 33 | 多预热 112 子帧未恢复 |
| Pause 策略，16+2，有原始探针 | 32,656 | 5,991 | 大量近点恢复 |
| Pause 策略，16+2，无原始探针，组0 | 32,646 | 6,038 | 无探针复现恢复 |
| 同上，组1 | 32,688 | 6,027 | 持续恢复 |
| 同上，组2 | 32,626 | 6,036 | 持续恢复 |

控制改动仅在新实验的配置中：

```text
原生基线：freeze_method=autoupdate，pause_after_step=false
对照配置：freeze_method=pause，pause_after_step=true
```

对应 `timeline.set_auto_update(False)` 与 `timeline.pause()/commit()`、`rep.orchestrator.step_async(... pause_timeline=...)` 的不同调度。

无探针 Pause 三组与原生基线的 Mesh 世界矩阵最大差仍为 0，传感器参数无差异。正式渲染前后仿真时间完全不变，传感器姿态变化为 0，关节目标误差为 0。与自制第二轮相比，NZ3_left 最近邻 P95 从米级降到约 `1.1e-6m`，但仍有少量不同返回和较大离群最近邻距离，不能宣称点云全面严格一致。

**已证明冻结策略及伴随执行历史可以改变结果；尚未单独隔离某个布尔量。** Pause 对照同时改变了渲染帧编号、初始化时间偏移和内部执行顺序，所以不应把整件事简化成“时间暂停按钮本身存在某个已知引擎 bug”。

### 发布与录包没有同步解决

三组无探针 Pause 试验：引擎退出码 0，内存点云正常；原有全包校验及分组校验退出码均为 1。MCAP 缺少 13 路点云以及四路图像/CameraInfo 消息。因此该包是**失败诊断产物**，不能交付为有效采集包。

128 预热的单组诊断也有部分话题未录到；其结论仅依据已校验的 GMO/提取数组，用于回答“多预热是否恢复近点”，不把该 MCAP 计为有效基线。

默认 Helper 图含物理时钟/执行门控，Pause 与默认发布调度不兼容是目前有依据的下一步调查方向；准确哪个门控阻断需要继续跟踪，不在本报告中冒充已经完成节点级因果验证。

## 7. 建议的下一步

1. **保持真实 Pause 的几何生成结果，独立解决完成触发与发布。** 从同次 GMO/提取完成信号发送点云和图像，记录原生仿真时间；先证明“内存数据＝正式消息＝MCAP”，再考虑替代正式入口。
2. **继续隔离 Playing/冻结期间的内部几何状态。** 对照 USD、Fabric/PhysX、Hydra 场景提交及 TLAS 更新时机。必要时仅在新的诊断输出中保留无效射线和更完整的附加字段，查明 missing emitter 是求交、材质响应还是有效性筛选所致。
3. **不要靠增加子帧、修改 TF 或点云后处理填补缺口。** 本轮证据已经不支持把这些作为首要修复方向；不应直接用“点多/原生”作为正确性的标签。
4. 修复验收保留同一场景静止三轮，再扩展移动姿态；同时验收图像、TF、源时间与 MCAP。性能优化放在正确性闭环之后。

## 8. 交付与证据索引

代码与文档：

- 本地：`D:\learning\IntelligentDepartment\CodesSet\Self\260707IsaacSIm\scripts\260920SensorVisualizer\lidar_equivalence_006`
- 云端：`/root/gpufree-data/semantic/scripts/260920SensorVisualizer/lidar_equivalence_006`
- 云端完整输出：`/root/gpufree-data/semantic/output/lidar_equivalence_006/study_20261013_030531`

| 输出子目录 | 内容 |
|---|---|
| `baseline_pose` | 实际初始化基准姿态、三行静止轨迹、19 项 USD 依赖哈希 |
| `legacy/round_01..03/capture` | 自制三轮正式 MCAP、正式数组、状态证据、日志 |
| `native/round_01..03/capture` | 原生三轮正式 MCAP、正式数组、状态证据、日志 |
| `analysis` | 六次基线的 MCAP 匹配、跨链路统计、重复性 |
| `native_dual_retry1` / `legacy_raw_retry1` | 成功的两种链路同帧 GMO/CPU/CUDA 诊断 |
| `raw_analysis` | 第一批 78 个 GMO 与正式输出核对、按发射器配对 |
| `geometry_analysis` | 最近表面和射线查询证据、几何分析核缓存 |
| `diagnostic_analysis` | 成功探针与单组预热/Pause 控制统计 |
| `native_pause_no_probe` / `pause_confirmation` | 不带原始探针的三组 Pause 复测及其失败录包验收 |

每次运行的配置、原始日志和失败结果均保留。新项目 `deploy_history` 保存覆盖前的实验源码；`docs/experiment_source_changes.patch` 记录相对原始副本的改动。`results/*/transfer_manifest.json` 是本地拉取文件的大小/SHA-256 证明，完整 MCAP 留在远端，本次未把全部实验包下载到本地。

最终保全核对：**本地原始 79 个源文件未变；远端同一 79 个源文件与原始哈希一致；19 项场景依赖未变；所有本次 Kit 采集进程已退出。**
