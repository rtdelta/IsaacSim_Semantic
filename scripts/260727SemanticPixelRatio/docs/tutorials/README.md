# 260727SemanticPixelRatio 从零到完整掌握

这套笔记面向此前不了解并行、GPU 和性能优化的读者。目标不是只教会你运行一条命令，而是让你最终能够：

1. 准确说出项目在解决什么问题，以及每个指标的数学含义；
2. 从 `run_compare.py` 开始，独立追踪到读取、计数、账本和报告的每一步；
3. 理解线程、生产者—消费者、背压、批处理、GPU、CUDA、Triton 和归约；
4. 判断一项“加速”究竟减少了计算、内存流量、I/O，还是仅改变了调度；
5. 解释项目为何能断点续跑，以及并行完成顺序为何不影响最终结果；
6. 使用测试、微基准和性能剖析工具验证正确性与速度；
7. 在不破坏结果契约的前提下继续实现 pinned ring、多 stream、packed cache 等优化。

## 先记住项目的一句话定义

项目对严格配对的两套二维 semantic ID 图像进行离线统计：

- `whole_scene`：完整场景中的目标可见像素；
- `excavator_only`：只有挖掘机时的参考像素；
- 对五个 `tooth_front` semantic ID 分别计数；
- 主比值为 `whole_scene_pixels / excavator_only_pixels`；
- 五齿集合比值是“两边像素总数之比”，不是五个单齿比值的平均数。

它是**离线后处理项目**，不会修改 Isaac Sim Writer，也不会重新渲染场景。

## 当前实现与规划蓝图必须分开

项目的 [Plan_v01.md](../Plan_v01.md) 描述了目标架构，其中包含未来优化。当前源码真正实现的是：

- 严格文件配对、shape/dtype/mapping 校验；
- 后台 NPY 读取和有界队列；
- NumPy、Torch CUDA、Triton CUDA 三种计数后端；
- `Triton → Torch → NumPy` 的能力降级；
- GPU 结果的 NumPy 整数抽样复核；
- 分片 `.npz` 计数账本、校验和与断点续跑；
- 原子写出的 CSV/JSON/NPZ 报告。

当前**尚未**实现：

- 真正复用固定内存的 pinned-memory 环形缓冲；
- 多 CUDA stream 的 H2D、kernel、D2H 跨批重叠；
- CUDA Graph；
- `io_uring` 原生读取器；
- packed 连续数据缓存；
- AVX-512/OpenMP 原生 CPU 后端；
- GDS/cuFile；
- 依据实测结果选参数的自动调优器。

源码中的 `ring_slots` 目前是有界 Python 队列容量，不是规划图里拥有 `FREE → FILLING → ...` 状态机的物理 pinned buffer 槽。`auto` 目前按“能否使用”选择后端，也不是实测竞速。

## 推荐学习顺序

### 第一阶段：知道程序算的是什么

1. [01｜问题、数据与数学定义](01_problem_data_and_math.md)
2. [02｜读代码前必须会的 Python 与 NumPy](02_python_numpy_foundations.md)
3. [03｜项目架构与完整执行链](03_architecture_and_dataflow.md)
4. [04｜配置、输入发现与数据契约](04_config_discovery_contract.md)

完成后，你应该能手算一帧结果，并能从配置定位全部输入和输出。

### 第二阶段：真正理解并行与 GPU

5. [05｜并发、并行、线程池、队列与背压](05_parallelism_prefetch_backpressure.md)
6. [06｜NumPy CPU 计数算法](06_numpy_counting_algorithm.md)
7. [07｜从零理解 GPU、CUDA 与性能模型](07_gpu_cuda_foundations.md)
8. [08｜Torch CUDA 后端逐步拆解](08_torch_cuda_backend.md)
9. [09｜Triton 两阶段融合计数 Kernel](09_triton_backend.md)

完成后，你应该能解释“为什么 GPU 计算快，但端到端任务不一定快”。

### 第三阶段：掌握可靠性与完整代码

10. [10｜pipeline 主流程与后端验证](10_pipeline_walkthrough.md)
11. [11｜计数账本、原子写入、锁与断点续跑](11_ledger_atomic_resume.md)
12. [12｜报告、异常状态与确定性](12_reporting_and_determinism.md)
13. [13｜运行、测试、演示数据与故障排查](13_run_test_debug.md)
14. [14｜源码地图与推荐阅读顺序](14_source_code_map.md)

完成后，你应该能从一次失败的输出目录判断任务停在了哪里，以及是否可以安全续跑。

### 第四阶段：从“会用”走向“会优化”

15. [15｜基准测试、瓶颈定位与参数调优](15_benchmark_and_tuning.md)
16. [16｜进阶优化路线：从 pinned ring 到 GDS](16_advanced_optimization_roadmap.md)
17. [17｜分级实验与参考答案](17_labs_and_answers.md)
18. [18｜术语表、公式表与检查清单](18_glossary_and_checklists.md)
19. [19｜远端 RTX 4090 真机验证与实测结论](19_remote_gpu_validation.md)

## 学习方式

每学一章，建议执行以下循环：

```text
先手算一个小例子
    ↓
阅读对应源码
    ↓
运行现有测试
    ↓
故意制造一个错误
    ↓
解释错误在哪一层被发现
    ↓
修改 batch/线程等非语义参数并确认计数不变
```

不要用“程序运行成功”代替“已经理解”。真正掌握的标准是：你能预测输入改变后，哪个文件、哪个数组形状、哪个状态和哪个输出字段会改变。

## 贯穿全教程的形状记号

后文统一使用：

| 记号 | 含义 |
|---|---|
| `N` | 总帧数 |
| `B` | 一个 batch 的帧数 |
| `H, W` | 图像高度和宽度 |
| `P = H × W` | 每帧像素数 |
| `S = 2` | 两个来源：whole 与 reference |
| `K = 5` | 五个目标 semantic ID |
| `T = ceil(P / block_pixels)` | 每帧 Triton tile 数 |

核心数组形状：

```text
LoadedBatch.data     [B, 2, H, W]
BatchCounts.counts   [B, 2, 5]
Triton partial       [B, T, 2, 5]
```

对于 `720 × 1280`、`uint16`、`B=128`：

```text
一个输入 batch = 128 × 2 × 720 × 1280 × 2 bytes
               = 471,859,200 bytes
               = 450 MiB
```

这条计算会在后续内存和显存分析中反复使用。

## 验证基线

本机 CPU 环境已执行：

```text
python -m unittest discover -s . -p "test_*.py" -v
Ran 5 tests ... OK
```

本机没有安装 PyTorch/Triton，所以本机测试不包含 GPU。但教程随后通过免密 SSH 在远端 RTX 4090 上完成了真实验证：

- Python 3.12.3、PyTorch 2.11.0+cu128、Triton 3.6.0；
- NumPy、Torch CUDA、Triton CUDA 的三帧全量复核；
- 1026 帧、720p 正式数据的三后端整数账本完全一致；
- 三轮轮换顺序端到端基准；
- reader、pin、H2D、Torch 算子和 Triton kernel 分阶段计时。

完整环境、方法、原始结果与适用边界见 [第 19 章](19_remote_gpu_validation.md)。因此教程中的 GPU 章节既包含源码推导，也包含当前远端版本的真机证据。
