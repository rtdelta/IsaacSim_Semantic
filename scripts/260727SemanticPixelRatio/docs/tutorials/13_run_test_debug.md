# 13｜运行、测试、演示数据与故障排查

## 1. 进入正确目录

以下命令默认终端位于：

```text
D:\learning\IntelligentDepartment\CodesSet\Self\260707IsaacSIm\scripts\260727SemanticPixelRatio
```

PowerShell：

```powershell
Set-Location "D:\learning\IntelligentDepartment\CodesSet\Self\260707IsaacSIm\scripts\260727SemanticPixelRatio"
```

Linux 远端则进入对应仓库目录。

从项目目录运行能确保 `semantic_pixel_ratio` 包可被导入。

## 2. CPU 环境

建议虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Linux：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

CPU 只要求 NumPy。

## 3. GPU 环境

GPU 需要：

- NVIDIA GPU 与驱动；
- CUDA-compatible PyTorch；
- Linux 上兼容版本 Triton；
- PyTorch 能看到目标 CUDA device。

`requirements-gpu.txt` 只是最低依赖提示，PyTorch 的 CUDA wheel/conda 包必须与目标机器匹配。远端已有稳定 PyTorch CUDA/Triton 时，不要只为本项目盲目覆盖安装。

检查：

```bash
python -c "import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'no cuda')"
python -c "import triton; print(triton.__version__)"
```

Windows 常规环境通常不提供与 Linux 相同的 Triton 使用路径；本项目 `auto` 会按实际 import/CUDA 能力降级。

### 当前远端的正确解释器

远端提示符虽然显示 `(venv)`，但 `/etc/isaac_alias/bin/python` 当前没有 Torch/Triton；`/root/isaacsim/python.sh` 的 Isaac Python 也没有这两个包。离线项目应使用已经配置好的 v02 入口：

```bash
cd /root/gpufree-data/repositories/260727SemanticPixelRatio_v02

.venv/bin/python -c \
  "import torch,triton; print(torch.__version__,triton.__version__,torch.cuda.is_available())"

.venv/bin/python run_compare.py --config configs/output0727_01.json
```

已验证版本：

```text
Python 3.12.3
NumPy 1.26.4
PyTorch 2.11.0+cu128
Triton 3.6.0
RTX 4090
```

不要只根据 shell 前缀 `(venv)` 判断依赖，也不要把独立后处理项目强行放进 Isaac Python。远端部署、三后端正确性和性能证据见 [第 19 章](19_remote_gpu_validation.md)。

## 4. 先运行单元测试

```powershell
python -m unittest discover -s . -p "test_*.py" -v
```

当前测试覆盖：

1. 数字 frame ID 按数值排序；
2. 两目录缺帧时拒绝；
3. NumPy 对两来源五 ID 计数；
4. 完整 CPU pipeline、输出和第二次 resume；
5. group ratio、分母为零、ratio over one 和 aggregate。

这 5 项自动化测试未覆盖：

- Torch/Triton 真机运行；
- kernel 边界 ID=0；
- stale lock；
- part checksum 损坏；
- overwrite；
- 超大规模性能；
- io_uring/GDS/AVX 等未实现项。

“5 tests OK”是当前基线，不是所有环境和边界已证明。

GPU 真机路径已经通过第 19 章的独立交叉验证，但该验证尚未固化成每次 `unittest discover` 都自动执行的测试；换驱动、Torch/Triton 或 kernel 后仍应重新运行。

## 5. 跑一个三帧微型演示

教程附带 [make_tiny_demo.py](make_tiny_demo.py)：

```powershell
python docs/tutorials/make_tiny_demo.py
python run_compare.py --config docs/tutorials/_demo/config.json
```

输出：

```text
docs/tutorials/_demo/output/
```

再次运行同一命令，会走 resume：不再读取已完成帧，只加载账本并重写报告。

建议查看：

```powershell
Get-Content docs/tutorials/_demo/output/per_frame.csv
Get-Content docs/tutorials/_demo/output/anomalies.csv
Get-Content docs/tutorials/_demo/output/summary.json
Get-Content docs/tutorials/_demo/output/counts_manifest.json
```

微型数据每帧只有 8 像素，可以对照第 01 章手算。

若不想在源码树生成 demo，可指定临时目录：

```powershell
python docs/tutorials/make_tiny_demo.py --root "D:\temp\semantic_ratio_demo"
python run_compare.py --config "D:\temp\semantic_ratio_demo\config.json"
```

## 6. 正式运行前复制配置

`configs/combine_scene_02.json` 使用 Linux 远端绝对路径。本机 Windows 不能直接访问时，应复制成自己的配置并修改：

- 两个 semantic 目录；
- mapping 路径；
- output root；
- backend 与 batch/线程参数。

不要修改正式模板后忘记记录运行参数；建议每个 output 使用一份独立配置并保留在版本管理或实验记录中。

运行：

```bash
python run_compare.py --config configs/combine_scene_02.json
```

## 7. CPU 首次正式验证策略

在大数据前先选少量配对帧复制到测试目录：

```json
"backend": "numpy",
"batch_frames": 2,
"reader_threads": 2,
"ring_slots": 2,
"cpu_workers": 2,
"verify_sample_frames": 0
```

先确认：

- target IDs 正确；
- shape/dtype 正确；
- per-frame 手算一致；
- group 和 summary 口径一致；
- output 路径正确；
- 第二次 resume 成功。

## 8. GPU 首次验证策略

用同一小数据分别运行：

```text
output_numpy
output_torch
output_triton
```

GPU 配置：

```json
"verify_sample_frames": 100
```

让样本帧数小于验证数，从而全部复核。

用 NumPy 比较 cache：

```python
import numpy as np

with np.load("output_numpy/counts_cache.npz") as a, \
     np.load("output_triton/counts_cache.npz") as b:
    for key in ("ordinals", "frame_ids", "whole_counts", "reference_counts"):
        np.testing.assert_array_equal(a[key], b[key])
print("all integer counts match")
```

计数一致后再测大数据性能。

## 9. 如何读一次成功运行

### `manifest.json`

确认：

```text
status=completed
backend_requested/selected
dataset.frames/shape/dtype
targets label/id
verified_sample_frames
summary
```

### `counts_manifest.json`

确认：

```text
status=completed
completed_frames=expected_frames
parts 连续
```

### `summary.json`

重点看：

```text
aggregate_ratio
mean/median
zero_reference_frame_count
ratio_over_one_frame_count
```

### `anomalies.csv`

逐帧回查输入、相机和 mapping。

## 10. 常见错误

### `... directory does not exist`

原因：

- 配置仍是远端绝对路径；
- 相对路径误以为相对工作目录；
- 路径拼写或挂载点错误。

处理：记住配置内相对路径以 config 文件目录为基准。

### `semantic frame sets do not match`

原因：两个目录 frame ID 集合不同。

处理：

1. 不要通过 zip 或重命名强行错配；
2. 查清上游为何缺帧；
3. 确认是否选错 run 目录；
4. 修复/重新采集后再跑。

### `shape mismatch` / `dtype mismatch`

原因：

- 分辨率变化；
- 两次采集设置不同；
- 部分文件来自另一数据集；
- mapping 声明 dtype 与数组不符。

处理：检查报错 frame 的两个 `.npy`：

```python
import numpy as np
a = np.load("path.npy", mmap_mode="r", allow_pickle=False)
print(a.shape, a.dtype)
```

### `mapping is missing target labels`

配置 label 必须与 mapping 字符串精确相同，包括大小写和后缀。

### `output contains counts for a different input...`

fingerprint 不同。可能输入 path/size/mtime、mapping、目标或 shape 变化。

处理：

- 若这是新实验，使用新 output root；
- 若确实要重做，确认目标后设置 overwrite；
- 不要手工编辑 fingerprint 绕过保护。

### `counts part checksum mismatch`

part 被损坏或修改。不要继续生成报告。应从可靠备份恢复或使用新 output 重算。

### `output is locked`

可能有活跃运行，也可能是异常中断残留。

先读取 `.run.lock` 的 hostname/PID/time，并在对应主机确认进程状态。只有确认任务已终止后才删除精确锁文件并 resume。

### `CUDA device is unavailable`

检查：

- `torch.cuda.is_available()`；
- 驱动；
- 容器 GPU 映射；
- PyTorch 是否为 CUDA build；
- `device` 是否正确，如 `cuda:0`。

### `triton_cuda backend requires...`

Triton import、平台、PyTorch CUDA 任一不满足。可先用 `torch_cuda` 或 `numpy`，不要把能力降级误认为数据错误。

### CUDA out of memory

优先降低 `batch_frames`。`ring_slots` 主要影响 host 队列，不直接让单个 device batch 变小。

同时检查 GPU 是否被 Isaac Sim/其他进程占用。

### GPU verification failed

这是严重正确性错误，不应关闭验证后继续正式跑。

保存：

- 报错 frame ID；
- target IDs；
- batch shape/dtype；
- expected/actual；
- PyTorch/Triton/CUDA/GPU 版本。

用单帧复现，再检查 kernel mask、stride、dtype 和版本兼容。

## 11. 如何安全重跑

### 完全相同输入，继续

```json
"resume": true,
"overwrite": false
```

直接重跑。

### 新参数但同一结果语义

修改 backend/batch/threads 后可 resume。新运行可能只处理剩余帧。

若想公平比较性能，必须给每个配置独立全新 output，不能用已完成账本的 resume 时间比较。

### 输入/标签改变

使用新 output root。不要复用旧账本。

### 从零重做

明确设置：

```json
"overwrite": true,
"resume": false
```

再次核对 output root，避免删除混入其中的其他文件。

## 12. 最小诊断信息清单

报告问题时附：

```text
操作系统
Python/NumPy/PyTorch/Triton 版本
GPU/驱动/CUDA 版本
config（敏感路径可脱敏）
manifest.json
counts_manifest.json
完整 traceback
报错 frame 的 shape/dtype
剩余磁盘、内存、显存
是否第一次运行还是 resume
```

只说“GPU 不工作”很难定位。

## 13. 本章自检

1. 为什么本机不能直接运行远端绝对路径配置？
2. 为什么性能比较不能在已 completed 的 output 上 resume？
3. checksum mismatch 时为什么不应强行继续？
4. CUDA OOM 首先调哪个参数？
5. GPU verification failed 为什么不能简单设为 0？
