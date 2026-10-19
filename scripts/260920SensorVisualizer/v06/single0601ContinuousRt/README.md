# single0601ContinuousRt

根据 `docs/ImpPlan/002` 和 `003` 实现的独立 Isaac Sim 6.0.1 项目。旧 v06 与磁盘 USD 不需要修改。单个 Kit GUI 拥有 USD、PhysX、渲染和原生输入；一个独立 CPU worker 负责无损 PNG、ROS2 CDR 与 MCAP。运行记录含源文件/资产/环境清单、逐组调度和原生 receipt、commit、独立回读及 SHA256。

当前连续 RT2 路线在实际 SDK 运动探测中未通过 LiDAR 位姿及独立射线几何校验，禁止写入正式连续数据。2026-10-14已部署原生GMO、自有字节、Fabric阶段追踪及最小房间诊断；低速运动复现半步/一步旋转残差，修复门槛仍未通过。具体结果见[本次执行报告](docs/Execution/20261014_execution.md)。已验证的 `barrier` 后备路线保留产品和 Writer，在目标物理边界请求一次正式事件，不使用逐组16子帧预热；旧结果见[2026-10-13执行报告](docs/Execution/20261013_execution.md)。后备同步和完整性结果不代表连续、质量、速度及交互通过。

## 运行

远端已有 `/root/isaacsim`、ROS2 Jazzy、scene18 与显示器 `:20`。在远端项目目录执行：

```bash
DISPLAY=:20 /usr/bin/python3 -B run_capture.py --job config/mixed_pair.json --probe
S0601_FORCE_BARRIER=1 DISPLAY=:20 /usr/bin/python3 -B run_capture.py --job config/mixed_pair.json --barrier-probe
S0601_FORCE_BARRIER=1 DISPLAY=:20 /usr/bin/python3 -B run_capture.py --job config/mixed_pair.json
```

`--probe` 和 `--barrier-probe` 只产生能力证据。正式入口在每次录制前重新执行24个运动目标的原生时间/位姿/数组寿命探测，失败立即拒绝录制。默认 `auto_verified` 选择连续路线进行探测；目前请显式设置 `S0601_FORCE_BARRIER=1` 使用已验证后备。运行中不自动切换后端。

五种 schema4 配置为 `strict_scene18`（4相机+13雷达）、`single_camera`、`single_lidar`、`mixed_pair` 和 `benchmark_scene18`。`null` 选择全部、`[]` 不选择该类；两类同时空报错。默认60Hz物理/循环、10Hz模拟时间采样；5Hz固定抽取完整10Hz事件。1920×1080 RGB、无损PNG、原生Instant LiDAR XYZ与10Hz scan参数保持不变。模拟10Hz不等于单卡墙钟实时10Hz。

默认 `strict_complete` 先预留有界 credit，再进入目标物理步。512MiB配置按保守原始/编码/到达安全容量计算，目前一组在途；raw release不等于written或segment_closed。`strict_latest` 有配置校验，但运行器明确返回 `policy_unverified`，尚未实现和验收。不要将它用于正式数据。

## 控制与停止

原生窗口 `single0601ContinuousRt` 提供速度/转速、JSON轨迹、Hold、当前组完成后Pause/Resume/Stop。视口获得键盘焦点且物理推进时接收 W/S、A/D、Q/E、R/F；U/O、T/G、Y/H控制关节，I/K、J/L控制倾斜。焦点丢失、暂停与停止清空按键。所有命令在下一物理PRE阶段处理，POST实际读回后记录，不按墙钟积分。原生焦点与延迟验收尚需专项证据。

Stop 保留原始 requested 数，不发布完整 READY。失败目录保留 `FAILED` 与原因，不把已有前缀补写为成功。仅允许关闭本任务创建的进程；`tools/stop_record_remote.py` 验证记录PID、Kit及入口，并要求测试已结束后才执行关闭。不要按名称全局 kill Isaac。

## 回读与验收

Linux 已有 ROS2，无需安装依赖：

```bash
source /opt/ros/jazzy/setup.bash
/usr/bin/python3 -B tools/validate_mcap.py /path/to/READY_recording --report reports/revalidation.json
/usr/bin/python3 -B tools/extract_samples.py /path/to/READY_recording --output reports/samples/run_id
/usr/bin/python3 -B tools/run_acceptance.py /root/gpufree-data/semantic/output/single0601ContinuousRt --output reports/acceptance_actual.json
/usr/bin/python3 -B tools/compare_performance.py reports/benchmark_spec.json --output reports/performance_comparison.json
```

独立回读使用真实 ROS2 `SequentialReader`，重算 CDR/PNG/XYZ/状态哈希、源时间、原生ReferenceTime、新鲜性、历史位姿、TF拓扑和全部请求目标。已经发布的 READY 文件不可变，回读报告必须写在外部。`run_acceptance` 汇总已有真实记录并检查完整文件 SHA；它不代替新的 SDK 或 MCAP 回读。`compare_performance` 拒绝缺少三轮交错基线/候选、20组预热、200组测量及独立质量证据的速度通过声明。

本地纯逻辑测试：`python tools/run_logic_tests.py`。结果明确限定为逻辑契约，不代表 Isaac、ROS或原生键盘测试。

有界原生诊断：`/usr/bin/python3 -B tools/start_native_probe_remote.py --scene room --profile mixed`。启动器拒绝已有Kit；仅输出`reports/continuous_recovery`证据，不发布READY。`--sync zero_delay`、`--motion-history off`、`--tlas frame`为诊断对照，当前均未解决低速连续旋转。全部XYZ、全部GMO头及固定首/中/末完整包按128MiB预算保存；初始化和采样受120秒墙钟约束。离线检查使用`analyze_native_events.py`、`analyze_room_geometry.py`和`analyze_room_rotation.py`。完整命令和实际边界见本次执行报告。

按 [003 分层测试方案](docs/Experiments/003_物理传感器时序与状态历史一致性_分层测试方案.md) 实现的进一步诊断位于 [tools/clock_state](tools/clock_state/README.md)，使用独立 `reports/clock_state_consistency/` 证据目录，保存拒绝前完整 GMO/XYZ、固定目标表、阶段时钟、输入等价与候选不可辨识性。实施与实测状态见 [004 执行记录](docs/Experiments/004_时序状态一致性分层测试_实现与执行记录_20261014.md)。其 POST 与保持模式是纯 USD 房间诊断条件，不自动启用到正式采集后端，也不发布 READY。

本轮选定分支已完成 61 对 C/F 实验（每侧 4,428 目标），53 对同时通过测量与生命周期资格，8 对历史 120 Hz 清理失败保留。退出 Timeline 恢复遗漏提交已修复并通过新的 120/60 Hz 原生回归；旋转几何故障仍在。HOLD2/ALT 四条件各 100×3 几何通过，但改变平均运动轨迹且载荷新鲜度未知，不提升正式连续验收状态。

## 文件与回退

正式数据在输出根目录的 `partial/<recording_id>` 准备，独立 CPU 回读通过后进入 `datasets/<recording_id>`。根目录和每段有 `dataset_manifest.json` 与 READY，READY内容恰为实际manifest字节SHA256加换行。失败进入 `failed`；历史失败前缀可能保留在 `partial`，其 session 仍为FAILED且无READY。

Windows `tools/remote_ops.py` 使用已有 `isaac-new` 配置、Credential Manager凭据引用、SSH指纹和实例身份校验。exec/deploy/pull均留本地审计，不接受明文密码。deploy只传输本项目源文件，并为覆盖文件备份到远端本项目 `.deploy_backups`。运行矩阵时不要更新其源文件。回退先通过自身运行记录确认进程已退出，再恢复需要的项目内备份；旧v06及资产无需恢复。

生成的本次汇总可用`publish-report --report-name continuous_recovery_result.json`或`project_acceptance_20261014.json`发布，并提供`--purpose`说明。该入口只接受这两个项目内schema1 JSON文件，大小不超过2MiB；固定落点、传输SHA、覆盖备份和原子替换均有审计。避免把大型证据文件内嵌进远端执行脚本。

安装revision、录制中Reset、完整原生交互测试、同条件M5质量/速度比较和30分钟全组合长测的未验收状态必须保留，不能从READY推导通过。

## 报告与验收证据

正式报告、精选验收摘要和必要配图见 [报告索引](docs/reports/README.md)。原始采集、逐帧状态和性能追踪保留在原运行目录，由仓库忽略规则排除。
