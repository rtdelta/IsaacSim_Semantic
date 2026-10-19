# Gaussian / Motion BVH 根因实验报告

日期：2026-09-17。远端完成时间：09:06 UTC（北京时间 17:06）。结论限定于本次安装与已验证的渲染路径。

**结论**

当前 Isaac Sim 6.0.1-rc.7 / Kit 110.1.2 中，Gaussian 专用加速结构的构建实现不能处理本次 Motion BVH 路径传入的模式。相机和 LiDAR 都能触发，静态 Gaussian 也能触发，NZ3 Instant 不能避免该冲突。

本次将证据从“存在错误字符串”推进到：独立输出对照、实际 Hydra 引擎标志、原生函数参数、原生调用栈，以及构建任务的参数传递代码。

## 1. 文件保护与运行范围

远端实验目录：

/root/gpufree-data/diagnostics/bvh_causality_20260917_083739

所有新脚本、场景覆盖、日志、数据、调试器和运行缓存均放在该新目录。未修改原业务入口、配置、场景或供应商动态库。引用层在进程中禁止编辑与保存，场景 EditTarget 指向新根层；渲染所需 RenderVar 也定义在新层。

建立并最终核验了 1,088 个既有文件的 SHA-256，包括前一轮的 93 个 USDA、项目脚本与配置、相关历史文件和本次引用的 Gaussian 资产：

- checked=1088
- changed=[]
- missing=[]

SceneDB 动态库 SHA-256 仍为 3fc6bb790d164decaf40aa52c5c76a6401e67e210f395e40cea9ea20ac6c57f0，与审计阶段相同。

所有本轮 Isaac 实验进程均已结束；最终显存 668 MiB。没有发现仍运行的 /root/isaacsim/ 下进程。

## 2. 环境与实验统计

- Isaac Sim：6.0.1-rc.7+release.42383.32955d8d.gl。
- Kit：110.1.2+production.326809.f9bf0dda.gl。
- GPU：NVIDIA L40；驱动 580.126.09。
- 主体渲染模式：RealTimePathTracing。
- 场景与传感器均静止；没有运行机器人运动脚本或 ROS 发布器。
- 每个 case 独立冷启动，记录启动参数与生效设置、活动 RenderProduct、OmniLidar、视口和 Hydra 引擎。
- 第一轮测量前预热 60 帧，测量 180 帧；后续大部分预热 60 帧、测量 120 帧。调试 OFF 基线预热 30 帧、测量 60 帧。配对与复测的条件见各 manifest/args。
- 42 个 case 目录中，34 个产出了结果数据；其中 1 个是低照明的准备性 Mesh 相机测试。其余 33 次属于正式对照和原生诊断。数据产出并不等于 Gaussian 兼容通过；下文明确排除未通过 Gaussian 返回基线的判断。

所有尝试均保留。8 个未完成有效采集的准备性尝试主要涉及：移除视口也移除了引擎、空缓存编译超时，以及编排脚本 queue.py 与 Python 标准库同名造成的扩展导入失败。后续版本通过独立创建引擎、将既有缓存只读复制到新目录、从 worker 导入路径排除编排目录解决。没有将这些准备失败计为 Gaussian/Motion BVH 证据。

最终可复用 worker 是 probe_v5.py；前一轮八组对照使用 probe_v3.py，在产生导入命名冲突之前完成。每个 case 都保留实际 worker 快照。

## 3. 八组独立对照

固定 multi-tick=false、perSensorTickTlas=false。Gaussian 为原项目使用的真实牙齿资产；Mesh 参照是距传感器各坐标轴方向 10 m 的室内壁面。相机使用同一固定视角。诊断 LiDAR 为 8 通道旋转配置，每圈最多 800 个返回。

| 几何 | 活动输出 | Motion OFF | Motion ON |
|---|---|---|---|
| Mesh | 仅相机 | 正常图像，无 Gaussian 错误 | 正常图像，无 Gaussian 错误 |
| Gaussian + Mesh | 仅相机 | Gaussian 可见 | Gaussian 消失，出现原生不支持错误 |
| Mesh | 仅 LiDAR | Mesh 返回正常 | Mesh 返回正常 |
| Gaussian + Mesh | 仅 LiDAR | 每扫描有 10–16 个近处返回 | 近处返回为 0，仅剩 Mesh 返回，并报同一错误 |

相机条件：0 个活动 OmniLidar、1 个相机 RenderProduct、0 个活动视口。LiDAR 条件：1 个 OmniLidar、1 个 LiDAR RenderProduct、0 个活动视口。最终组成检查全部通过。

创建标志也随之变化：

- OFF：EngineCreationFlags.NONE，数值 0。
- ON：EngineCreationFlags.MOTION_RAYTRACING_ENABLED，数值 1。

因此，这些 ON 条件不是仅设置全局键而未启用引擎运动追踪。基础经验文件仍加载了部分传感器扩展/动态库；“相机独立”指无活动 LiDAR 渲染请求，不能表述成“没有加载任何 LiDAR 代码”。原生调用栈也没有显示 LiDAR 测量模型作为该构建函数的直接上游。

相机图像：

![相机独立对照](camera_only_comparison_v2.png)

“LiDAR 仍输出 800 点”不等于成功：Gaussian 缺失后，原本可能命中它的射线到达更远的 Mesh 壁面，完整点云可以继续产生。

## 4. 原生调用参数和调用栈

使用解压在新实验目录中的 GDB，观察现有库中的函数入口；没有修改磁盘上的供应商二进制，也没有改变函数参数、返回值或执行分支。

目标：

rtx::scenedb::PreprocessedGaussians::buildTlas(CommandList*, uint32_t, AccelStructMode, bool) const

| 调试 case | 引擎标志 | 实际 AccelStructMode | bool 参数 | 输出 |
|---|---:|---:|---:|---|
| debug_camera_gaussian_off | 0 | 0 | 0 | Gaussian 可见 |
| debug_camera_gaussian_on_r1 | 1 | 1 | 0 | 报错、Gaussian 消失 |
| debug_lidar_gaussian_on_r1 | 1 | 1 | 0 | 报错、Gaussian 近处返回消失 |

目前使用模式数值表达观测，没有将尚未取得完整定义的内部枚举名称当作已知源码。

三条栈均经过以下模块路径；这里按照调用发生方向列出：

libomni.usd.so → librtx.hydra.so → libcarb.scenerenderer-rtx.plugin.so → libgpu.foundation.plugin.so → librtx.scenedb.plugin.so → PreprocessedGaussians::buildTlas

调用点的 SceneDB 相对地址相同：0x1eba39，返回地址 0x1eba3e。Gaussian 构建函数入口为 0x184990。完整栈与动态库加载基址保存在对应 case 的 native_trace.jsonl。

由于发布库缺少完整调试符号，栈中的部分函数显示为 ??。报告只使用已证实的模块、偏移和函数内嵌标识，不把相邻导出符号误认为实际函数名。

## 5. 更深一层：模式如何传给 Gaussian

补充反汇编定位到一个构建任务，其名称由代码构造为：

SceneDb: Build Gaussian bvh

观察到的参数传递是：

1. 任务注册时将模式写入任务对象 +0x8c（0x1f6530）。
2. 回调 0x1eb9e0 遍历任务持有的 Gaussian 列表。
3. 每次从同一个任务对象 +0x8c 读取模式到 ecx（0x1eba23）。
4. 调用 Gaussian 的 buildTlas（0x1eba39）。
5. buildTlas 检查模式；模式非零时走不支持错误和退出路径；模式为零才继续后续构建。

用于理解的伪代码如下，不是 NVIDIA 源码：

    task.mode = requested_scene_acceleration_mode
    for gaussian in task.gaussians:
        gaussian.buildTlas(command_list, device, task.mode, false)

    Gaussian.buildTlas(..., mode, ...):
        if mode != 0:
            log_if_enabled("Gaussians do not support motion BVH")
            return
        ... 普通模式的 Gaussian 构建 ...

这解释了两个此前容易混淆的事实：

- **Gaussian 静止仍会失败。** 此调用路径把任务的模式传给 Gaussian；它不会因为本次对象速度为零就自动传入普通模式。实验中无运动也已触发。
- **Instant 仍可能失败。** 发射时序和这里的场景加速结构模式是不同输入。Instant 没有使本次引擎和 SceneDB 构建任务自动切回模式 0。

这些证据说明本构建存在实现能力与所请求模式不匹配。至于 NVIDIA 为何尚未支持该分支，是资源布局、运动实例支持、更新方式或其他设计取舍，仍不能从这个 return 唯一推断。尤其不能据此声称 Gaussian 在数学上无法支持运动射线追踪，或 GPU 普遍不支持。

## 6. NZ3 Instant 与最小 Gaussian

**NZ3 Instant**

使用远端原始 NZ3 扫描配置的只读引用，保留 46,080 个发射器、全零 fireTimeNs，开启 instantLidar；在新层固定无测距噪声、SENSOR/NONCOMPENSATED 等诊断条件。

| 条件 | 完整输出样本 | 近处 Gaussian 返回 / 样本 | 错误 |
|---|---:|---:|---|
| Gaussian、Motion OFF | 120 | 658–715 | 无 Gaussian/Motion BVH 错误 |
| Gaussian、Motion ON | 120 | 0 | 相同不支持错误 |
| Mesh、Motion OFF/ON | 各 120 | 0（场景中本来没有近处靶标） | 均无 Gaussian 错误 |

因此，对于这台机器上这个包含 Gaussian 的 NZ3 Instant 场景，开关 Motion BVH 确实改变最终点云的场景内容。

只将同一 NZ3 配置的 Instant 改为 false 时，本轮 OFF 条件每份输出只含 1 点，且无 Gaussian 近处返回。这个条件没有通过 Gaussian 测量基线，不能用它证明“定时模式的 Gaussian 回波被 Motion BVH 删除”，也不能比较其扫描精度。它的配置/输出语义需另行排查。Instant=true 的正反对照有独立的完整基线，不依赖该条件。

**单个原生 Gaussian**

新建一个仅含 1 个 Gaussian 的 ParticleField3DGaussianSplat，位置 (4,0,0)，尺度 (0.5,0.5,0.5)，不透明度 0.99，SH degree=0，属性按已安装 schema 写入。

相机 OFF 时能看到该 Gaussian，ON 时消失并触发同一错误。因此复现不需要真实资产中的大量 Gaussian、复杂机器人或完整项目场景。

该合成 Gaussian 在本轮旋转 LiDAR 的 OFF 条件下未产生近处返回，故只把其相机对照用于证明最小资产也受影响；没有把合成 LiDAR 条件作为回波丢失的有效对照。

## 7. 为什么项目一起关闭三个开关

对三项进行了独立组合检查，并为新增组合提供 Mesh 控制：

| Motion | multi-tick | per-sensor TLAS | Gaussian / 传感器表现 |
|---:|---:|---:|---|
| 1 | 0 | 0 | Gaussian 不支持错误，输出缺失 |
| 1 | 1 | 0 | 相同错误 |
| 1 | 0 | 1 | 相同错误 |
| 1 | 1 | 1 | 相同错误 |
| 0 | 0 | 0 | Gaussian 返回保留；有 Motion BVH 未启用提示 |
| 0 | 1 | 0 | Gaussian 返回保留；额外警告 multi-tick 与未启用 Motion BVH 的组合不受支持 |
| 0 | 0 | 1 | Gaussian 返回保留；未观察到 per-sensor 独立导致的 Gaussian 错误 |
| 0 | 1 | 1 | Gaussian 返回保留；相同 multi-tick 不支持警告 |

因此，当前 Gaussian 冲突直接涉及 Motion BVH。关闭它后，multi-tick 又触发传感器层的另一项约束。per-sensor TLAS 在本轮没有被证明是独立的必关项；原项目把三项一起拦截，是范围更宽的兼容配置策略。

本轮这些设置组合的已附着引擎仍显示 tickrate_in_hz=0。它们验证了设置组合与错误的关系，不代表已验收按各传感器频率创建独立引擎和独立 TLAS 的完整多 tick 工作流。

未据此改动或放宽原业务 guard。

## 8. 已完成与尚未覆盖

本轮已完成：

- 主体八组独立路径对照。
- 原生参数与调用栈对照。
- NZ3 Instant 正反对照。
- 单个 Gaussian 相机对照。
- 三个设置的组合检查及 Mesh 控制。
- 原文件最终哈希核验和进程清理确认。

未在本轮完成：

- 跨完整 Isaac/Kit 构建比较：本机只发现一个完整 Isaac 安装，未下载或替换它。
- 全项目重新启用 Motion BVH 的端到端运行及 Stop/Play 崩溃归因：此前已有全场景错误/崩溃记录，本轮专注最小触发链，没有用重复崩溃代替机制定位。
- 上述 NZ3 非 Instant 单点输出、单 Gaussian 未产生 LiDAR 返回的独立原因。
- 厂商内部为何尚未实现该构建模式的设计原因。

后续最有价值的工作是将本轮最小复现与 native_chain.json 在另一个完整构建中原样验证，或用于取得该实现分支的正式支持说明。当前结论已经能解释本项目这台安装上为什么需要关闭 Motion BVH，但不能推断所有版本的能力。

## 9. 复现与证据

在远端新实验目录执行，case 名称必须未使用：

    python3 runner_seed.py new_camera_off --script probe_v5.py --geometry gaussian --output camera --bvh 0
    python3 runner_seed.py new_camera_on --script probe_v5.py --geometry gaussian --output camera --bvh 1
    python3 runner_seed.py new_nz3_off --script probe_v5.py --geometry gaussian --output lidar --native-nz3 --instant 1 --bvh 0
    python3 runner_seed.py new_nz3_on --script probe_v5.py --geometry gaussian --output lidar --native-nz3 --instant 1 --bvh 1

原生跟踪：

    python3 runner_debug.py new_native_trace --script probe_v5.py --geometry gaussian --output camera --bvh 1 --timeout 240

关键文件：

- summary_final.json：所有 case 的状态、引擎、错误和测量摘要。
- CASE_INDEX.md：每次尝试的分类索引。
- evidence.tar.gz / evidence：脚本、原始日志、结果、图像、点云、原生调用栈与保护清单。
- native_chain.json：动态库哈希、节点名称和关键相对地址。
- native_caller_disassembly.txt、native_caller_registration.txt：调用与任务注册代码证据。
- protected_before.json、verification_*.json：既有文件的前后校验。
- final_environment.json：结束时间、GPU 与进程状态。
- camera_only_comparison_v2.png / .pdf：独立相机对照图。

官方 [HydraEngineCreationConfig](https://docs.omniverse.nvidia.com/kit/docs/omni.usd/latest/omni.usd/omni.usd.HydraEngineCreationConfig.html) 和 [EngineCreationFlags](https://docs.omniverse.nvidia.com/kit/docs/omni.usd/latest/omni.usd/omni.usd.EngineCreationFlags.html) 说明可查询的引擎配置；本次同时核对了已安装 Python 接口定义与运行时返回。

[RTX Particle Fields 文档](https://docs.omniverse.nvidia.com/materials-and-rendering/latest/particle-fields.html) 描述原生 Gaussian 渲染及相机 motion blur 能力。不能用这项概述替代对当前具体构建、具体加速结构模式与传感器路径的验证。

