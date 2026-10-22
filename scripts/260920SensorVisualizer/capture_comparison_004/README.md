# NC-004：八种采集配置统一复跑

本项目保存旧版本，独立运行原生测试副本，并在录包完成后从实际 MCAP 解码 PNG。测试数据不是重新渲染的样图。

入口：`suite.py`；矩阵：`config/suite.json`；解码：`tools/decode_case.py`；统计与画面比较：`tools/analyze_suite.py`。

本地项目：`D:/learning/IntelligentDepartment/CodesSet/Self/260707IsaacSIm/scripts/260920SensorVisualizer/capture_comparison_004`。

远端项目：`/root/gpufree-data/semantic/scripts/260920SensorVisualizer/capture_comparison_004`。

远端数据：`/root/gpufree-data/semantic/output/capture_comparison_004/comparison_<UTC>/`；具体目录见项目 `reports/latest_suite.json`。结果包含每个配置、每轮的 MCAP、源配置、原始日志、资源采样、校验结果、PNG 和图像索引。MCAP 保留在远端，解码图片及证据同步回本地 `results/`。

完整操作与统计边界见 [NC-004 实现方案](docs/NC-004_implementation_plan.md)。最终结果以 `results/<本轮目录>/analysis/NC-004_report.md` 为准，不能把后台启动成功当作所有配置验收通过。

## 本次结果入口

本次目录：`comparison_20261012_070140`。完成后的解读见 [NC-004 执行报告](docs/NC-004_execution_report.md)，逐轮数字见 [完整统计报告](docs/reports/results/comparison_20261012_070140/analysis/NC-004_report.md)，直接看图打开 gallery.html（本地原始证据：`scripts/260920SensorVisualizer/capture_comparison_004/results/comparison_20261012_070140/analysis/gallery.html`）。这些相对结果链接适用于本地副本；云端结果在下述 output 目录。

## 在云端复跑

先确认没有其他 Isaac 测试或正在使用的 GUI 占用这张 GPU，再在云端终端运行：

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/capture_comparison_004
python3 suite.py
```

每次生成独立时间目录；不会覆盖本次 MCAP 或图片。保持终端会话，直到 24 项运行及其解码结束。已有一轮运行时不要重复启动。当前矩阵按 1024 目标 SPP 测试 PT，完整测试约需两小时；不是秒级冒烟测试。

suite 使用已有 `/root/isaacsim` 与 `/opt/ros/jazzy`，配置中写明当前固定场景和基线轨迹。换实例/路径时先核对 `config/suite.json`，不能假定机器配置相同。

## 完成后重新分析已有 MCAP 和 PNG

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/capture_comparison_004
source /opt/ros/jazzy/setup.bash
OUT=/root/gpufree-data/semantic/output/capture_comparison_004/comparison_20261012_070140
python3 tools/verify_common_inputs.py "$OUT"
python3 tools/analyze_suite.py "$OUT"
```

以上只分析已完成结果，不重新渲染。各项 PNG 已由 suite 在采集进程退出后解码；单项需要重新解码时可执行 `python3 tools/decode_case.py "$OUT/05_native_frozen_rt_default/round_01"`。失败配置会返回非零并保留诊断图，不能将其视为成功数据。

`tools/watch_results.py` 是本次已授权套件的本地取证辅助，固定跟踪本次目录，使用已登记 SSH 凭据与操作审计。它不启动或停止远端测试，不能直接当作下一次套件的通用启动器。

## 报告与验收证据

正式报告、精选验收摘要和必要配图见 [报告索引](docs/reports/README.md)。原始采集、逐帧状态和性能追踪保留在原运行目录，由仓库忽略规则排除。
