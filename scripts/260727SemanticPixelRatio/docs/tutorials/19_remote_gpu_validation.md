# 19｜远端 RTX 4090 真机验证与实测结论

本章记录 2026-07-29 对远端实际环境的验证。它回答三个问题：

1. 远端代码是否与本教程分析的本地代码一致；
2. Torch/Triton 后端是否真的能在 RTX 4090 上运行并产生相同整数；
3. kernel、数据传输和端到端速度之间究竟是什么关系。

这些数字是特定机器、软件版本、数据和缓存状态下的测量，不是永久性能承诺。学习重点是实验设计和结论推导方式。

## 1. 连接与安全边界

使用已配置 SSH alias：

```powershell
ssh -o BatchMode=yes isaacsim-gpufree "printf 'key-auth-ok user='; id -un; printf 'host='; hostname"
```

实测：

```text
key-auth-ok user=root
host=gpufree-container
```

sshd 生效路径：

```text
authorizedkeysfile /root/gpufree-data/wyb/RemoteConnection/authorized_keys
```

验证过程中：

- 始终使用 `BatchMode=yes`；
- 没有读取、复制或展示私钥；
- 没有启动 Isaac Sim；
- 没有终止其他进程；
- 没有覆盖旧项目和历史输出；
- 新验证写入独立的 `260727SemanticPixelRatio_v02/validation`。

## 2. 代码版本核对

比较范围：

- `run_compare.py`；
- `semantic_pixel_ratio/**/*.py`；
- `tests/**/*.py`；
- `requirements*.txt`；
- `README.md`；
- `configs/*.json`；
- 原有项目文档。

本地与旧远端目录共有的 32 个文件逐文件计算 SHA-256：

```text
IDENTICAL   32
DIFFERENT    0
```

非代码差异：

```text
远端旧目录额外存在 configs/output0727_01.json
本地额外存在 docs/OptimizationGaps_v01.md
```

因此旧远端项目的执行代码与本教程分析版本完全一致。为了：

- 不覆盖旧历史输出；
- 上传完整教程；
- 建立明确的 GPU Python 入口；
- 保存新的验证结果；

又在原本为空的目录中配置：

```text
/root/gpufree-data/repositories/260727SemanticPixelRatio_v02/
```

本教程随后把远端额外的 `output0727_01.json` 也补回本地配置目录，使正式可用数据配置纳入当前版本。

## 3. 远端有三套不同 Python

这是本次验证最重要的环境修正。

### 3.1 交互登录 `(venv)`

提示符显示：

```text
(venv) root@gpufree-container
```

但实际：

```text
VIRTUAL_ENV=/etc/isaac_alias
python=/etc/isaac_alias/bin/python
```

该解释器当前没有：

```text
torch
triton
```

所以“看到 `(venv)`”不能证明项目 GPU 依赖已安装。

### 3.2 Isaac Sim Python

```text
/root/isaacsim/python.sh
→ /root/isaacsim/kit/python/bin/python3
```

实测能导入 Isaac 自带 NumPy，但当前也没有 Torch/Triton：

```text
NUMPY_SPEC = Isaac pip_prebundle
TORCH_SPEC = None
TRITON_SPEC = None
```

本项目是独立离线后处理，不需要用 Isaac Python。不要为了“项目和 Isaac 有关”就强行使用 `/root/isaacsim/python.sh`。

### 3.3 系统 GPU Python

真正已有 GPU 依赖的是：

```text
/usr/bin/python3
```

为了给 v02 一个稳定、明确的项目入口，创建：

```text
/root/gpufree-data/repositories/260727SemanticPixelRatio_v02/.venv/
```

创建方式：

```bash
/usr/bin/python3 -m venv --system-site-packages \
  /root/gpufree-data/repositories/260727SemanticPixelRatio_v02/.venv
```

运行入口：

```bash
/root/gpufree-data/repositories/260727SemanticPixelRatio_v02/.venv/bin/python
```

`--system-site-packages` 避免在仅剩约 15 GB 的数据盘重复安装数 GB CUDA wheels。代价是 venv 会继承系统包升级，不能当作完全不可变环境；每次正式实验仍需记录版本。

## 4. 已验证软件与硬件

| 项目 | 实测值 |
|---|---|
| OS | Ubuntu 24.04 |
| Kernel | 5.15.0-168-generic |
| Python | 3.12.3 |
| NumPy | 1.26.4 |
| PyTorch | 2.11.0+cu128 |
| PyTorch CUDA runtime | 12.8 |
| Triton | 3.6.0 |
| NVIDIA driver | 580.126.09 |
| GPU | NVIDIA GeForce RTX 4090 |
| GPU memory | 24,564 MiB |
| Compute capability | 8.9 |
| SM count | 128 |
| Warp size | 32 |
| CPU | Intel Xeon Gold 6430 |
| cgroup CPU quota | 14 cores |
| cgroup memory limit | 50 GiB |
| 数据盘 | ext4，约 69 GB，总剩余约 15 GB |

`/proc/cpuinfo` 可见 128 个逻辑 CPU，但 cgroup 的：

```text
cpu.max = 1400000 100000
```

表示实际 CPU quota 约 14 cores。正式配置 `cpu_workers=16` 因此可能略微 oversubscribe，说明调参应看容器配额，不能只看宿主可见 CPU 数。

## 5. GPU 空闲确认

运行前检查：

```bash
nvidia-smi --query-compute-apps=pid,process_name,used_memory \
  --format=csv,noheader
```

验证时没有 compute process，GPU baseline memory 约 75 MiB。没有与 Isaac Sim GUI 同时竞争显存。

`nvidia-smi` 的瞬时 utilization 采样即使没有 compute process 也偶尔显示非零，不能只看一个利用率采样判断是否有任务；进程列表和时间线更可靠。

## 6. 可用正式数据

原 `combine_scene_02.json` 指向的 917 帧输入在当前远端实例上已不存在，但历史 manifest 和账本仍在。

当前仍存在并用于验证的是：

```text
/root/gpufree-data/repositories/260714_01semantic_worldModule/
  output/output0727_01/
```

配置：

```text
configs/output0727_01.json
```

数据契约：

```text
frames = 1026
shape = [720,1280]
dtype = uint16
target IDs = [5,7,9,11,13]
```

两套 semantic payload 约：

```text
1026 × 2 × 720 × 1280 × 2 bytes
≈ 3.78 GB（十进制）
```

历史 NumPy账本提供了独立的整数结果基线。

## 7. 第一层验证：现有测试

在 v02：

```bash
cd /root/gpufree-data/repositories/260727SemanticPixelRatio_v02
.venv/bin/python -m unittest discover -s . -p "test_*.py" -v
```

结果：

```text
Ran 5 tests
OK
```

这证明 CPU 路径和原有集成测试在 Python 3.12/NumPy 1.26.4 下仍通过，但它本身不执行 GPU 后端。

## 8. 第二层验证：三帧全量交叉检查

使用教程 [make_tiny_demo.py](make_tiny_demo.py) 创建三帧数据，分别运行：

```text
numpy
torch_cuda
triton_cuda
auto
```

GPU 配置：

```text
verify_sample_frames=3
```

因此所有三帧都由 NumPy reference 复核。

结果：

| 请求后端 | 实际后端 | NumPy复核帧 | pipeline elapsed |
|---|---|---:|---:|
| NumPy | NumPy | 0 | 0.0118 s |
| Torch CUDA | Torch CUDA | 3 | 0.3925 s |
| Triton CUDA | Triton CUDA | 3 | 2.4439 s |
| auto | Triton CUDA | 3 | 0.7264 s |

四份 cache 中：

```text
ordinals
frame_ids
whole_counts
reference_counts
```

全部逐元素相同。

这个实验得出两条不同结论：

1. Torch、Triton 与 auto 的**正确性路径真实可用**；
2. 三帧数据上 GPU 很慢，因为 CUDA context、allocation、Triton JIT 等固定成本远大于计算。

不能拿三帧 elapsed 评价大规模后端速度。

Triton 的第二次 `auto` 运行比显式 Triton 第一次快，正是编译缓存/预热效应的表现。

## 9. 第三层验证：1026 帧控制变量基准

### 9.1 实验设计

固定：

```text
同一 1026 帧数据
batch_frames=128
reader_threads=8
ring_slots=3
cpu_workers=16
GPU verify=8
每次独立新 output
```

先用一次 NumPy 扫描预热 page cache。随后三轮轮换运行顺序：

```text
round 1: NumPy → Torch → Triton
round 2: Triton → NumPy → Torch
round 3: Torch → Triton → NumPy
```

这样避免某个后端永远享受固定的先后位置。

所有 9 个新 `counts_cache.npz` 都与历史 NumPy cache 逐整数完全一致。

### 9.2 预热影响

首次 NumPy：

```text
pipeline = 9.374 s
109.45 fps
```

预热后 NumPy 三轮中位数：

```text
pipeline = 4.351 s
235.78 fps
```

第二次接近快一倍，说明 page cache 对本数据集影响巨大。若不区分冷热缓存，后端比较会严重失真。

### 9.3 三轮中位数

| 后端 | pipeline 中位数 | pipeline fps | pipeline 时间范围 | shell wall 中位数 |
|---|---:|---:|---:|---:|
| NumPy | 4.351 s | 235.78 | 4.321～4.405 s | 6.544 s |
| Torch CUDA | 2.720 s | 377.27 | 2.703～2.822 s | 5.149 s |
| Triton CUDA | 2.837 s | 361.68 | 2.719～2.908 s | 5.248 s |

在这次**热 page cache、完整进程运行**中：

```text
Torch pipeline 相对 NumPy约 1.60×
Triton pipeline 相对 NumPy约 1.53×
```

Torch pipeline 中位数比 Triton 少约 4.1%。因此当前：

```text
auto 选择 Triton
≠ auto 选择了端到端最快后端
```

差距不大，但足以实证“能力选择器不是自动调优器”。

### 9.4 pipeline time 与 shell wall

`summary.elapsed_seconds` 从 `pipeline.run()` 内开始计时，不包含 Python 模块导入等全部进程启动成本，而且在报告文件完整写完前就取值。

shell wall 还包含：

- Python 启动；
- import Torch/Triton；
- CLI；
- pipeline 外围；
- 剩余报告写出与进程退出。

所以 GPU 的 pipeline 加速在 shell wall 中被稀释：

```text
Torch wall 相对 NumPy约 1.27×
Triton wall 相对 NumPy约 1.25×
```

性能报告必须说明时间边界。

## 10. 第四层验证：64 帧阶段拆分

从正式数据读取前 64 帧，先把 page cache 热起来，再测五次中位数。

### 10.1 Reader 与完整 backend call

| 项目 | 64 帧中位数 | 范围 |
|---|---:|---:|
| warm reader：NPY load + batch copy | 111.4 ms | 108.7～127.5 ms |
| NumPy `count_batch`，batch 已在内存 | 159.9 ms | 151.2～161.5 ms |
| Torch `count_batch`，batch 已在内存 | 55.1 ms | 54.6～69.4 ms |
| Triton `count_batch`，batch 已在内存 | 42.6 ms | 41.9～90.9 ms |

reader 的 payload 吞吐约：

```text
2.12 GB/s
```

这里的 GPU `count_batch` 仍包括：

```text
pageable→pinned
H2D
device allocation
kernel
D2H count
```

不是纯 kernel 时间。

### 10.2 GPU 子阶段

| 子阶段 | 64 帧中位数 | 说明 |
|---|---:|---|
| pageable→pinned | 10.30 ms | 波动 6.37～111.42 ms |
| pinned H2D | 35.22 ms | CUDA Event |
| Torch 五目标通用算子 | 13.11 ms | CUDA Event |
| Triton 两个 kernel | 0.327 ms | CUDA Event |

Triton 的纯 kernel 约比 Torch 通用算子快：

```text
13.11 / 0.327 ≈ 40×
```

但 Triton kernel 相比 H2D：

```text
35.22 / 0.327 ≈ 108×
```

也就是说，Triton 已经把计数本身优化到几乎不是主要成本。继续把 0.327 ms 减半，每 batch 只省约 0.16 ms；减少一次 10 ms pin copy、改善 35 ms H2D 或 111 ms reader 更有价值。

## 11. 为什么“纯 kernel 快 40×”没有变成“项目快 40×”

完整路径：

```text
磁盘/缓存读取
→ 单帧数组
→ 连续 pageable batch
→ pinned copy
→ H2D
→ kernel
→ D2H小计数
→ checksum/fsync/report
```

Triton 只极大压缩了其中 kernel 一段。

对 64 帧：

```text
reader 111 ms
pin 10 ms
H2D 35 ms
Triton kernels 0.327 ms
```

即使流水线能重叠部分阶段，临界路径也主要由 reader/host transfer 决定。

这就是 Amdahl 定律、带宽瓶颈和端到端思维在真实项目中的具体表现。

## 12. 为什么完整运行 Torch 略胜 Triton

单独看热态 backend call，Triton 42.6 ms 优于 Torch 55.1 ms；单独看 kernel，Triton 更是大幅领先。

但完整进程还包含：

- Triton 首 batch specialization/JIT 与缓存加载；
- 不同 allocation 行为；
- reader 与后端的调度重叠；
- 每次进程启动；
- I/O 抖动；
- pipeline 计时边界；
- 只有 9 个 batch 的有限样本（8 个满 batch 加最后 2 帧）。

所以本次完整中位数中 Torch 略快并不与 kernel 结果矛盾。正确结论是：

> 在当前数据规模和现有非流水 GPU 实现中，二者端到端接近，Torch 略胜；若消除传输和调度瓶颈，Triton 的 kernel 优势才更可能显现。

不能从这一次测试推导“Torch 永远更快”或“Triton 没价值”。

## 13. 真机证据对优化顺序的修正

当前优先级：

1. 记录稳定的分阶段 timing 和 queue occupancy；
2. reader 直接填充可复用 pinned slots；
3. 消除每批 `.pin_memory()` 临时 copy；
4. 用固定 device buffers 减少 allocation；
5. 多 stream/event 重叠 H2D 与计算；
6. 对重复分析建立 packed 连续缓存；
7. 再评估 CUDA Graph；
8. 最后才继续微调已经只有 0.327 ms 的 Triton kernel。

GDS、io_uring、AVX-512 仍需单独证明环境和收益，不应仅凭技术名称实施。

## 14. 结果语义实测

1026 帧 group summary：

```text
whole total = 2,092,661
reference total = 5,340,479
aggregate ratio = 0.3918489334009178
ratio_over_one frames = 57
zero_reference frames = 0
```

NumPy、Torch、Triton 的计数 cache 完全相同，所以这些报告指标也相同。后端只影响执行时间和 manifest 的 backend 字段，不影响业务结果。

## 15. 验证产物

远端 v02：

```text
validation/
├── tiny_cross_backend_20260729_01/
└── full_output0727_benchmark_20260729_01/
```

其中保留：

- 每个后端的独立 config；
- output manifests；
- counts parts/cache；
- CSV/JSON reports；
- 每次完整运行日志。

不要把这些性能输出当作新的输入数据，也不要在比较时 resume 已完成 output。

## 16. 可复现实验前检查

重新测试前：

```bash
cd /root/gpufree-data/repositories/260727SemanticPixelRatio_v02

.venv/bin/python -c \
  "import torch,triton; print(torch.__version__,triton.__version__,torch.cuda.is_available())"

nvidia-smi --query-compute-apps=pid,process_name,used_memory \
  --format=csv,noheader
```

然后确认：

- 输入 1026 帧仍存在；
- output 使用新目录；
- GPU 没有 Isaac/其他 compute process；
- venv 版本与本章一致；
- 冷/热缓存口径明确；
- 每个候选 counts 与 reference 相等。

## 17. 本章结论

远端验证最终证明：

1. 本地与旧远端执行代码逐文件一致；
2. v02 已配置当前教程、代码和可用 GPU Python；
3. Torch 2.11/Triton 3.6/RTX 4090 能运行现有源码；
4. 三后端对三帧及 1026 帧正式数据整数一致；
5. `auto` 确实选 Triton，但不是端到端 autotuner；
6. 小数据 GPU 冷启动比 NumPy 慢；
7. 热态 Triton kernel 极快，但项目主要受 reader、pinned copy、H2D 和调度限制；
8. 优化必须看完整临界路径，而不是只看 GPU kernel。

这组结果把教程从“依据源码推导”升级为“源码、正确性账本和远端性能证据三者一致”。
