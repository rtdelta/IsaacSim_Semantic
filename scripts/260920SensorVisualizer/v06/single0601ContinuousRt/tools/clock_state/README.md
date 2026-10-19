# 物理时钟与状态历史一致性诊断入口

依据 `docs/Experiments/003_物理传感器时序与状态历史一致性_分层测试方案.md`，执行记录见同目录的 `004_时序状态一致性分层测试_实现与执行记录_20261014.md`。

这是独立诊断入口。原始字节、关联拒绝、全部计划目标和冻结参考均保留；输出不提升正式连续采集验收状态。房间是纯 USD 静态六面环境，不能推及接触动力学、相机或多传感器全量运行。

## 文件职责

| 文件 | 职责 |
|---|---|
| `run_continuous.py` | 实际物理步推进、固定目标表、PRE/POST 写入、独立原始旁路、阶段记录、保持窗口实际状态检查 |
| `raw_tap.py` | 同一 Writer 事件先拥有 XYZ/GMO 副本，再进行严格 source/ref/epoch 关联；错误保留为数据 |
| `common.py` | 纯 CPU 目标表、保持模式及三值状态 |
| `candidates.py` | 十种位姿候选、完整链接等价组、不可辨识判定 |
| `analyze.py` | 所有原始证据 SHA 回读、GMO 独立解码、F 解析资格、逐目标联合表 |
| `phase_analysis.py` | CPU 阶段顺序和当前 USD/Fabric 观测；不代表 GPU 提交/完成顺序 |
| `h5_models.py` | 已登记的有限浮点阈值模型与常量基线比较 |
| `branch_analysis.py` | PRE/POST 与成对保持写入方式的实际输入、效果和代价比较 |
| `coordinator.py` | 单实例有界 C→F→分析任务，竞争进程/预算检查，进程级 watchdog |
| `test_contracts.py` | 无 SDK 的独立数值控制与失败注入 |

## 本地检查

从项目根目录执行：

```powershell
& 'D:\Anaconda3\python.exe' -m unittest tools.clock_state.test_contracts -v
```

## 远端运行约束

当前协调器明确绑定既有单卡项目路径 `/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt`。经本项目 `tools/remote_ops.py` 执行，保留已配置主机指纹、GPU 身份和本地审计。不得改为双卡端口或绕过主机检查。

先检查进程与容量；运行中的批次即便暂时没有 Kit，也可能继续启动下一对，不能在此期间覆盖采集源码。新分支使用新的实验 ID，先 12 目标资格，再按已保存条件表执行 100×3。已有运行目录拒绝覆盖；重跑必须分配新 repeat/实验 ID 并说明原因，不能抹去失败。

协调器在实例内的调用形式：

```text
/usr/bin/python3 -B tools/clock_state/coordinator.py --batch config/clock_state/<locked_batch>.json
```

仅使用已经审核、锁定且已通过相应前置资格的批次文件。启动返回 PID 后，状态在 `reports/clock_state_consistency/batches/<batch_id>/status.json`。`progress_remote.py` 仅读取状态。

## 证据与解释

每对证据位于 `reports/clock_state_consistency/<experiment_id>/<condition>/repeats/<repeat>/`。两侧均有完整文件清单；C 保存未归属、重复或拒绝事件，目标统计分母不随其增减。

`measurement_qualified=true` 表示能解释该实验，不表示 C 几何通过。`lifecycle_qualified` 还要求 C/F 清理均显式通过，`run_qualified` 为二者合取；清理失败保留字段细节、返回失败终态并停止依赖批次。旧报告未包含新字段时应从原始 terminal 独立核对，不能默认通过。`formal_continuous_acceptance=false` 始终保持。`payload_freshness_ok=null` 表示尚未取得逐载荷重算证据，不能用新 header 或回调次数代替。

候选是对原始距离的解释，不是用于重新计算通过率的修正变换。静态/保持相同位姿会让多个时间候选等价，应报告不可辨识。当前矩阵和 ExternalSimulationTime 一致，也不能证明 GPU 取用了同一历史状态。

v2 可将完整 GMO 无损 gzip 保存，保存原始字节 SHA；分析器解压后再次核验，且队列/磁盘预算仍按未压缩字节保守预留。压缩与回调观测也可能影响壁钟代价，因此 v2 PRE/POST/保持条件共用相同保存策略，并保留同版本 PRE 基线。
