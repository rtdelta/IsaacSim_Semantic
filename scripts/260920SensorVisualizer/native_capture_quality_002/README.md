# NC-002 原生采集画质与耗时实验

独立于 `v06`、`single06_lab` 和首轮 `native_capture_baseline`。旧源码在 `backups/` 保存可恢复快照，部署后每次检查旧项目源码哈希。方案完整保存在 [NC-002](docs/NC-002_implementation_plan.md)。实验结果另写报告，不能将源码已部署当成验证通过。

## 模块

- `run.py`：现有 Kit、标准 ROS2 MCAP 录制器的启动、采样、超时和进程收尾。
- `kit_entry.py`：同场景、同传感器的原生启动与官方 ROS Helper 管线。
- `experiment.py`：Session 层灯光/有效管线对齐，官方冻结采集、姿态跳变与独立观察证据。
- `wave.py`：实时子帧、Path Tracing SPP、Nsight 代表性实验。
- `tools/validate_bag.py`：标准包字段、标定、有限XYZ及末帧TF检查。
- `tools/validate_groups.py`：冻结组的新时间戳、MCAP/当前原生RGB和XYZ字节一致、关节及18条TF数值、相机和LiDAR实际渲染姿态检查。
- `tools/analyze_quality.py`：采集后做耗时与图像参考差异分析。
- `reference_external.py` / `reference_native.py`：分进程运行保留的旧链路与当前默认原生链路，各三轮，比较条件和作用域另记。
- `tools/analyze_phases.py` / `tools/compare_reference.py`：按NVTX阶段分析底层追踪，并核实跨链路位姿、标定和阶段耗时。

## 已完成结果

详见 [NC-002执行报告](docs/NC-002_execution_report.md)。默认Helper冻结采集通过字节、位姿和时间校验；旧gated约8.4秒/组，旧keepalive约4.4～4.5秒/组，默认原生约4.1～4.2秒/组。这里是包含准备和输出观察的各自作用域，消息格式、初始化和存储成本仍不同。

早期45组RT及12组PT参数扫描使用了可选门控改接诊断；后续默认Helper对照与实际Nsight轮次不改接图。质量扫描不是自动降低正式画质的依据。完整日志、样图和分析摘要在本地 `reports/runs/`；标准MCAP及完整大追踪文件保留在云端输出目录。

## 命令

执行入口面向云端Linux；本地Windows保存源码、备份和分析证据。`run.py`使用Linux的进程/资源接口，不是在本地Windows启动Isaac的入口。

先正常关闭当前 Isaac GUI，脚本不会终止别人的 Isaac 进程。云端终端：

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_quality_002
python3 run.py
```

这是三组冻结采集 smoke。最终默认配置保留官方Helper生成的门控，不改接图、不写自定义传感器Writer：保持资源常驻、关闭隐式capture-on-play，使用时间轴关闭自动推进而保持播放状态，并执行官方零增量渲染。查看输出目录的 `result.json` 和 `group_validation.json`；只有 strict `ok=true` 才算冻结原生MCAP验证成功。实验曾做过门控改接诊断，其数据不能混称为默认结果，见 `docs/experiment_decisions.md`。正式矩阵：

```bash
python3 wave.py rt
python3 wave.py pt
python3 wave.py trace
python3 matrix.py
```

三轮对照可运行 `python3 reference_external.py`，完成后运行 `python3 reference_native.py`；旧链路由独立子进程调用，原生引擎不导入旧代码。参考脚本顺序运行，避免两套Kit同时争抢GPU。两脚本目前内部生成各自的输出目录和静止姿态输入。

`rt` 请求1/2/4/8/16预热子帧，加固定2子帧正式采集，三类姿态、三轮重复。`pt` 固定每次渲染请求32 SPP，目标64/256/512/1024 SPP、8反弹、自适应关闭、OptiX降噪开启。当前请求值不等于已测到实际硬件样本数；必须结合输出证据和实测报告解释。

输出在 `/root/gpufree-data/semantic/output/native_capture_quality_002/`，包含标准 `bag/*.mcap`、实际配置、原始日志、资源采样、逐组计时及质量PNG。PNG为诊断证据；其读回、编码耗时单独记录，不混入渲染作用域。整轮时间仍包含这项诊断开销，因此不能直接等同生产吞吐。

没有外部依赖下载或系统修改。Ctrl+C会请求收尾；外层超时只处理本轮登记的子进程。冻结发布失败、时间错误或旧图像不能通过补写header掩盖。Path Tracing测试不承诺自动提高3DGS本身的重建细节。

`trace`会核实真实Nsight证据；不能只凭轮次名称判断已经追踪。完整SQLite较大，默认报告传输可显式排除 `native.sqlite` / `native.nsys-rep`，不删除云端原件。
