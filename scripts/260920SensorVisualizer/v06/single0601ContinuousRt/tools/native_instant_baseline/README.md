# 005 原生 Instant LiDAR 独立基线

独立最小入口为 `run_minimal.py`，只使用原生 USD、SimulationManager、RenderingManager、Replicator、时间映射 API，以及本目录的 CPU 保存和只读元数据模块。不会导入生产 Owner、Backend、状态账本、保持/Barrier、ROS/MCAP 或在线几何分析。

`P_E` 仍运行 `tools/clock_state/run_continuous.py`。本轮专用 spec 让它使用整数局部步的绝对目标、固定两周期正常推进排空、PRE/POST 只读记录；旧实验默认行为保留。两个入口均使用一个 300×300 render product 和同顺序四个原生 annotator，后台 gzip level 1、mtime 0，保留所有原始字节。

## 入口

| 文件 | 职责 |
|---|---|
| `run_minimal.py` | 独立 Kit 采集，先拥有 XYZ/GMO 字节，后保存原生时间映射，接收回调不查历史或计算几何 |
| `io.py` | 独立 CPU 字节队列、压缩、完整 SHA 清单 |
| `runtime.py` | 两组共用只读元数据；不含运动/状态账本/几何算法 |
| `math_independent.py` | 独立 GMO 序列化区间、slab 射线、固定墙点 yaw 拟合、候选等价组 |
| `analyze_independent.py` | 离线唯一源时间关联、绝对/增量判据及旧解析器交叉核验 |
| `compare_runs.py` | E 有效配置、环境、资产、输出拓扑、初始化、实际输入与目标相位的跨组资格 |
| `coordinator.py` | 每批最多四轮，独立 Kit、原始字节预算、单 GPU 排他和 600 s 总 watchdog |
| `execute_declared.py` | 有限、串行执行整份已冻结次序；资格失败即停，主轮前生成源码锁，每批复核锁 |
| `generate_specs.py` | 创建首版 E、规则、资格及必做主轮次序；拒绝覆盖既有目录 |
| `revise_qualification_v2.py` | 记录 q01 ABI 解码边界修正，保留原数据，创建 q02 与主轮 v2 的新编号 |

## 本地数值控制

```powershell
& 'D:\Anaconda3\python.exe' -X utf8 -m unittest tools.native_instant_baseline.test_controls tools.clock_state.test_contracts -v
```

包含独立标量射线、轴向/斜向与转动符号、0/0.5/1/2 步合成控制、绝对与增量分离、不可辨识、观测不足、保存所有权和 GMO 有效结构/额外分配空间边界。

## 已实现的实例命令

远端项目根为 `/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt`，已有 `/root/isaacsim` 和 `DISPLAY=:20`。通过既有审计工具调用已审阅脚本：

```powershell
& 'D:\Anaconda3\python.exe' -X utf8 tools/remote_ops.py exec --script tools/native_instant_baseline/status_remote.py --intent read --timeout 60 --purpose '读取 005 批次状态' --name native005_status
& 'D:\Anaconda3\python.exe' -X utf8 tools/remote_ops.py exec --script tools/native_instant_baseline/start_next_remote.py --intent diagnostic --timeout 60 --purpose '启动已经锁定并满足前置资格的下一批 005 实验' --name native005_start
```

`start_next_remote.py` 只按 `run_order.json` 前进，已有失败/运行批次会阻止后续。最终 v4 次序是四个静态资格、两个旋转资格、六批交错主轮，再运行 D 的三轮资格与六轮主对照。E 的有效设置读取统一到“24 次暖机后、Timeline 正在运行”；暖机前与暂停后的快照单独保留。主轮要求配对资格和源码锁文件，几何失败本身不阻断测量合格的对照。

本轮实际由 `start_sequence_remote.py` 启动有限顺序执行器，状态写入实验根的 `sequence_status.json`。已有序列或输出目录拒绝覆盖。该序列运行时不要另外调用 `start_next_remote.py`。

D 仅将 `/rtx/scenedb/maxHistoryTransformCount` 从 64 改为本构建实测默认 8；实际有效值必须逐轮匹配 `effective_D.json`。其余补偿、10 Hz、多 tick 和输出条件保持 E。默认值来自独立探针去掉该项启动覆盖后的读回，不能把其他未验证值统称“默认”。

一轮离线分析的实际命令：

```text
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /usr/bin/python3 -B tools/native_instant_baseline/analyze_independent.py <run_directory>
```

分析输出拒绝覆盖。失败修正使用新 run_id；已有 raw、分析和终态必须保留。

## 当前构建与解释边界

原生探针核验构建为 Isaac Sim `6.0.1-rc.7+release.42383.32955d8d.gl`、Kit `110.1.2+production.326809.f9bf0dda.gl`、Replicator `1.13.27`，单 L40。`Lidar`、`LidarSensor` 与 GMO parser 存在，但可选 O_D 路径尚未执行。Timeline 不提供 `get_auto_update`，该字段记为不可用，以实际步序列检查推进条件。

完整 GMO ndarray 可能大于头部声明的有效结构；必须保留整个自有缓冲区，按头部声明区间校验序列化字段，不解引用任何指针。当前 ABI 为 264-byte v1 header；安装头文件及哈希保存在实例审计结果中。

所有诊断均保持 `formal_continuous_acceptance=false`。静态或保持的时间延迟不可辨识，重算新鲜度没有证据时保持 unknown。实际完成状态见新执行报告，不能以工具存在或配置已生成代替完成。
