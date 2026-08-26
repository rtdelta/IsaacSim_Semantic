# 11｜计数账本、原子写入、锁与断点续跑

对应源码：

- [ledger.py](../../semantic_pixel_ratio/results/ledger.py)
- [atomic_io.py](../../semantic_pixel_ratio/results/atomic_io.py)
- [lock.py](../../semantic_pixel_ratio/results/lock.py)

## 1. 为什么不能只写一个大 CSV

长任务可能因以下原因中断：

- 文件损坏；
- CUDA OOM；
- 网络/磁盘异常；
- 人工 Ctrl+C；
- 机器重启；
- 进程崩溃。

若全部结果只保存在内存，最后一次写 CSV，任何中断都会失去已经完成的工作。

账本把每个成功 batch 变成一个不可变 part：

```text
counts/
├── part-000000000-000000127.npz
├── part-000000128-000000255.npz
└── ...
counts_manifest.json
```

续跑只需从最后一个连续 part 后开始。

## 2. 每个 part 保存什么

```text
ordinals         [batch] int64
frame_ids        [batch] unicode
whole_counts     [batch,5] uint32
reference_counts [batch,5] uint32
```

不保存：

- 原 semantic 图；
- ratio；
- group count；
- summary；
- bool mask。

group 和 ratio 都可从整数计数重新生成，避免派生数据重复存储后不一致。

## 3. part 文件名

```text
part-{start:09d}-{end:09d}.npz
```

例如：

```text
part-000000128-000000255.npz
```

文件名可读，但恢复不会只相信文件名；manifest 还保存：

```text
start_ordinal
end_ordinal
frames
sha256
```

## 4. append 的事务步骤

一次 `ledger.append(result)`：

1. 检查 batch ordinals 恰好是下一连续范围；
2. 在 counts 目录创建随机名临时文件；
3. `np.savez` 写入四个数组；
4. flush；
5. `fsync` 文件；
6. `os.replace(temp, final)` 原子替换正式 part；
7. 计算正式 part SHA-256；
8. 在内存 manifest 追加 part 元数据；
9. 原子重写 `counts_manifest.json`。

关键顺序是：

```text
先让 part 完整存在
再让 manifest 宣称 part 已提交
```

不能反过来，否则崩溃后 manifest 可能引用不存在或半写的 part。

## 5. 原子替换的含义

`atomic_write_json/csv` 使用：

```text
同目录临时文件
→ 完整写入
→ flush + fsync
→ os.replace
```

观察者通常只会看到：

- 旧完整文件；
- 或新完整文件。

不会看到逐字节增长的正式文件。

“原子”不等于整组输出是单一数据库事务。`per_frame.csv` 已替换而 `summary.json` 尚未替换时进程仍可能中断。顶层 `manifest.status` 最后更新为 completed，消费者应结合状态判断整组报告是否完成。

另外，源码 fsync 了文件本身，没有显式 fsync 父目录；极端断电和特定文件系统下的最强持久性语义仍依赖操作系统与文件系统。

## 6. manifest 恢复验证

存在 `counts_manifest.json` 且 `resume=true` 时：

1. JSON 可读且 schema 为 1；
2. config fingerprint 完全相同；
3. expected frame 总数相同；
4. target labels 顺序相同；
5. 每个 manifest part 文件存在；
6. 每个 part SHA-256 相同；
7. 第一 part 从 ordinal 0 开始；
8. 后续 start 与前一累计完成数连续；
9. 累计 frames 等于 `completed_frames`。

任一步失败都拒绝续跑。程序不会“猜测”损坏数据应如何修复。

## 7. 为什么允许换后端续跑

manifest 中记录 backend，但恢复时不要求它等于当前 backend，随后会更新为当前值。

理由：

```text
后端是执行策略
整数 counts 是结果契约
```

如果前 1000 帧由 NumPy 得到、后 1000 帧由 Triton 得到，只要两者逐整数一致，同一账本仍是有效的。

因此后端版本或算法发生语义变化时，必须：

- 提升 `PIPELINE_VERSION` 或把 backend semantic version 纳入 fingerprint；
- 或使用新的 output root；
- 并通过 cross-backend 测试证明兼容。

## 8. 崩溃点分析

### 崩溃在写临时 part 前/中

正式 part 不存在，manifest 未更新。临时 `.tmp` 可能残留，但不算 completed。

### part 已 replace，manifest 尚未更新

出现 manifest 未引用的 orphan part。下次 append 同一个 ordinal 范围时使用相同正式文件名并 `os.replace`，可以覆盖它。

当前恢复代码不会主动列举和拒绝 manifest 外的额外 part；它只验证 manifest 已声明的 parts。

### manifest 已更新

该 batch completed。续跑从其后开始。

### counts 全部完成，报告中断

重新运行时 remaining pairs 为空，加载账本并重新生成报告，无需重扫输入 payload。

## 9. `mark_completed` 与 `mark_failed`

completed 前再次要求：

```text
completed_frames == expected_frames
```

避免“读取器提前结束但程序仍提交成功”。

失败记录：

```text
status = failed
updated_at
last_error
```

失败并不删除完整 part，因为它们是可恢复工作。

## 10. `load_all`

按 manifest parts 顺序打开每个 `.npz`，连接为：

```text
ordinals          [N]
frame_ids         tuple length N
whole_counts      [N,5]
reference_counts  [N,5]
```

这一步内存是 `O(N×5)`，不是 `O(batch)`。但计数非常小：

```text
N×2×5×4 bytes
```

十万帧约 4 MB 计数 payload，另加 frame ID 字符串和 ordinal，通常仍很小。项目所说的大数据内存有界主要针对 semantic pixel payload。

## 11. `counts_cache.npz` 与 parts 的区别

parts + manifest：

- 是断点续跑的权威账本；
- 每批提交；
- 有每 part checksum。

`counts_cache.npz`：

- 在最终报告阶段把全部计数再写成单文件；
- 方便后续分析；
- 不是当前 resume 的数据源；
- 关闭 `write_counts_cache` 不影响账本恢复。

不要只备份 cache 而删除 parts 后仍期待当前代码续跑。

## 12. 输出锁

获取锁使用：

```python
os.open(path, O_CREAT | O_EXCL | O_WRONLY)
```

`O_EXCL` 使“仅当不存在时创建”成为原子操作。两个进程同时争同一 output root，只有一个成功。

锁内容：

```json
{
  "pid": 1234,
  "hostname": "...",
  "started_at": "..."
}
```

正常离开上下文会删除锁。

## 13. stale lock 如何处理

断电或强杀可能留下 `.run.lock`。当前代码不会自动判断锁是否过期，因为：

- PID 可能已被复用；
- 输出可能位于共享文件系统；
- hostname 可能不同；
- 误删活跃锁会允许两个 writer 并发破坏输出。

人工处理前必须：

1. 读取锁中的 hostname/PID/start time；
2. 确认对应机器上进程不再存在；
3. 确认没有任务仍在写该 output root；
4. 备份或检查 manifest/parts；
5. 只删除这个精确 `.run.lock`；
6. 使用相同配置 resume。

不要看到锁就机械删除。

## 14. overwrite 的风险

`overwrite=true` 会递归删除整个 output root。保护措施：

- output 不得与输入目录相等或互相包含；
- 存在 `.run.lock` 时拒绝覆盖；
- overwrite 与 resume 不能同时 true。

它仍无法判断 output root 中是否放了用户自己的其他文件。输出目录应该专用于一次运行。

## 15. 确定性与账本

确定性来自：

- pair ordinal 固定；
- append 只接受连续 range；
- part 顺序固定；
- integer counts；
- summary 最终按固定顺序从账本重算。

并行线程的完成先后不进入账本顺序。只要后端结果契约相同，batch size 改变只会改变 part 边界，不会改变最终 counts 和报告内容；运行时间和 backend 字段当然可能不同。

## 16. 恢复决策表

| 现象 | 处理 |
|---|---|
| 无输出目录 | 正常新跑 |
| 有完整 manifest/parts，resume=true | 自动验证并续跑 |
| fingerprint 不同 | 不要强行复用；新 output 或确认后 overwrite |
| part 缺失/sha 不符 | 视为损坏；从可靠备份恢复或新跑 |
| parts 存在但无 counts manifest | 当前代码拒绝猜测；使用新 output |
| stale lock | 先确认进程已死，再精确删除锁 |
| counts 完整但报告失败 | resume，重新生成报告 |

## 17. 本章自检

1. 为什么要先 replace part，再更新 counts manifest？
2. 原子写一个文件为什么不等于全部报告是一个事务？
3. orphan part 在什么崩溃窗口产生？
4. 为什么换 backend 可以续跑？
5. `counts_cache.npz` 为什么不是 resume 权威来源？
6. stale lock 为什么不能自动随便删除？

