# single06_lab 启动与证据读取

## 目录与环境

本地项目：`D:\learning\IntelligentDepartment\CodesSet\Self\260707IsaacSIm\scripts\260920SensorVisualizer\single06_lab`

单卡云端：`/root/gpufree-data/semantic/scripts/260920SensorVisualizer/single06_lab`

实验输出：`/root/gpufree-data/semantic/output/single06_lab/`

正式 v06 的启动和网页操作保持原样。实验期间先正常关闭现有 Isaac；运行器遇到已有 Isaac 会拒绝隔离采集，不会结束它。并发试验由实验运行器自己启动两个进程。所有命令在单卡实例运行，使用已有 `/usr/bin/python3`，不执行 pip 或 apt。

## 一次最小实验

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/single06_lab
python3 - <<'PY'
import json,time
from pathlib import Path
matrix=json.loads(Path('config/matrix.json').read_text())
spec={'name':'manual','groups':4,'policy':'gated','pose':'moving','trajectory':matrix['trajectory']}
Path('reports/manual_spec.json').write_text(json.dumps(spec))
PY
python3 -m lab.runner --spec reports/manual_spec.json \
  --output /root/gpufree-data/semantic/output/single06_lab/manual_$(date +%Y%m%d_%H%M%S)
```

运行器正常退出后自动在已有 ROS 环境逐条校验 MCAP。不要把实验启动命令粘进 Isaac Script Editor；`kit_lab_entry.py` 由运行器在独立 Isaac 子进程中执行。

## 完整顺序实验

```bash
python3 tools/run_investigation.py \
  --output /root/gpufree-data/semantic/output/single06_lab/investigation_$(date +%Y%m%d_%H%M%S) \
  --groups 4 --repetitions 2
```

默认先做 gated／keepalive × 固定／移动姿态的 A/B、B/A；随后 CPU 主机池、同进程三轮、初始化／清理原生追踪；最后仅交互和交互＋采集。相机预热数量与画质不变。首次测试是筛选，不能用四组数据承诺 P99 稳定性。

若当前不希望出现测试用的交互 Isaac 窗口，可加 `--skip-interaction`。仅交互和并发模式会显示独立 GUI，并通过本机 Unix socket 发送模拟按键，用来衡量 accepted-to-applied；不包含网页网络和人的主观画面延迟。

## 原生短窗口

在规格 JSON 加入：

```json
{"trace_window":"steady","trace_group":1,"metrics_set":"ad10x","metrics_hz":1000}
```

保留其他规格字段。`trace_window` 还支持 `initialize`、`cleanup`。窗口结束后停止采样，进程继续完成采集与资源释放。若 GPU 指标不可用，保留失败证据，不自动安装或升级。

原生追踪显著增加开销，`native.nsys-rep`／`native.sqlite` 用于机制分析；吞吐收益使用无追踪的结果。启动器显式设置 `NSYS_NVTX_PROFILER_REGISTER_ONLY=0`，保证普通 NVTX 字符串能触发窗口。

## 实验选项

| 字段 | 取值与作用 |
|---|---|
| `policy` | `gated`／`keepalive`，每轮单独比较 |
| `pose` | `moving` 保留原轨迹；`static` 只固定姿态，时间仍推进 |
| `host_pool` | `true` 启用实验 CPU 缓冲复用，默认关闭 |
| `episodes` | 大于 1 复用同进程场景／产品；每轮新录制进程，仍排空生成 |
| `rgb_immediate_copy` | 实验性 RGB 立即消费，默认关闭；当前没有明显端到端收益 |
| `isolated_camera_warmup` | 仅供失败机制复现。当前会触发 `render_pose_mismatch`，不应启用来正式采集 |
| `full_group_window` | 从第 1 组时钟推进到提交打包的完整原生窗口 |
| `native_memory_stacks` | 请求 CUDA 内存追踪与 API 栈；实际栈覆盖必须检查，当前导出未取得 API 栈 |
| `stop_after_groups` | 在收到指定组数进度后请求正常停止；已经开始的下一组可继续排空 |
| `timeout_s` | 运行超时先发 stop、等待排空，最后只处理本任务创建的进程组 |

## 分析与文件层次

```bash
python3 tools/analyze.py /root/gpufree-data/semantic/output/single06_lab/具体实验目录
```

| 产物 | 内容 |
|---|---|
| `result.json`、`spec.json`、`job.json` | 变量、过程状态、退出码、画质配置与逐轮校验 |
| `engine.log` | Isaac、RTX、PhysX、Replicator 原始 warning/error |
| `system_resources.jsonl` | 每秒 NVML 与进程／线程 CPU ticks，统一 host monotonic ns |
| `captures/<session>/bag_unified/` | 完整点云、图像、相机标定、相机位姿、TF、Clock、关节／整机姿态、帧索引 |
| `captures/runs/<run>/diagnostics/` | 原模块与实验阶段、请求、所有权、等待依赖、warning、资源事件 |
| `native.nsys-rep`、`native.sqlite` | 原生 CPU 调度、Vulkan/CUDA、复制、硬件指标，实际存在才算追踪成功 |
| `analysis.json` | 阶段统计、设备指标目录／缺口、活动区间并集、同步关系与证据限制 |
| `dependency_ledger.csv` | 等待方→生产方→资源→完成信号及包含性耗时 |
| `resource_ledger.csv` | 产品生命周期及回调源数组元数据，注明是否拥有／是否暴露完成信号 |
| `native_memory_ledger.csv` | 短窗口 CUDA 内存分配／释放事件、大小、上下文、关联号；不是泄漏判定 |
| `public_api_frames.json` | 已解析的公开 NVRTC API 采样祖先数量，不能当作调用次数 |
| `group_1_timeline.csv`、`timeline.html` | 一组的执行顺序与设备指标曲线 |
| `sessions.json` | 同进程多轮的独立录制目录 |

## 停止

优先让短试验自然结束。需停止某个采集试验时，在其**实际实验目录**写入：

```bash
printf '%s\n' '{"action":"stop"}' > /实际实验目录/control.json
```

当前已提交的冻结组完成后停止，排空录制与资源释放。不要使用 `pkill kit`、`pkill python`。SIGINT/SIGTERM 对实验采集运行器也先转换成 stop 请求；整套试验的监督进程停止行为须以其运行状态确认。

## 后续机制复现与读取

```bash
python3 tools/run_followup.py \
  --output /root/gpufree-data/semantic/output/single06_lab/followup_$(date +%Y%m%d_%H%M%S)
python3 tools/run_confirmation.py \
  --output /root/gpufree-data/semantic/output/single06_lab/confirmation_$(date +%Y%m%d_%H%M%S)
```

两条命令依次执行，各自完全结束再执行下一条。后续试验会故意复现一个失败候选，保留失败原因后继续独立试验；不是正式录制入口。图形指标窗口使用已有 `ad10x-gfxt` 和 10 kHz，仍排除于普通吞吐比较。

```bash
python3 tools/analyze.py /实际实验目录
python3 tools/group_timeline.py /实际实验目录 --group 1
python3 tools/build_timeline.py /包含native.sqlite的实际实验目录
```

本轮结果及证据限制见 [findings.md](findings.md)，实际操作与备份见 [operation_record.md](operation_record.md)。原始 Nsight 文件可能包含机器环境信息，给同事分享时优先使用整理后的图表和报告。
