# 2026-10-14 连续主路线实施与机制诊断报告

后续同日已完成实际状态配对及独立房间三重复实验，新增原始 GMO 与射线距离证据，见[连续与冻结配对实验及机制排查结果](../Experiments/002_连续与冻结采集_配对实验与机制排查结果_20261014.md)。下文保留此前阶段的采样规模与结论，不与后续统计混为同一轮。

本次按[004方案](../ImpPlan/004_single0601ContinuousRt_连续主路线修复与流水线实现方案.md)实施原生事件观测、状态追踪和最小几何诊断，并部署到已有单卡L40实例。连续修复门槛仍未通过：低速旋转时既有原生位姿错误，也有独立几何测出的实际射线错误。因此未进入C3正式连续录制及C4至C6，未生成新的连续MCAP或READY。

本报告补充[2026-10-13执行报告](20261013_execution.md)，不改写已发布数据和原001至003契约。完整实际结果见[机器可读汇总](../../reports/continuous_recovery_result.json)。

## 1 运行范围与阶段状态

| 阶段 | 本次结果 | 尚缺内容 |
|---|---|---|
| C0 | 冻结实际源码、SDK、场景、READY清单和诊断预算 | 正式worker/VRAM预算及长测预算尚未锁定 |
| C1 | 已实现原生GMO、自有字节、阶段状态和独立头解码 | 公开历史读取接口未取得；原生单时刻语义未证明 |
| C2 | 完成有依据的最小对照，收敛当前运行时复现材料 | 无通过验证的修复；完整重复/非匀速/全模型矩阵未完成 |
| C3 | 未进入 | 单组连续正式MCAP及独立回读 |
| C4 | 未进入 | 多ticket、分阶段credit、IPC2、异步编码/顺序提交 |
| C5 | 未进入 | Reset、安装revision、原生焦点、strict_latest/gap验收 |
| C6 | 未进入 | 六轮基线对照、场景质量及30分钟全组合长测 |

目标保持单卡实例`isaac-new`、SSH端口30729、现有`/root/isaacsim`和ROS2 Jazzy。实际版本为`6.0.1-rc.7+release.42383.32955d8d.gl`、Replicator1.13.27、sensor common3.0.0。所有GPU试验均使用完整GUI经验、`:20`显示器和单个自有Kit进程。

源码只部署到本项目，覆盖前由既有部署工具备份至项目`.deploy_backups/<audit_id>`。没有安装依赖、下载新SDK、修改已安装SDK或旧v06源码。原生几何房间、噪声覆盖和渲染rig均位于自有匿名Session层。

## 2 实际实现

| 文件/模块 | 实际行为 |
|---|---|
| `native_event.py` | 同一Writer事件取得GMO；复制有界CPU字节，再用另一副本交给已安装解析器；保留frameId、时间、起止位姿、坐标系、motion状态和点offset摘要 |
| `native_header.py` | 按已安装packed v1.0.0头布局独立解码264字节；检查尺寸、版本和有限值，不追随指针；逐字段交叉校验SDK解析结果 |
| `state_trace.py` | 在物理POST和app update后读取USD与Fabric当前世界矩阵、可用分量及外部物理时间；不刷新Fabric缓存、不创建变换属性 |
| `native_probe_owner.py` | 原始MyAiry传感器的纯USD最小场景，已知六面非对称房间；60/60Hz真实物理/loop时钟，10Hz原生tick |
| `render_pose_rig.py` | 实际POST世界矩阵驱动的实验渲染rig；保持原始安装路径作为实际状态来源，并检查传感器属性摘要一致 |
| `probe_native_events.py` | 有界诊断，最多40个有效事件/路、128MiB追踪；保存全部XYZ、全部GMO头、固定首/中/末完整GMO及RGB；不发正式ticket或READY |
| `analyze_native_events.py` | 无SDK离线解码字节头、验证hash、统计时间差和原生/实际位姿差 |
| `analyze_room_geometry.py` | 完整自有XYZ对已知六面几何的P95；另以真实上一物理步作负对照 |
| `analyze_room_rotation.py` | 固定50mm平面归属歧义排除规则，独立拟合水平射线旋转残差；只用于诊断，不改变点云、位姿或时间 |
| `summarize_recovery.py` | 校验回传证据manifest逐文件大小/hash，并汇总实际运行与未验收阶段 |

rig仅为失败的实验候选。五种正式配置仍保持原有默认安装路径、1920×1080、无损PNG、Instant与scan参数，现有连续能力门禁仍有效。

发现并修正一项诊断实现问题：安装的`getModelOutputFromBuffer`会在输入buffer中重定位指针字段。前两轮的三个完整GMO样本因此与解析前hash不符，原始错误记录保留。现在对第二份自有字节进行解析，原始保留packet不再被修改；后续各完成轮的packet/头摘要校验通过，独立头解码与元数据逐字段一致。

## 3 实际对照结果

下表时间为本地Asia/Shanghai，run目录均位于远端项目`reports/continuous_recovery/`。`diagnostic_completed`仅表示诊断采样完成，不表示连续能力通过。

| run目录后缀 | 场景/唯一对照 | 有效目标 | 原生位姿超限 | 实际XYZ最大组P95 |
|---|---|---:|---:|---:|
| `104509_mixed` | 首次scene18观测 | 未完成 | 未汇总 | 无独立房间检验 |
| `104858_mixed` | scene18默认 | 40/路 | LiDAR 12/40；相机0/40 | 未检验scene18连续几何 |
| `105624_mixed` | scene18零延迟设置 | 40/路 | LiDAR 12/40；相机0/40 | 未检验scene18连续几何 |
| `110016_static` | 房间静止 | 40 | 0/40 | 0.001431 mm |
| `110246_rotation` | 房间10°/s纯旋转 | 40 | 0/40 | 0.735620 mm |
| `111016_mixed` | scene18实际驱动rig | 40/路 | LiDAR 12/40；相机0/40 | 未检验scene18连续几何 |
| `111558_mixed` | 房间0.3m/s、3°/s | 40 | 12/40 | 5.937871 mm，失败 |
| `113855_mixed` | 同上，增加Fabric分量纯读 | 40 | 12/40 | 5.937871 mm，失败 |
| `114132_mixed` | 运行中关闭Motion BVH | 0 | 超时，无有效对照 | 未取得点云 |
| `114712_mixed` | 启动时关闭Motion BVH | 40 | 39/40 | 8.449152 mm，失败 |
| `115026_mixed` | Motion BVH保留，改每帧TLAS | 40 | 12/40 | 5.937871 mm，失败 |
| `115233_translation` | 房间1m/s纯平移 | 40 | 0/40 | 0.001907 mm |

共10轮诊断采样完成、2轮明确失败；完成轮共520条有效receipt。这些不是正式采集组。所有已结束轮的自有产品、Writer、物理回调、输入、Session层和设置恢复检查均通过。

首次失败为128MiB追踪容量耗尽，保留了10条相机与11条LiDAR证据；之后固定完整GMO/RGB的采样索引，全部XYZ和全部头仍保留。`114132`轮初始化阶段输出过Hydra配置警告，最终进入有效运行阶段但没有有效事件，120秒采样超时后自行清理退出。随后停止请求的归属检查发现PID已结束，未发送信号。其失败不能当作运动几何结果。

## 4 已证实的机制边界

### 4.1 当前变换正确不能证明历史射线正确

低速最小房间两次独立初始化得到相同超限分布。Fabric当前世界矩阵与USD实际读回矩阵在所观测物理POST和app后阶段完全一致；独立属性读取发现该最小传感器没有`_worldOrientation/_worldPosition`值，实际存在的是`omni:fabric:worldMatrix`。没有取得公开渲染历史读取接口，因此不能宣称历史变换也正确。

同样的低速运动在无关节机器人、无父链复杂度的纯USD传感器中仍复现。因此此前高转速对照通过只能说明该用例通过，不能把失败仅归因于机器人安装层级；R4 rig也未解决原scene18的旋转问题。

### 4.2 实际射线与元数据都需要验收

`113855_mixed`完整XYZ已回传本地并独立复算。原生位姿有12/40条旋转超限，最大约`8.726809e-4 rad`，对应3°/s时的一个60Hz物理步约0.05°。独立六面检验的最大组P95为5.937871mm，超过5mm阈值。

独立水平面拟合进一步测得39/40组射线旋转残差超过`1e-4 rad`，多数接近落后半步0.025°或一步0.05°。例如物理步18约落后0.05°，步24约落后0.025°；步60的元数据看似对齐，但实际射线仍约落后0.05°。拟合后水平平面P95最大约2.34微米，这支持旋转残差的诊断，但不是对正式数据进行纠正的授权，也不证明所有方向、模型或噪声条件。

不能用actual历史矩阵覆盖错误原生矩阵后宣称修复。也不能仅凭元数据通过推断实际射线满足同步要求。

### 4.3 原生时间字段保留其真实含义

完成轮观测到GMO主timestamp相对ReferenceTime映射物理时间约早100ms，frameStart约早16.666667ms，frameEnd相差0至1ns；Instant逐点offset均为0。该输出标记SENSOR、NONCOMPENSATED。

这些原生字段未被平移或重新命名为已验证源时间。正式源时间仍来自同事件ReferenceTime及IsaacReadSimulationTime的交叉映射。GMO主timestamp的锚点、点offset基准及Instant单时刻语义仍未证明；本次不把frameEnd对齐作为单时刻语义通过证据。

### 4.4 候选原因与排除范围

当前优先候选是原生渲染/传感器链路的小角度变换历史插值。证据是低速纯USD复现、当前矩阵正常、射线出现半步/一步旋转残差、高速与纯平移对照行为不同。

未取得实际故障函数源码或调用级历史，因此具体SLERP阈值、舍入、GPU/CPU插值实现仍是未知。离线float32四元数点积检查也未建立简单`dot==1`判据，不能据此宣布根因。已安装core公开SLERP头有小角度线性分支，但未证明传感器内部调用它；没有修改该头或SDK二进制。

零延迟有效值为`waitIdle=true`和完成检查顺序1000，仍失败；每帧TLAS仍失败。启动时关闭Motion BVH得到更多超限，且SDK明确警告MultiTick与未激活Motion BVH的组合不支持，不能采纳为正式修复。

## 5 复现与离线校验

远端项目目录中使用已有依赖；先确认无其他Kit，再启动唯一诊断进程：

```bash
/usr/bin/python3 -B tools/start_native_probe_remote.py --scene room --profile mixed
/usr/bin/python3 -B tools/native_probe_status_remote.py
```

启动器拒绝已有Kit，不停止其他进程。完整GUI启动仍禁用registry下载、匿名遥测和crash上传。诊断入口内现在将初始化也计入120秒墙钟预算。房间明确将rangeAccuracyM从原值改为0，用于理想几何；正式scene18保留原噪声。

完成后读取实际目录并执行CPU分析：

```bash
/usr/bin/python3 -B tools/analyze_native_events.py reports/continuous_recovery/RUN_ID --report reports/continuous_recovery/RUN_ID/native_analysis.json
/usr/bin/python3 -B tools/analyze_room_geometry.py reports/continuous_recovery/RUN_ID --report reports/continuous_recovery/RUN_ID/room_geometry_analysis.json
/usr/bin/python3 -B tools/analyze_room_rotation.py reports/continuous_recovery/RUN_ID --report reports/continuous_recovery/RUN_ID/room_rotation_analysis.json
```

`--sync zero_delay`、`--motion-history off`和`--tlas frame`均是明确诊断变量。后两项只支持最小房间。不要把失败候选写入正式配置。

本地完整复现载荷见[113855房间目录](../../reports/remote/reports/continuous_recovery/native_20261014_113855_mixed/)。共有95个文件、78,452,334字节，逐文件传输SHA/大小一致；包含完整传感器参数、全部XYZ和首/中/末完整GMO。12轮元数据、原生头、配置与源码SHA集中在[证据目录](../../reports/remote/reports/recovery_delivery_evidence/)，其manifest另经本地汇总工具验证。

## 6 验证、保留与未完成项

15项纯Python契约测试通过，包含大整数、packed头布局、未知版本/截断/非有限值拒绝和不追随指针。实际SDK运行及已冻结真实字节解码独立提供证据，纯逻辑测试不替代GPU验收。五种schema4配置校验通过。[源码完整性报告](../../reports/source_integrity.json)记录所比较的实际快照时间，避免把旧保留报告当成本次检查。

本次结束的当前检查确认：旧v06源码文件未增加、删除或改变；scene18 SHA与C0一致；36份根READY及manifest与C0完全一致。本次没有重做其完整MCAP回读，1612组同步/完整性结论继续引用昨天已完成的证据。当前无Kit进程，GPU占用740MiB；没有结束无关GPU进程。

诊断追踪预算128MiB/轮，录制credit配置仍512MiB，Kit RSS诊断上限在初始化后按已测峰值两倍冻结。它们不构成worker、VRAM或30分钟运行预算验收。

暂停阶段只证明物理时钟冻结及旧映射回调被拒绝。本诊断没有收集恢复后的有效载荷验收样本，不能报告恢复首帧正确。

后续顺序保持004方案：沿R5对可复现原生问题取得支持的SDK修复入口或开展明确版本对照，重新通过原生位姿、独立射线几何、时间语义及暂停恢复门槛，才能进入C3正式连续闭环。新版本/新配置不能继承本轮或屏障路线的通过结果。随后才能实施C4流水线、C5控制生命周期和C6性能质量长测。

目前`continuous_ok=false`，完整交付仍未完成。现有屏障后备不受本次诊断代码的默认设置影响，但本次没有新生产数据用于替代主路线验收。

## 7 操作记录与参考

使用[cloud-instance-ops](C:/Users/15452/.codex/skills/cloud-instance-ops/SKILL.md)及项目已配置凭据引用、主机指纹和身份校验。每次SSH脚本、部署和回传保留本地CloudInstanceOps审计；它不是整台实例的完整网络或安全审计。部分请求在SSH banner、认证前失败，后续有界重试成功；没有为此重启或修改SSH服务。

汇总文件改用`remote_ops.py publish-report`的固定JSON文件白名单、2MiB上限、临时文件SHA校验和原子替换发布；已有文件覆盖前留备份。首次内嵌base64的发布尝试卡在本地长文本检查，远端目标确认不存在后停止了准确匹配的自有本地子进程，未关闭无关Python进程。该工具传输恢复不构成额外GPU诊断结果。

官方文档仅用于设计对照，实际结论来自上述rc7运行：

- [Multi-Tick Rendering](https://docs.isaacsim.omniverse.nvidia.com/6.0.1/sensors/isaacsim_sensors_multitick_rendering.html)：物理时间镜像、同帧顺序及perSensorTickTlas设置。
- [Lidar Extension](https://docs.omniverse.nvidia.com/kit/docs/omni.sensors.nv.lidar/latest/lidar_extension.html)：Motion BVH与输出运动补偿的作用不同，Instant提供每帧完整scan；这些描述不代替当前单时刻语义验证。
