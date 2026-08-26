# Semantic World Module v03 示例配置索引

本目录提供一组相互引用的配置样例。每个参数/数据文件都有同名 Markdown，文档中的字段顺序与对应文件一致。

| 文件 | 用途 | 是否通常需要 |
|---|---|---:|
| `01_capture_multisensor.example.json` | 主运行配置；场景、传感器、变体、时钟和 supervisor | 必需 |
| `01_capture_multisensor.example.md` | 主配置逐字段说明 | 文档 |
| `02_render_pathtracing.example.json` | PathTracing RTX 配置 | 正式 PathTracing 任务需要 |
| `02_render_pathtracing.example.md` | PathTracing 配置逐字段说明 | 文档 |
| `03_render_realtime.example.json` | RealTimePathTracing RTX 配置 | 实时任务二选一 |
| `03_render_realtime.example.md` | 实时渲染配置逐字段说明 | 文档 |
| `04_semantic_mapping.example.json` | 稳定语义 ID 和颜色映射 | 输出标准语义时需要 |
| `04_semantic_mapping.example.md` | 语义映射逐字段说明 | 文档 |
| `05_fisheye_calibration_1920x1080.example.json` | 动态创建鱼眼相机的标定 Profile | 创建/覆盖鱼眼时需要 |
| `05_fisheye_calibration_1920x1080.example.md` | 鱼眼标定逐字段说明 | 文档 |
| `06_lidar_profile.example.json` | RTX LiDAR 标定审计 Profile | LiDAR 任务按需使用 |
| `06_lidar_profile.example.md` | LiDAR Profile 逐字段说明 | 文档 |
| `07_trajectory.example.csv` | 关节和根位姿轨迹数据 | 动态场景需要 |
| `07_trajectory.example.md` | CSV 每列说明 | 文档 |

## 文件引用关系

```text
01_capture_multisensor.example.json
├─ 02_render_pathtracing.example.json
├─ 04_semantic_mapping.example.json
├─ 05_fisheye_calibration_1920x1080.example.json
├─ 06_lidar_profile.example.json
└─ 07_trajectory.example.csv
```

主配置中的相对路径以主配置所在目录为基准解析。因此复制整套文件到同一目录后，内部相对引用仍然成立。

## 推荐使用流程

1. 复制 `01_capture_multisensor.example.json` 并改成任务专用名称。
2. 逐项阅读同名 Markdown，修改输出路径、USD、Prim Path、DOF、传感器和类别。
3. 在新输出目录上运行静态校验。
4. 查看 segment 计划。
5. 先做 1～3 帧 headless 冒烟测试，再启动正式长任务。

```bash
cd /root/gpufree-data/semantic/scripts/260819semantic_worldModule_v03

/usr/bin/python3 run_capture.py validate \
  --config configs/example/01_capture_multisensor.example.json

/usr/bin/python3 run_capture.py plan \
  --config configs/example/01_capture_multisensor.example.json

/usr/bin/python3 run_capture.py run \
  --config configs/example/01_capture_multisensor.example.json \
  --headless
```

`validate` 只验证 v03 配置结构和交叉引用，不保证远端 USD Prim、Isaac 内置 LiDAR 配置或标定内容真实存在。正式运行前仍应做 Isaac worker 预检和单帧测试。
