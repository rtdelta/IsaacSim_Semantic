# 10｜pipeline 主流程与后端验证

对应源码：

- [pipeline.py](../../semantic_pixel_ratio/pipeline.py)
- [run_compare.py](../../run_compare.py)
- [factory.py](../../semantic_pixel_ratio/backends/factory.py)

## 1. CLI 入口

`run_compare.py` 只做三件事：

```text
argparse 解析 --config
→ load_config
→ pipeline.run
```

成功打印：

```text
frames
backend
elapsed_seconds
frames_per_second
output
```

失败时捕获常见配置、I/O 和运行错误，打印到 stderr 并返回退出码 1。

`SystemExit(main())` 让 shell、CI 和调度系统能根据退出码判断任务成功或失败。

## 2. `run()` 第一阶段：确定语义

按源码顺序：

```python
mapping = load_semantic_mapping(...)
target_ids = resolve_target_ids(mapping, labels)
pairs = discover_frame_pairs(...)
contract = inspect_dataset_contract(pairs[0], expected_dtype)
```

得到四项核心事实：

```text
五个 label 对应哪五个整数 ID
有哪些严格配对的帧
帧的确定顺序 ordinal
所有帧必须满足的 shape/dtype
```

这是后续所有性能实现共享的“语义边界”。

## 3. `run()` 第二阶段：构造缓存身份

```text
pairs_digest   = paths + sizes + mtimes 的 SHA-256
mapping_digest = mapping 文件内容 SHA-256
config_fingerprint = 再结合目标/ratio/shape/dtype/pipeline version
```

fingerprint 的目的不是加密结果，而是回答：

> 输出目录里的旧整数计数，是否仍可解释为当前输入与当前目标的结果？

性能参数不进入 fingerprint，所以改 `batch_frames`、线程数或 backend 后可以续接。

## 4. `run()` 第三阶段：准备输出

`_prepare_output` 有三种典型模式。

### resume

```json
"overwrite": false,
"resume": true
```

输出目录可已存在，后续账本会严格验证 fingerprint 和 part。

### new-only

```json
"overwrite": false,
"resume": false
```

输出目录只要非空就失败，防止混入旧结果。

### overwrite

```json
"overwrite": true,
"resume": false
```

若输出存在，会先确认没有 `.run.lock`，然后递归删除输出目录并重建。这是破坏性操作，因此 config 已禁止输出与输入目录互相包含。

## 5. 锁的作用范围

```python
with OutputLock(output_root):
```

覆盖：

- 后端创建；
- manifest/ledger；
- 所有 batch；
- 报告生成；
- 最终状态更新。

同一输出 root 同一时刻只允许一个运行。锁不能保护输入目录不被外部程序修改，所以生产流程仍应保证输入在分析期间稳定。

## 6. 后端工厂

明确指定：

```text
numpy       → NumpyBackend
torch_cuda  → TorchCudaBackend
triton_cuda → TritonCudaBackend
```

auto：

```text
Triton 可用？是 → triton_cuda
否则 Torch CUDA 可用？是 → torch_cuda
否则 → numpy
```

这里的“可用”只检查软件和 CUDA 能力，不跑性能基准。Triton 可用不等于它对此机器和数据端到端最快。

## 7. 后端 context manager

```python
with create_backend(...) as backend:
```

NumPy 后端离开时关闭 counter 线程池。Torch/Triton 没覆写 `close()`，目前依赖 Python/PyTorch 生命周期释放设备张量。

若未来后端持有：

- 原生文件描述符；
- CUDA streams/events；
- 固定 device buffers；
- io_uring queue；

应在 `close()` 中显式回收。

## 8. manifest 与 ledger 的顺序

pipeline 先创建/恢复 `CountsLedger`，再写顶层 `manifest.json` 的 `running` 状态。

`manifest.json` 是面向一次运行的总说明：

- 输入路径；
- 后端请求和实际选择；
- shape/dtype/帧数；
- 目标标签和 ID；
- 执行参数；
- running/completed/failed；
- 最终 summary 或 error。

`counts_manifest.json` 是恢复所依赖的计数事务记录。不要把两个 manifest 混为一谈。

## 9. 续跑从哪里开始

```python
remaining_pairs = pairs[ledger.completed_frames:]
```

成立前提是 ledger 已验证所有 part 从 ordinal 0 开始连续。

例如：

```text
expected_frames = 1000
completed_frames = 384
remaining = pairs[384:]
```

下一批的第一个 pair.ordinal 必须正好为 384。`ledger.append` 再次检查，防止跳帧或重复。

## 10. reader 与主循环

```python
for loaded_batch in reader:
    result = backend.count_batch(loaded_batch)
    _validate_batch_counts(...)
    GPU 时 _verify_batch(...)
    ledger.append(result)
```

本批提交边界是：

```text
backend 完成
→ 基本计数校验通过
→ 抽样验证通过
→ part 文件落盘
→ counts manifest 原子更新
```

前面任何一步失败，本批不成为 completed frame。

## 11. 基本后端输出校验

`BatchCounts.__post_init__` 已检查：

```text
shape == [本批帧数,2,5]
dtype 是整数
```

pipeline 再检查：

```text
没有负计数
任一单目标计数 <= pixels_per_frame
五目标计数总和 <= pixels_per_frame
```

由于当前后端最终返回 `uint32`，负数检查通常不会触发；它仍保护未来可能返回 signed integer 的后端。

这些检查能发现明显的 kernel/布局错误，但不能证明计数完全正确，所以 GPU 还需 reference 抽样。

## 12. GPU 抽样验证的准确语义

只在 backend name 不是 `numpy` 时执行。

对当前 batch 前若干帧：

```text
expected = NumPy _count_frame(同一个 LoadedBatch)
actual   = GPU result
要求逐元素完全相等
```

全运行最多验证：

```text
verify_sample_frames
```

不是每个 batch 都验证这么多。

例：

```text
verify_sample_frames=8
batch_frames=128
```

通常只验证第一批前 8 帧，后续不再验证。

续跑时只针对 remaining pairs 计数；已经存在账本中的帧不会重新读取和复核。因此 manifest 中的 `verified_sample_frames` 表示**本次 run 新验证的数量**，不是账本历史累计保证。

## 13. 为什么抽样用当前 batch

优点：

- 不为验证重新读盘；
- 输入数据与 GPU 看到的完全相同；
- NumPy reference 只增加少量 CPU 计算；
- 可及时在账本 append 前发现错误。

代价：

- 只覆盖样本；
- 通常集中在前几帧，不是随机采样；
- 无法发现只在后部特殊数据触发的 kernel bug。

修改 kernel 后的专门测试应覆盖边界，而不能仅依赖正式运行前 8 帧。

## 14. 日志进度

每完成 1000 帧或到最后一帧打印：

```text
completed X/N frames with backend
```

小于 1000 的中间 batch 不打印，避免日志开销与噪声。

`completed` 来自已原子提交到账本 manifest 的帧数，比“后端刚计算完”更接近可靠进度。

## 15. 完成顺序

所有 batch 处理完：

```text
ledger.mark_completed
→ ledger.load_all
→ elapsed = perf_counter - started
→ write_reports
→ manifest.status = completed
```

注意 `elapsed_seconds` 包含：

- mapping/config 之后的 pipeline 初始化；
- discovery 与 fingerprint metadata stats；
- 后端创建/JIT；
- I/O 和计数；
- ledger append；
- `load_all` 之前到 report 调用前的时间。

在 `write_reports` 调用前计算 elapsed，因此报告文件实际写出时间不完全计入 summary elapsed；但 `started` 在 `run` 最前，包含大量端到端环节。做精细性能分析需要分阶段计时，不能仅靠这一个值。

## 16. 异常路径

try 块内任意 `BaseException`：

```text
ledger.mark_failed("Type: message")
manifest.status = failed
manifest.error = ...
原子写 manifest
raise
```

随后 context managers 关闭 backend 并删除正常持有的锁。

如果进程被断电、`kill -9` 或解释器无法执行 finally，锁可能残留，某些 manifest 也可能保持 `running`。账本 part 和 checksum 才是恢复时的核心事实。

## 17. 一次完整时序

```text
CLI        pipeline       producer/readers       backend       ledger/reporter
 |            |                   |                  |                 |
 | config --> |                   |                  |                 |
 |            | validate inputs   |                  |                 |
 |            | lock/select/init  |                  | create manifest |
 |            | start reader ---->|                  |                 |
 |            |                   | load batch 0     |                 |
 |            |<--- batch 0 ------|                  |                 |
 |            |------------------------------count-->|                 |
 |            |                   | load batch 1     |                 |
 |            |<-----------------------------counts-|                 |
 |            | verify ---------------------------------------------->|
 |            |                   |                  |       append part|
 |            |<--- batch 1 ------|                  |                 |
 |            | ...               |                  |                 |
 |            | mark/load/report ------------------------------------>|
 |<-- summary |                   |                  |                 |
```

## 18. 本章自检

1. backend 为什么不进入 fingerprint？
2. 本批在哪一步以后才算可靠 completed？
3. GPU 的 `verify_sample_frames=8` 是否代表每批验证 8 帧？
4. manifest 与 counts manifest 分别是什么？
5. 为什么账本可以先 completed，而顶层 manifest 后 completed？
6. summary elapsed 是否是每个阶段都精确可分的 profiler 数据？

