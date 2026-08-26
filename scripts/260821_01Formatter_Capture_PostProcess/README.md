# Semantic World v03 → Post Process Chain v02 Formatter

将 Semantic World Module v03 的逐帧目录转换成 Post Process Chain v02 可直接发现和严格配对的平铺输入目录。

## 核心映射

```text
v03_boom_camera/full_scene/frame_00000000/rgb.png
  -> full_scene_rgb/rgb_00000000.png

v03_boom_camera/full_scene/frame_00000000/semantic_class_id.npy
  -> full_scene_semantic/semantic_id/semantic_id_00000000.npy

v03_boom_camera/front_teeth_only/frame_00000000/semantic_class_id.npy
  -> teeth_only_semantic/semantic_id/semantic_id_00000000.npy
```

语义彩图、excavator-only 数据和 `packet.json` 也会转换到 v02 风格目录。v03 mapping 中的 `name` 会规范化为 Post Process v02 所需的 `label`，并写入 `dataset_dtype`。

## 安全与速度

- 输入目录只读，输出必须是不存在的新目录。
- 所有变体先做严格帧配对和数据契约检查，再原子发布。
- 默认多线程 `hardlink_or_copy`；同一文件系统使用硬链接，速度快且不重复占用大文件空间。
- 硬链接与源文件共享同一个 inode，任意一方修改文件内容都会影响另一方；本工具和 Post Process v02 都只读取这些输入。

## 使用

```bash
python3 run_formatter.py --config configs/example.json
```

输出根目录中的 `postprocess_v02_inputs.json` 可直接复制到 Post Process Chain v02 配置的 `inputs` 字段；`conversion_manifest.json` 记录帧数、shape、dtype 和物化统计。

