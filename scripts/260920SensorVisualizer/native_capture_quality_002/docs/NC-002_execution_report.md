# NC-002 执行报告：原生冻结采集、子帧、Path Tracing与底层追踪

执行日期：2026-10-12。批准方案原文保存在 `NC-002_implementation_plan.md`，本报告记录实际结果，不覆盖方案原文。

## 1. 已完成的交付

独立实验项目已经在本地和单卡云实例部署，名为 `native_capture_quality_002`。原生引擎不导入 `v06`、`single06_lab` 或首轮原生项目的运行时代码。旧链路对照由独立进程运行其保留的CLI，输入及产出写在新实验目录。

本轮完成冻结采集验证、45组实时子帧扫描、12组PT采样预算扫描、默认Helper控制实验、三轮旧链路与三轮默认原生对照、真实Nsight追踪、标准MCAP解码校验。失败实验及误标为trace的普通实验一并保留。

主要结论：

- 默认ROS Helper生成的图可以在仿真时间及姿态固定时，录到当前的四路图像、13路点云和对应TF。最终默认无需改接门控。
- 原生接口没有消除SDK渲染和主机固定页内存生命周期的成本。旧链路资源常驻后，与当前原生链路的差距明显缩小。
- 实时预热子帧减少能缩短实测时间，但像素会变化；尚未证明满足用户要求的同等画质。
- PT在当前场景能同时产出图像和LiDAR数据，但1024目标SPP成本很高，且不自动修复3DGS素材细节。

## 2. 保存、部署与改动范围

本地项目：

```text
D:/learning/IntelligentDepartment/CodesSet/Self/260707IsaacSIm/scripts/260920SensorVisualizer/native_capture_quality_002
```

云端项目与输出：

```text
/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_quality_002
/root/gpufree-data/semantic/output/native_capture_quality_002
```

旧代码快照：本地 `backups/20261012_pre_NC002_sources.zip`，云端 `backups/pre_NC002_sources.zip`。本地检查287个旧源文件、云端检查285个旧源文件，与各自执行前清单一致；二者清单文件数不同，不混为同一份镜像。

USD改动仅在本实验的匿名Session层。根场景磁盘文件前后SHA256一致：

```text
combine_scene_16_terrain_fisheye.usda
ab2a2ef736030adba3420450f916420e705952a04fec163c05b545655fc7f0ae
```

没有下载、安装或更新外部依赖，没有修改系统、桌面、Isaac安装或旧项目代码。结束时没有遗留本轮Kit/采集进程；GPU回到2%、609MiB显存。根USD校验不等同于对所有贴图及payload做了执行前后的完整哈希审计。新源码本地语法编译通过；执行入口面向Linux，Windows直接导入run.py缺少Unix的resource模块，因此运行验证以云端实测为准，未为此安装依赖。

## 3. 环境与对照条件

单GPU NVIDIA L40；Isaac Sim 6.0.1 rc7；ROS2 Jazzy；使用已安装的Kit、Replicator、ROS Bridge、rosbag2 MCAP、NumPy、Pillow、Nsight Systems。

同一场景、同一13路Instant LiDAR、四路1920×1080鱼眼、同一DomeLight；停用场景中原先持久化的重复采集图。关闭viewport及Motion BVH、Multi-tick/per-sensor TLAS，保持单卡。更换相机渲染模式没有更改LiDAR角采样表。

实时配置是 `RealTimePathTracing`，AA=3、DLSS execMode=2，关闭帧生成。PT配置是 `PathTracing`，每次迭代请求32SPP，目标64/256/512/1024SPP、8反弹、关闭自适应采样、开启OptiX降噪、关闭时间降噪和运动模糊。

默认原生参考记录的曝光设置包括：自动曝光关闭、相机fStop=5、ISO=100、曝光时间约0.02秒；全局histogram关闭，tonemap op=6、filmIso=100、cameraShutter=50、fNumber=5。旧参考相机清单中的fStop、ISO、responsivity、time与之相符。

尚未完全对齐：初始化更新次数、内部随机状态、每组累积重置、所有GPU纹理驻留状态、消息格式与数量、结束收尾计时边界。早期预算扫描没有逐组记录完整曝光/内部累积状态，不能借后续的设置日志反证早期每组状态。

## 4. 一组原生数据的实际顺序

1. 组间恢复时间轴自动推进，执行6个物理更新；设置关节/传感器目标姿态。
2. `timeline.set_auto_update(False)`，保持播放状态，固定当前仿真时间；提交姿态并记录预期TF和关节值。
3. 重置渲染累积，使用官方 `rep.orchestrator.step_async(delta_time=0, pause_timeline=False, wait_for_render=True)` 执行预热。
4. 再执行正式零时间增量采集，原生节点提取、转换并通过ROS发布，标准 `ros2 bag record` 写MCAP。
5. 原生RGB/点云观察接口读取当前结果；记录字节哈希、相机/LiDAR渲染位姿、关节、TF及仿真时钟。画质扫描另输出PNG，普通原生对照不输出额外PNG。
6. 验证采集前后仿真时间与USD位姿不变；下一组再恢复自动推进。
7. 整轮结束后执行一次SDK drain，正常关闭录包器，离线解码MCAP做逐组严格核验。

保持渲染资源常驻，关闭隐式capture-on-play，避免逐组暂停/停止引发的生命周期切换。组间物理更新仍有渲染成本；冻结只指正式组内，不意味着启动和组间都没有引擎更新。

这里的“原生”是使用NVIDIA的图节点、渲染/提取/发布接口及标准录包器；仍需要少量Python配置、组调度与证据记录，并非完全没有用户脚本。

## 5. 有效数据的判断

逐组要求：

- 四个Image、四个CameraInfo、13个PointCloud2在本组原生时间戳存在。
- MCAP内四路RGB与当前原生观察结果字节相同；13路XYZ字节相同。
- 18条TF父子关系及数值、关节角、相机和LiDAR实际渲染姿态一致。
- 正式采集期间时钟与位姿不变；不同组拥有不同的原生时间戳。

没有重写header、补时间戳或用预热数据冒充新组。源帧编号未暴露，不能把组编号当成底层源帧证明。结果同时保留数据字节和位姿检查，避免只凭话题存在判断成功。

早期冻结失败轮次中，观察接口拿到新图像、MCAP却停留在初始化时间戳。诊断版本曾改接21条仿真门控与13条点云发布完成连接；首次成功及45组RT、12组PT预算扫描使用这个诊断版本。其后默认门控控制实验、18组原生参考、真实Nsight的4组都通过；最终默认 `bypass_native_simulation_gate=false`。这证明改接不是必需，不证明常驻资源、捕获拥有者和观察接口组合中的每一项单独都是必要条件。

## 6. 实时子帧扫描

每个预算9组，涵盖静止、关节跳变、前相机及前LiDAR安装旋转三类姿态，各重复3次。以下来自早期“原生节点冻结适配诊断”，不能称为默认Helper完整预算扫描。

| 预热子帧 | 正式子帧 | 组准备+SDK返回中位数，秒 | 对16子帧参考的平均RGB MAE | 平均PSNR，dB |
|---:|---:|---:|---:|---:|
| 1 | 2 | 1.744 | 3.776 | 31.159 |
| 2 | 2 | 1.909 | 3.632 | 31.412 |
| 4 | 2 | 2.215 | 3.201 | 32.604 |
| 8 | 2 | 2.852 | 2.829 | 33.759 |
| 16 | 2 | 4.116 | 参考 | 参考 |

每个非参考预算的质量统计为4相机×9组。正式SDK调用约0.49秒，组间准备约0.88秒；增加预热是主要的额外成本。PNG观察导出另外约2.5秒/组，未包含在表中，已包含在整轮233.84秒窗口中。第一组含冷态开销，最大值4.82秒，不能当稳态1子帧速度。

16子帧参考并非质量真值；不同随机/历史状态也会改变像素。灰度box7 SSIM为本项目明确定义的诊断指标，不冒称其他库的标准实现。可以确定预算影响耗时，不能仅凭上述指标确定最低可接受预算，更不能自动把正式项目改成1子帧。

## 7. Path Tracing扫描

每预算3轮，正式与预热各一次显式SDK调用。以下同样来自早期改接诊断版本；后续默认Helper的1024SPP代表性测试也通过，但没有对全部预算再跑完整默认矩阵。

| 目标SPP上限 | 组间准备中位数，秒 | 预热中位数，秒 | 正式中位数，秒 | 组准备+SDK返回中位数，秒 | 对1024参考平均MAE |
|---:|---:|---:|---:|---:|---:|
| 64 | 11.671 | 5.007 | 0.552 | 17.230 | 22.147 |
| 256 | 11.662 | 19.021 | 1.352 | 32.069 | 4.597 |
| 512 | 11.659 | 37.797 | 2.409 | 51.886 | 1.583 |
| 1024 | 11.659 | 75.406 | 4.549 | 91.604 | 参考 |

整轮窗口616.41秒，另外PNG导出约2.3～2.6秒/组。6个组间物理更新在PT模式下也昂贵，这是可见的重复预览渲染成本；不能只把后续正式SDK调用的4.55秒称为1024SPP完整组成本。

`totalSpp`是请求累积上限，两个SDK调用可能复用或重置内部累积；本轮没有读取到每张图像硬件实际执行的样本数。不能简单声称“1024×2条射线/像素”。

64SPP第一轮四相机MAE约2.05～2.33，后两轮约30.30～35.51，视觉检查也出现明显亮度差异。不能把平均22.147解释为单纯蒙特卡洛噪声，也不能据此证明64SPP天生画质很差；需要隔离不同预算切换、累积/降噪历史与曝光状态。256/512的差异更小，但仍未做最终任务质量验收。

3DGS车体和地面的重建模糊在高SPP图像中仍可见，栅栏等mesh相对清晰。Path Tracing改善采样与光照，不凭空补齐资产没有的几何/颜色细节；本轮也没有单独证明所有素材的GPU驻留就绪时点。

## 8. 原生与旧链路的三轮对照

同一静止姿态，各轮6组；旧gated和keepalive按AB/BA/AB顺序，原生参考独立启动三次。各自都保留16预热+2正式子帧，并关闭本实验额外PNG导出。各相机光学坐标约定统一后，最大位姿矩阵差约1.08e-15，四路鱼眼标定完全匹配。已记录的LiDAR近远距、Instant、scanType、频率相符；旧清单未记录outputFrameOfReference，不能将缺失字段视为已验证相等。

| 链路 | 三轮各自每组中位数，秒 | SDK调用作用域中位数，秒 | 三轮各自整轮窗口，秒 |
|---|---|---|---|
| 旧gated | 8.341 / 8.437 / 8.410 | 7.648 / 7.763 / 7.736 | 50.779 / 51.205 / 51.343 |
| 旧keepalive | 4.439 / 4.503 / 4.439 | 3.360 / 3.394 / 3.360 | 32.034 / 32.285 / 31.852 |
| 默认原生 | 4.163 / 4.128 / 4.177 | 3.194 / 3.168 / 3.201 | 29.987 / 29.726 / 29.886 |

每组中位数列：旧链路从准备到拥有输出载荷；原生从准备到当前输出观察完成，包含约0.11秒哈希/读取。旧SDK事件可能包含回调物化，原生另记观察工作。各链路第一组均有额外开销，例如原生约7.1～7.3秒。中位数与整轮除以6含义不同。

整轮窗口边界不同：原生不包含约1.1秒最终SDK drain及录包器关闭，旧capture.wall包含管线尾部。因此表中窗口不能直接换算成纯调度加速倍数。初始化、每组累积重置和生成随机历史也不完全相同。

每轮第二组的图像还做了跨链路解码检查：24次比较的RGB MAE约2.54～3.55、PSNR约31.77～34.16dB，平均亮度接近。输出不是逐像素相同，不能宣称严格同质量；样图保存于 `final_analysis/cross_images/`。

可以支持的结论是：逐组启停带来的额外工作很明显，保持常驻已拿到大部分阶段性收益；改为原生后，相对旧keepalive剩余差距较小。当前证据不支持“原生比自制快几十倍”的说法。

## 9. 实际底层追踪

有效轮次是 `wave_trace_20261012_032227/capture`，使用默认门控。3组RT16与1组PT1024（模式切换）都通过严格校验。`trace=true`及 `profile_capture_verified=true`，SQLite有 `NATIVE_CAPTURE_WINDOW`、12个组内NVTX阶段、1kHz设备GPU_METRICS。

早期两轮名称带trace却没有真正追踪：命令行缺省false覆盖了配置true。已修正启动器并加证据检查，早期轮次只保留普通采集结果。本次追踪包含诊断与工具开销，不用于普通速度排名。

| 阶段 | 墙钟，秒 | SMs Active平均，% | SM Issue平均，% | cudaFreeHost次数 | cudaFreeHost包含等待的API墙钟，秒 |
|---|---:|---:|---:|---:|---:|
| RT关节组预热 | 2.933 | 35.48 | 5.69 | 221 | 1.761 |
| RT关节组正式 | 0.522 | 35.48 | 5.72 | 39 | 0.314 |
| RT关节组PNG证据导出 | 2.600 | 2.09 | 0.34 | 0 | 0 |
| PT1024预热/累积 | 80.318 | 87.08 | 11.66 | 429 | 77.079 |
| PT1024正式调用 | 4.623 | 32.41 | 5.37 | 429 | 2.719 |
| PT1024 PNG证据导出 | 2.321 | 1.51 | 0.23 | 0 | 0 |

整个114.27秒窗口记录2145次cudaFreeHost、2144次cudaHostAlloc。前者API墙钟总和89.35秒，单次最长2.456秒；后者总和3.14秒。主线程被调度约112.98秒，CPU叶模块采样以libcuda为主，PNG证据阶段还出现libz/Pillow。

这说明原生节点与观察读回链路中仍存在频繁固定页主机缓冲区生命周期和驱动等待。PT预热时GPU也持续高活跃，长cudaFreeHost与GPU工作重叠；不能将77秒当作独立内存释放计算成本，或断言把free删掉就能省77秒。需要进一步以调用栈、API开始/结束和GPU任务依赖核实同步来源。

稳态记录中未见持续 `cuModuleLoad*` / `cuModuleUnload` 成对循环；有3次cuModuleGetLoadingMode查询，以及模式切换时的其他库/核函数活动。这轮不支持“LiDAR插件每帧卸载重装”作为主瓶颈。未覆盖的API、启动加载及其他场景不能由此排除。

设备计数器区分了渲染高负载和CPU导出低GPU阶段。SMs Active表示SM活跃程度，SM Issue是指令发射相关吞吐，均不等于CUDA核算力利用率或warp occupancy。没有拿到RT Core逐核利用率、每个kernel的stall原因和实际路径样本数。

Vulkan工作区间可以跨等待或队列空闲，RT的PNG阶段区间并集仍覆盖整个阶段，而SMs Active只有约2%；因此不能把区间并集当有效计算忙碌时间。CUDA拷贝区间、运行时与驱动API也可能重叠，不能机械相加。

当前导出的GPC/SYS时钟标成MHz，却包含十亿量级甚至负数，解析器已标记为不可解释；保留原值，不擅自单位修正。PCIe计数器为设备吞吐百分比，未把它伪换算为控制器Hz、有效GB/s或链路瓶颈。

## 10. Warning与剩余风险

有效追踪日志仍有3648条PoseTree eInvalid提示，目标主要是辅助坐标Xform、光学坐标及OmniLidar；这说明默认targetPrim路径走了SDK的非Fabric类型路径。当前组内TF数值检查通过，但日志开销未做隔离测试，也不能推广为所有资产均安全。后续可按现有SDK建议使用ComputeTransformTree显式数组接口，另开实验对照，不修改旧项目。

136条getSimulationTimeMonotonicAtTime提示出现在冻结渲染时间映射查不到样本时；SDK明确回退到当前仿真时间。当前验证匹配冻结时刻，但尚未验证所有帧时间映射内部机制。MotionBVH关闭提示也保留：本轮Instant、组内静止的快照不包含运动扫描效果，不能据此承诺连续动态扫描正确。

启动还有schema注册、弃用接口、音频设备等warning。正式校验没有因此失败；不能仅因“属于启动warning”就将它们全部认定无影响。没有改动SDK安装去压掉这些日志。

仍需研究：PT64预算切换后的亮度差；相机每组实际累积样本数；PNG/原生RGB同格式同数量录包的严格成本；关闭额外CPU观察后的固定页调用归属；SDK内部同步调用栈；warning成本；持续键盘预览的响应延迟。该实验为离线采集基线，不是正式操作面板替换版。

## 11. 证据索引与数据结构

本地 `reports/runs/`：

```text
rt_sweep/                     45组RT扫描日志、逐组校验、180张图
pt_sweep/                     12组PT扫描日志、逐组校验、48张图
default_native_reference/     三轮各6组默认原生参考
preserved_single06_reference/ 6轮旧参考，各6组，gated/keepalive
verified_default_trace/       有效Nsight摘要、nsys-rep、原始日志和代表样图
  capture/phase_analysis.json 按预热/正式/观察阶段的底层数据
  final_analysis/
    reference_comparison.json 位姿、标定与计时作用域对照
    cross_image_comparison.json 第二组解码图像差异
    cross_images/             原生及旧链路解码样图
    final_verification.json   旧源码、根USD、进程与追踪文件校验
```

对应云端输出目录：

```text
wave_rt_20261012_023325
wave_pt_20261012_023923
wave_control_20261012_025436
reference_20261012_025546
reference_native_20261012_030638
wave_trace_20261012_032227
```

完整标准MCAP仍在各云端capture的 `bag/` 或旧参考session的 `bag_unified/`。本地传回日志、样图、分析及105MB的nsys-rep；约730MB的SQLite保留云端，路径和SHA256记在final_verification.json。一次图像证据传输与分析写文件重叠，哈希检查拒绝了变化文件；失败partial保留，分析结束后重新传输验证，不影响采集包。

原生包核心24个话题：

```text
/clock                           rosgraph_msgs/Clock
/tf                              tf2_msgs/TFMessage，world → swing_coordinate → 17路传感器坐标
/joint_states                    sensor_msgs/JointState
/lidar/<id>/points                13路PointCloud2，XYZ float32，传感器局部坐标
/camera/fisheye_<方向>/image_raw  4路Image，rgb8，1920×1080
/camera/fisheye_<方向>/camera_info 4路CameraInfo，鱼眼标定
```

原生参考6组每路有11条图像/点云消息，存在重复时间戳；初始化的clock/TF/JointState也可能在包内。有效组以外部 `groups.jsonl` 的原生时间戳与严格核验结果识别，不把包内每条消息都算成一个采集组。每轮原生MCAP约348MB。旧包为PNG CompressedImage，另有root/camera pose、frame_index、metadata及水平TF；两个包的组织与数量并不相同。

## 12. 复现命令

先正常关闭正在运行的Isaac GUI，避免另一个Kit争抢GPU。无需安装新依赖。

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_quality_002
python3 run.py                 # 默认Helper三组冻结验证
python3 wave.py rt             # 当前默认不改接图，45组实时预算扫描
python3 wave.py pt             # 当前默认不改接图，12组PT预算扫描
python3 wave.py trace          # 实际Nsight代表性追踪及证据验证
python3 reference_external.py  # 保留的旧链路，独立进程对照
python3 reference_native.py    # 当前默认原生，三轮各6组，无额外PNG
```

读取产出目录的 `result.json`、`validation.json`、`group_validation.json`；追踪还必须确认 `profile_capture_verified=true`。正式项目的质量配置、面板和运动控制没有被本实验替换。
