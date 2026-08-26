# 260727SemanticPixelRatio

独立的高吞吐离线后处理项目，用于严格配对 `whole_scene` 与
`excavator_only` 的 semantic ID 数组，统计五个 `tooth_front` 标签及其集合的
真实像素数量和可见像素比值。

主指标定义为：

```text
pixel_ratio = whole_scene_pixels / excavator_only_pixels
```

集合比值由两边五个标签的像素总和相除，不是五个单齿比值的平均值。

## 特性

- 严格的 frame ID、shape、dtype 和 mapping 校验；
- 有界批处理和后台 NPY 预取；
- `numpy`、`torch_cuda`、`triton_cuda` 三种后端；
- `auto` 模式优先选择 Triton CUDA，并在不可用时降级；
- GPU 结果使用 NumPy 精确抽样复核；
- 分片整数计数账本和断点续跑；
- CSV、summary 和计数缓存由主进程统一原子写出；
- 总数据规模增大时，内存和显存占用仍由 batch 大小限定。

## 环境

CPU 模式：

```bash
python -m pip install -r requirements.txt
```

GPU 模式需要与目标 CUDA 环境兼容的 PyTorch 和 Triton。远端现有环境已经提供
PyTorch CUDA 与 Triton，不建议仅为了本项目重复安装或覆盖。

## 配置

正式配置：

```text
configs/combine_scene_02.json
```

主要执行参数：

- `backend`: `auto`、`numpy`、`torch_cuda` 或 `triton_cuda`；
- `batch_frames`: 每个计算批次的帧对数量；
- `reader_threads`: 并行 NPY 读取线程数；
- `ring_slots`: 有界预取队列容量；
- `cpu_workers`: NumPy 计数线程数；
- `verify_sample_frames`: GPU 后端由 NumPy 精确复核的帧数。

## 运行

```bash
python run_compare.py --config configs/combine_scene_02.json
```

默认配置的输出位于：

```text
output/combine_scene_02_run_001/
```

## 输出

```text
output_root/
├── manifest.json
├── counts_manifest.json
├── counts/
│   └── part-*.npz
├── counts_cache.npz
├── per_frame.csv
├── anomalies.csv
├── summary.csv
└── summary.json
```

worker 和 GPU 后端只返回整数计数。最终比值、集合、CSV 和 summary 全部在主进程
中从同一份计数账本生成，因此并行完成顺序不会改变结果。

## 测试

```bash
python -m unittest discover -s . -p "test_*.py" -v
```

规划文档位于 `docs/Plan_v01.md`。

