# Custom Semantic Writer 极简实现

本目录实现一条单相机语义采集链路：

```text
USD class labels
  -> semantic_mapping.json（稳定 Dataset ID + 自定义 RGB）
  -> Camera / RenderProduct / RTX Renderer
  -> semantic_segmentation(colorize=False)
  -> Isaac runtime ID + idToLabels
  -> 最后一个逗号分隔标签
  -> 稳定 uint16 Dataset ID NPY
  -> mapping LUT
  -> 自定义 RGB Semantic PNG
```

标签规则示例：

```text
{"class": "simpleroom,towelroom01wallside"}
  -> towelroom01wallside
```

## 文件

- `extract_semantic_mapping.py`：从 USD 的 `semantics:labels:class` 生成配置。
- `semantic_mapping.py`：共享的标签规范化、runtime ID 到 Dataset ID 映射逻辑。
- `semantic_dataset_writer.py`：Replicator Custom Writer。
- `semantic_capture_custom.py`：启动 Isaac Sim 并采集。
- `validate_semantic_output.py`：验证 NPY、mapping 与 PNG 是否逐像素一致。
- `run_capture_remote.sh`：把临时目录和缓存定向到远端数据盘后启动采集。

## 远端生成 mapping

```bash
export HOME=/root/gpufree-data/wyb/.semantic_custom_writer_runtime/home
export TMPDIR=/root/gpufree-data/wyb/.semantic_custom_writer_runtime/tmp
export XDG_CACHE_HOME=/root/gpufree-data/wyb/.semantic_custom_writer_runtime/cache
export XDG_CONFIG_HOME=/root/gpufree-data/wyb/.semantic_custom_writer_runtime/config

/root/isaacsim/python.sh extract_semantic_mapping.py \
  --usd /root/gpufree-data/wyb/Semantic_260709_01.usd \
  --output semantic_mapping.json
```

## 远端采集

```bash
bash run_capture_remote.sh \
  --usd /root/gpufree-data/wyb/Semantic_260709_01.usd \
  --mapping semantic_mapping.json \
  --output /root/gpufree-data/wyb/test_semantic_CustomWriter_260713_01/output/run_01 \
  --frames 1 \
  --width 1280 \
  --height 720
```

输出目录包含：

```text
rgb/rgb_0000.png
semantic_id/semantic_id_0000.npy
semantic_color/semantic_color_0000.png
semantic_runtime_id/semantic_runtime_id_0000.npy
metadata/frame_0000.json
semantic_mapping.json
```

## 校验

```bash
/root/isaacsim/python.sh validate_semantic_output.py \
  --output /root/gpufree-data/wyb/test_semantic_CustomWriter_260713_01/output/run_01 \
  --mapping semantic_mapping.json
```

校验器会重新按 mapping 将 NPY 着色，并和 PNG 做逐像素对比。任何未定义 ID、形状或 dtype 不符、颜色不一致都会返回非零退出码。
