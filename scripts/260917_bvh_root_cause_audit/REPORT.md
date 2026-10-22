# Motion BVH 根因排查：远端只读审计与后续实验设计

日期：2026-09-17。此次已完成 SSH 检查、业务代码核对、历史实验复核和原生二进制静态定位；下述新实验尚未运行。

核心目标：解释原项目为何必须关闭 Motion BVH，定位触发条件、负责模块及版本边界。验收依据是因果证据，而不是仅让点云恢复输出。

## 1. 本次实际检查

- 远端：root@120.209.70.195:30162；已连接成功。
- 实际部署项目：/root/gpufree-data/semantic/scripts/260907LidarVisualizer。
- Isaac Sim：6.0.1-rc.7+release.42383.32955d8d.gl。
- Kit：此前运行日志记录 110.1.2+production.326809.f9bf0dda.gl；本次扩展包构建标识同为 f9bf0dda。
- GPU：NVIDIA L40，驱动 580.126.09；检查时显存约 668 MiB。
- 检查时没有可执行文件位于 /root/isaacsim/ 下的运行进程，因此没有“当前已打开场景”的运行态证据。场景判断来自磁盘文件与已有实验记录。
- 相对前一轮基线，93 个既有 USDA 全部存在且 SHA-256 未变化。本次未启动 Isaac、未写远端文件，未修改业务代码、配置和场景。

## 2. 已找到的三层证据

### 2.1 业务代码主动限制了三个开关

launch_isaac.py 第 31–32 行默认一起关闭：

- /renderer/raytracingMotion/enabled
- /rtx/hydra/supportMultiTickRate
- /rtx/rendering/perSensorTickTlas

runtime.py 第 92–97 行在 robot_motion.enabled=true 时，只要三项任意一项开启，就主动抛出 RuntimeError。这段检查没有先验证场景内是否真的存在 Gaussian，也没有检查 instantLidar。

当前 sensors.json 中 robot_motion.enabled=true、forward_speed_m_s=0，说明“配置启用运动功能”和“物体此刻具有非零速度”也不能混为一谈。传感器和机器人由场景自动发现，不能把历史验证中的数量当作当前活动数量。

意义：项目 guard 是较宽的应用兼容策略，单凭它不能证明三个开关分别都与 Gaussian 冲突。历史独立脚本绕过该业务代码后仍能复现底层错误，故应用 guard 不是全部原因。

源码快照、行号和文件哈希保存在 source_snapshots 与 audit_data.json。DEPLOYMENT.json 中旧的文件哈希/描述不作为当前源码替代。

### 2.2 明确错误位于 RTX SceneDB 的 Gaussian TLAS 构建路径

定位到安装包：

/root/isaacsim/extscache/omni.hydra.rtx-1.0.4+f9bf0dda.lx64.r/bin/deps/librtx.scenedb.plugin.so

- SHA-256：3fc6bb790d164decaf40aa52c5c76a6401e67e210f395e40cea9ea20ac6c57f0
- ELF Build ID：c69f93567740418057f0739d469eec000d59d9fe
- 错误字符串地址/文件偏移：0x3d6b10，内容为 Gaussians do not support motion BVH。
- 同一函数引用编译时源路径 ../../../source/plugins/rtx.scenedb/PreprocessedGaussians.cpp。
- 内嵌函数签名：void rtx::scenedb::PreprocessedGaussians::buildTlas(carb::graphics::CommandList*, uint32_t, rtx::scenedb::AccelStructMode, bool) const。

反汇编将字符串与实际执行分支联系起来，证据超过“库里存在一条字符串”：

1. 0x184990 为该函数入口；内嵌函数名、签名及源路径均被入口代码引用。
2. 按此 Linux x86-64 调用约定，AccelStructMode 参数从 ecx 保存到 r15d。
3. 0x184a35 检查该参数；为零时进入后续构建路径。
4. 参数非零时进入错误路径。日志允许输出时，0x184e2e 加载上述错误字符串，并带入源路径与 buildTlas 标签。
5. 0x184e5b 跳向函数退出路径；即使日志等级抑制输出，也直接走同一退出路径，没有继续构建。

用于理解的伪代码如下；它是控制流还原，不是 NVIDIA 源码：

    buildTlas(..., AccelStructMode mode, bool flag):
        if mode != 0:
            log_if_enabled("Gaussians do not support motion BVH")
            return
        if flag:
            log_if_enabled("Gaussians do not support refit")
            return
        ... 后续 Gaussian TLAS 构建 ...

非零枚举的完整名称映射、上游选择该模式的路径尚未恢复。最后 bool 参数的含义由对应错误文本推断为 refit 相关；它不等同于已经证明项目会触发 refit 错误。

这个检查针对加速结构模式，并不在此分支检查 NZ3、Instant、点云话题或 Gaussian 当前速度。因此，静态 Gaussian 也可能在请求此种构建模式时失败；历史实验已有静态 Gaussian 报错证据。

TLAS 是组织几何实例、供射线查询使用的一层加速结构。这里是 Gaussian 专用 TLAS 路径，不能从名称推断它就是整个场景唯一的顶层 BVH。

### 2.3 传感器层另有独立约束

在同一安装中检查了以下库：

| 库 | 检查结果 |
|---|---|
| librtx.scenedb.plugin.so | 找到 Gaussian/Motion BVH 明确拒绝分支 |
| librtx.rtxsensor.plugin.so | 未找到该 Gaussian 错误；另有“Multi-tick enabled but motion BVH not active”不支持提示 |
| librtx.sensors.lidar.core.plugin.so | 未找到该 Gaussian 错误；存在启用 Motion BVH 的提示 |
| librtx.hydra.so | 未找到该 Gaussian 错误；有 Gaussian 几何流送相关代码文本 |

“未找到字符串”只用于定位该条诊断文本，不能据此证明其他库完全没有 Gaussian 逻辑或缺陷。应用同时关闭三项，很可能也在避免多 tick 依赖 Motion BVH 所带来的第二种不支持组合；其具体运行条件仍要逐项验证。

模块关系可概括为：USD ParticleField 经 Hydra 接入 RTX SceneDB；SceneDB 构建几何加速结构；相机/RTX Sensor 渲染路径请求和消费这些场景数据；LiDAR 模型生成测量，之后才进入点云输出和 ROS。

当前证据直接定位的是 SceneDB 的 Gaussian 构建限制。LiDAR 可能是触发这种模式的调用方，其触发范围尚需运行时对照。

## 3. 对此前结果的重新归类

| 证据 | 已支持的判断 | 未支持的判断 |
|---|---|---|
| mesh_on_multi 成功 | Motion BVH、传感器与基础 Mesh 在此环境可工作 | 所有功能、所有资产均正常 |
| gs_on_multi_rgb 报错且只剩 Mesh 墙回波 | Gaussian 在该组合中未正常进入最终测量 | 相机单独运行一定失败 |
| gs_on_single_v2 在 multi/perSensor 都关闭时仍报错 | 关闭另外两项不足以消除该 Gaussian 冲突 | 另外两项在全部场景中都无影响 |
| hidden/inactive Gaussian 后错误消失 | Gaussian 是否参与渲染场景与错误强相关 | Gaussian 永远不能支持 Motion BVH |
| 本次函数参数检查与提前返回 | 当前二进制具有显式未支持路径 | 未实现的原因一定是数学困难或硬件不支持 |
| 全场景 Stop/Play 曾崩溃 | 该组合还存在生命周期稳定性问题 | 已确定崩溃就是上述 return 的直接后果 |

全场景崩溃与 Gaussian 回波消失需分别归因。时间错位、点云 deskew、GS/Mesh 测距差异属于其他问题，暂不作为本轮主变量。

远端 NZ3 原始配置已只读核实：instantLidar=1，SOLID_STATE，46,080 个发射器，fireTimeNs 共 46,080 项且全为 0，SENSOR/NONCOMPENSATED。它说明发射时间模式，不代表 SceneDB 会自动避免请求 Motion BVH 模式。

## 4. 下一轮实验：先回答“谁会触发”

采用独立的新入口，不导入 LidarVisualizer/runtime.py。第一轮复用之前已确认能正常显示/测到的最小 Gaussian 资产，避免从未验证的新合成资产引入额外问题。

固定单 GPU、固定相同渲染后端、固定场景和相机姿态、静态几何、关闭测量噪声。multiTick=false、perSensorTickTlas=false。每个条件独立冷启动；唯一主动切换变量是 Motion BVH。

| 顺序 | 几何 | 活动输出 | Motion BVH | 目的 |
|---|---|---|---|---|
| A1/A2 | 纯 Mesh | 仅相机 | OFF / ON | 验证相机侧控制实验 |
| A3/A4 | 同一 Gaussian + Mesh 参照物 | 仅相机 | OFF / ON | 判断去掉 LiDAR 后是否仍触发 |
| B1/B2 | 纯 Mesh | 仅一个 LiDAR | OFF / ON | 验证独立传感器控制实验 |
| B3/B4 | 同一 Gaussian + Mesh 参照物 | 仅一个 LiDAR | OFF / ON | 判断独立 LiDAR 是否触发 |
| C1/C2（条件执行） | 相同 Gaussian 场景 | 相机 + LiDAR | OFF / ON | 当独立运行与已有结果不一致时，验证共存因素 |

“仅相机”必须没有活动 OmniLidar、雷达 RenderProduct 和雷达 annotator；不能只是隐藏雷达图标或停止 ROS 发布。“仅雷达”必须检查无额外 RGB RenderProduct 和活动视口。扩展已加载和传感器正在工作是不同事实，二者都记录。

全局设置为 true 不足以证明某个 Hydra engine 实际请求了 Motion BVH。每次都记录生效设置、engine 信息（若可取得）、RenderProduct 绑定和原生诊断。若相机没有报错但无法证明它进入 Motion BVH 构建模式，只能得出“该相机配置未触发”，不能得出“Gaussian 的 Motion BVH 已受支持”。

必要时增加具有已知运动的 Mesh 相机控制、明确 shutter/渲染模式，并进一步采集构建模式。相机的后处理运动模糊不能替代原生 Motion BVH 生效证据。

判定逻辑：

- 相机独立也报同一错误：该限制在此相机配置下不依赖 LiDAR。
- 相机正常、LiDAR 独立失败：重点追踪传感器渲染路径选择的 SceneDB 模式，以及相机究竟使用了什么模式。
- 两者独立正常、同时运行失败：重点查 engine/SceneDB 上下文共享、masking 与多输出配置。
- 所有新最小场景正常：与旧 probe 快照逐项比较，检查资产表示、隐含 RenderProduct 和开关生效差异；不能直接宣告旧错误已修复。

## 5. 触发路径确认后，继续缩小原因

按次序执行，每一层只处理一个问题：

1. **拆开三个设置。** 在已复现的输出路径上，从 Motion=1、multi=0、perSensor=0 出发，单独改变 multi 和 perSensor，再检查共同开启。每种配置先跑纯 Mesh，排除本来就不支持的配置。不要把三项同时切换的结果全归因于 Motion BVH。
2. **隔离 Instant。** 保持同一传感器、同一发射数组、同一场景，只切 instantLidar。用远端原始 NZ3 配置的只读引用加新层 override。记录场景最终组成值，不只看资产文件中的 authored 值。检查相同 SceneDB 错误及 Gaussian 返回是否仍存在，不以 P95 畸变为主要指标。
3. **隔离资产表示。** 在已知可工作的 Gaussian 基线之后，增加一个或少量、属性完整的原生 ParticleField3DGaussianSplat，再与真实资产对照；分别测试静态和仅刚体变换。每个资产必须先通过 Motion OFF 可见/可测基线。
4. **追踪上游参数。** 若 API/日志无法说明模式来源，针对独立最小进程采集 buildTlas 的 mode 与调用栈、调用模块和偏移。当前未找到 gdb；此步骤尚不具备现成运行环境。保留二进制哈希和映射基址，不能把剥离符号后 objdump 的“最近导出符号+大偏移”误认为真实函数名。
5. **核对版本边界。** 完整固定最小复现包，在另一个完整、受支持的 Isaac/Kit 安装上做相同实验；保留旧安装。不要只替换一个 SceneDB .so，避免 ABI/依赖不匹配。公开发布说明需与实测构建对应。
6. **最后检查全场景生命周期。** 只有最小条件清楚后，才复验 Stop/Play，采集首次错误时刻、退出阶段和 GPU dump，单独解释崩溃链。

## 6. 记录与验收

每组记录：启动参数与生效 Carb 设置；组件版本/hash；组成后的 prim 类型与 schema；活动传感器和 RenderProduct；Gaussian 数量及可见性；首次错误；RGB 中 Gaussian 是否可见；雷达目标区间返回、Mesh 控制返回、点数及时间戳；进程退出结果。

优先采用可靠对象标识；若 Gaussian 不提供可用 ObjectId，则使用空间隔离的 Gaussian 靶区和更远 Mesh 背板，对目标区间作对照。不能以“点云非空”作为成功标准，也不把 Gaussian 统计形状的中心距离冒充真实表面距离。

使用新根层/会话层及新实验目录。所有被引用的既有层设置禁止编辑与保存，EditTarget 固定到新层；每轮核验原 USDA 哈希。若创建 annotator 需要写 RenderVar，在新层先定义，不解除源层保护。监督器一次只启动一个 GPU 测试进程，超时只终止其自身进程组。

根因验收需要能够回答：

- 触发来自哪条活动渲染路径，实际请求什么构建模式？
- 对所有该类型 Gaussian 都发生，还是特定资产条件才发生？
- Instant 与另外两个设置是否改变触发条件？
- 限制存在于哪些已实际验证的构建版本？
- Gaussian 数据遗漏与崩溃分别在哪一步发生？

当前已将定位推进到“本机 SceneDB 的 Gaussian TLAS 构建函数存在显式拒绝并提前返回”。关于 NVIDIA 为何尚未实现该模式，例如时间变换、嵌套加速结构、refit、资源生命周期或其他约束，现有证据不能作唯一归因；需要更完整实现信息、调用栈或厂商确认。

## 7. 官方文档边界

官方 [LiDAR 文档](https://docs.omniverse.nvidia.com/kit/docs/omni.sensors.nv.lidar/latest/lidar_extension.html) 将 Motion BVH 的时间相关射线追踪支持与输出坐标 deskew 分开；修改输出补偿无法补上没有完成的 Gaussian 几何构建。

官方 [RTX 110.1 发布说明](https://docs.omniverse.nvidia.com/materials-and-rendering/latest/rtx-renderer_release_notes.html) 描述原生 ParticleField 渲染与相机 motion blur 能力。它未在该说明中明确保证本机这一具体预发布构建的所有 LiDAR/Motion BVH 组合。相机可实现某种 motion blur，也不能自动证明这里的非零 AccelStructMode 构建路径已实现。

文件：

- audit_data.json：当前源码快照、哈希、远端 NZ3 属性、既有 USDA 校验和历史 case 诊断。
- native_evidence.txt：安装库哈希、ELF Build ID、字符串与关键反汇编。
- source_snapshots：业务代码只读快照。runtime 为带原始行号的节选。
- test_matrix.json：第一轮待运行对照矩阵。

