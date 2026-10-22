# NC-006：Scene18 点云链路一致性实验

本项目是隔离的排查项目，不替代 single06/v06 或原生 NC-005 的正式采集入口。旧项目与磁盘 USD 保持原样。

## 入口与记录

- 完整已确认方案：`docs/NC-006_scene18_lidar_equivalence_plan.md`。
- 结果报告：`docs/NC-006_scene18_lidar_equivalence_report.md`。
- 执行决定与失败记录：`docs/execution_decisions.md`。
- 原件备份：`backups/source_copies.zip`；来源与哈希：`source_provenance.json`。
- 本地 `reports/` 保存脱敏 SSH 操作回执、接口检查与部署回执；独立审计日志实际位置见每份回执的 `audit_log`。
- 本地 `results/` 保存通过 SHA-256 校验拉取的首轮点云、状态证据和统计。完整各轮 MCAP/日志保留在远端输出目录。

远端代码目录：`/root/gpufree-data/semantic/scripts/260920SensorVisualizer/lidar_equivalence_006`。

本次输出目录：`/root/gpufree-data/semantic/output/lidar_equivalence_006/study_20261013_030531`。

## 模块

| 文件/目录 | 职责 |
|---|---|
| `legacy/` | single06 实验源码副本；保持自制采集行为，增加观测入口 |
| `native/` | NC-005 源码副本；保持原生 Helper 冻结采集行为，增加正式数组观测 |
| `native_dual/` | 单独的原生诊断副本；同时观察 GMO、CPU、CUDA |
| `snapshot_entry.py` | 在实际初始化后记录静止基准姿态及依赖哈希 |
| `suite.py` | 三轮配对独立进程，交替执行次序；不并行争抢一张 GPU |
| `observations.py` | 保存已经获得的正式 XYZ、矩阵、有效参数和 mesh 状态 |
| `dual_observe.py` | 同次输出连续读、原始帧号/数组、CPU/CUDA 哈希检查 |
| `legacy_raw_probe.py` | 可选的自制链路原始输出探针、可见三角网格导出 |
| `causal_suite.py` / `causal_retry.py` | 追加诊断及其独立重试；失败输出不覆盖 |
| `analyze.py` | 正式 XYZ 与 MCAP 哈希匹配、最近邻、距离分布、重复性 |
| `analyze_raw.py` | GMO 与提取数组一致性、按发射器编号配对 |
| `analyze_diagnostics.py` | 同帧读取和预热/冻结对照汇总 |
| `geometry_compare.py` | 用现有 Warp 对导出三角形做最近表面/首个命中核对 |
| `make_figures.py` | 用本地证据生成静态科学对照图 |
| `operations/` | 经审阅、通过审计包装器执行的远端操作脚本；含保留的失败尝试，不应批量执行 |
| `build_deploy.py` / `pull_evidence.py` | 有路径约束、备份和哈希校验的源码部署/证据传输 |

## 复核已有结果

在远端 ROS 环境下可以重跑离线分析，不必启动 Isaac：

```bash
source /opt/ros/jazzy/setup.bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/lidar_equivalence_006
/usr/bin/python3 analyze.py /root/gpufree-data/semantic/output/lidar_equivalence_006/study_20261013_030531
/usr/bin/python3 analyze_raw.py /root/gpufree-data/semantic/output/lidar_equivalence_006/study_20261013_030531
/usr/bin/python3 analyze_diagnostics.py /root/gpufree-data/semantic/output/lidar_equivalence_006/study_20261013_030531
```

重新渲染应创建全新的 study 目录，先运行姿态探测，再运行 `suite.py`。操作脚本故意拒绝覆盖已存在实验输出、拒绝遇到既有 Kit 时继续启动。每次的 `input_spec.json`、`spec.json`、`job.json` 和源码 manifest 是具体运行依据。

未安装新依赖；没有下载外部文件。Warp 编译的是本项目的几何核，缓存位于本次输出的 `geometry_analysis/warp_cache`，不是更新 Warp 或 CUDA。
