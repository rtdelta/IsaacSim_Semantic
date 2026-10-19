# v07 日志结构和完整性约定

默认输出根目录为 `/root/gpufree-data/semantic/output/sensor_visualizer/v07`。测试使用独立的 `v07_validation` 目录。数据和诊断分开组织，所有运行代码独立于 v06。

## 1 启动和服务

- `launches/*.json`：请求的物理 GPU UUID／PCI、角色、CPU 配额、工作池上限、affinity、作业文件和原生日志路径。
- `launches/*.kit.log`：Kit 启动至退出的原生日志，包含诊断订阅建立前的 warning。控制台输出仍保留。
- `launches/*_resources/`：独立启动监控进程，从 exec 前开始记录该 PID 的 CPU／线程与逐卡资源，覆盖 Kit 入口尚未执行的原生准备阶段。通过 PID 和 start_ticks 匹配生命周期，目标退出后自行停止，不控制或终止目标。
- `runtime/capture_service.log`：常驻服务的启动标准输出、异常与退出信息。
- `runtime/capture_worker.json`：worker ID、PID、Linux 进程 start_ticks 和项目归属。
- `runtime/capture_worker_status.json`：心跳、服务阶段、任务归属和设备绑定；关闭后仍保留最后状态。
- `runtime/capture_pending.json`：一轮尚未结束的持久任务提交；通过非覆盖的原子发布建立。正常任务完成后删除，异常退出后保留供显式恢复。
- `runtime/capture_worker.lock` 与 `capture.lock`：分别表示常驻服务锁和单轮任务锁。服务在空闲时保留前者，释放后者。
- 深目录的 IPC 路径会映射到本用户拥有、权限 0700 的 `/tmp/sv07-ipc-<uid>/`，socket 权限 0600；状态中的 `ipc_endpoint` 记录实际地址，避免 Linux 路径长度限制。
- `runtime/control_events.jsonl`：控制事件流，带 logger ID、会话／状态 revision、事件序号、UTC 与 monotonic 时间。每次关闭保留单独的 `control_events.<log_id>.summary.json`，并更新最新 summary，报告产生／写入数、丢失和 I/O 错误。

## 2 每轮任务和数据

`tasks/<job_id>/` 保存 `job.json`、`task.json`、`control.json` 和 `status.json`。`job_complete` 表示记录、清理和任务释放已经结束；`finished` 但尚无 `job_complete` 时仍应等待，不能仅凭“服务还活着”判断上一轮是否结束。

实际数据在时间命名的 session 目录。`job_spec.json`、`sensor_registry.json`、`render_profile.json`、`asset_manifest.json`、`trajectory_metadata.json`、`capture_index.jsonl` 和 `writer_report.json` 解释本轮条件和产出。`bag_unified/` 保持 ROS 2 CDR／MCAP 的组织及原有话题。`diagnostics_ref.json` 指向本轮诊断，并标记 worker、job 和场景是否复用。

## 3 诊断文件

`runs/<run_id>/diagnostics/` 的文件按进程分开写入：

| 文件 | 内容 |
| --- | --- |
| `events_<role>_<pid>.jsonl` | 状态变化、span 起止、输入回执、传感器完成、缓冲槽和写入事件 |
| `resources_<role>_<pid>.jsonl` | 逐卡 UUID／PCI／利用率／功耗／显存；进程与线程 CPU、RSS、上下文切换、缺页、I/O 计数；cgroup 配额／cpuset／限流与压力；采样器墙钟及线程 CPU 耗时 |
| `warnings_<role>_<pid>.jsonl` | 首次警告及出现次数为二次幂时的样本，抑制重复文本风暴 |
| `warnings*.json` | 各类 warning 的精确累计次数、首末时刻和代表性文本 |
| `summary*.json` | span 分布、事件产生和落盘数、丢失计数、队列峰值、I/O 错误及 `complete` |
| `manifest*.json` | 源码哈希、配置、原生 API 能力、设备和日志策略，注明测量边界 |
| `anomaly*.jsonl` | 慢阶段、失败、重试和 warning 周边的有界历史；最多循环保留 32 个异常窗口 |

常驻服务的初始化／复用日志与每轮采集日志不同。交互、网页、采集、记录各有自己的诊断角色。不要把一份事件文件当成所有线程或整台云实例的完整审计。

## 4 一组数据的细分阶段

日志覆盖：源状态等待 → 槽位等待 → 原生时钟推进 → 姿态应用 → 冻结检查 → 预热 → 正式渲染提交／返回 → 全部传感器手动回执 → GPU 数据物化／独立 CPU 复制 → 姿态／时钟验证 → mmap 打包／发送 → PNG 编码 → CDR／MCAP 写入 → 消费确认／释放。

任务准备、暂停 drain、最终 drain、记录进程关闭和 worker 是否可复用单独记录。请求设备、Annotator 目标设备、节点暴露的源设备及回调数组物理设备分别观察；仅设置 renderer 编号不是完整执行位置证明。

Python GC 通过 `gc.callbacks` 观察，不禁用收集、不改变阈值。summary 的 `python_gc` 保存 0/1/2 代次数、墙钟与线程 CPU 总时长、最大时长和对象计数；2 代及慢收集另记 `python_gc_begin/end` 与 collection ID。可将收集区间与 `physx_root_write` 等慢 span 对齐，区分调用期间的收集和候选 native 工作。回调耗时包含观察开销；没有对应事件时不能把 native 长尾归因于 GC。

共同关联字段为 `worker_id`、`job_id`、`capture_id`、`group_id`、`request_id`、`attempt_id`、`stage_generation`、`pose_revision`、`slot_generation`、物理 GPU、PID／TID、同实例 `monotonic_ns` 和人类可读 UTC。

## 5 完整性和测量边界

默认启用交互诊断，正常队列和关键事件队列各 8192 条，非阻塞后台落盘。关键事件优先写，文件行顺序可能不同于 `event_seq`，分析按序号及 monotonic 时间排序。队列满不会阻塞按键回调；产生的丢失会记入 summary 和最近丢失事件，不能宣称该轮日志完整。

有序关闭会排空、flush 和 fsync。`complete=true` 需要没有已报告丢失、没有 I/O 错误，而且产生数等于落盘数。警告采用精确计数加抽样文本，异常窗口是滚动证据，均不代表逐条无限保留。突然 SIGKILL、掉电或磁盘满可能丢失尾部；未完成 manifest 保持 incomplete，不能伪装为正常结束。

纳秒是时间单位，不是承诺纳秒精度。跨 await 的同线程 CPU 时间包含同线程其他回调；墙钟时间包含原生等待。GPU 资源是离散采样，不能当作某个函数的精确 GPU 耗时。网页接收、引擎应用和屏幕呈现不同；没有可靠呈现事件时不填造屏幕完成时间。

不记录图像／点云正文、密码、token、完整环境变量或 HTTP 认证头。原生警告通过去敏后的诊断样本记录，原生 Kit 日志作为项目内部证据保留，分享前需按内容复查。

## 6 查看和离线分析

按键日志区分 IPC 接收、主线程解释与实际姿态应用。新版按键到姿态时间从 socket 接收或原生输入时刻计算，包含队列等待；每次解释及有新输入的姿态提交均记录 command ID／input revision。按键续租与松键也记录，不能把最近一次界面状态替代完整事件历史。

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/v07
python3 -c 'from sensor_visualizer_v07.analysis import analyze; import sys; analyze(sys.argv[1], export_trace=True)' /完整路径/runs/某个run/diagnostics
```

生成 `analysis.json` 与 `trace.json`。先看 `log_quality`、summary 的 `complete` 和未闭合 span，再解释阶段耗时。后台采样默认约一秒；更深追踪可以指定组范围，避免全程高密度分析改变被测工作负载。
