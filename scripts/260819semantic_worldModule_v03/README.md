# Semantic World Module v03

v03 是一个自包含的、配置驱动的 Isaac Sim 6 数据采集项目。主流程只认识传感器驱动契约，不认识“第几台相机”或某个具体型号；针孔相机、OpenCV 鱼眼相机、RTX LiDAR 和自定义驱动都从 schema-v6 JSON 装配。

本目录的 Python 代码不导入任何旧版本脚本。

## 已实现的核心能力

- 严格配置校验：未知字段、错误频率、无效 Prim 路径和不兼容的采集模式会在启动前失败。
- 内置驱动：`camera.pinhole`、`camera.fisheye_opencv`、`lidar.rtx.rotary`、`lidar.rtx.solid_state`。
- 多传感器整数时钟：所有采样时刻落在物理步上，不累计浮点误差。
- RenderGroup：`batched` 模式下，同组多相机只触发一次 RTX 渲染，再分别读取数据。
- 两种相机来源：绑定 Stage 中已有 Camera Prim，或由配置创建新 Camera Prim。
- 鱼眼自动校准：绑定已有 Prim 时，自动读取 Camera 属性、`OmniLensDistortionOpenCvFisheyeAPI` 属性、应用的 schema 和世界变换，并计算 SHA-256 校准哈希。
- LiDAR 区间语义：第一份数据只会在一个完整扫描周期之后到期；点云、距离和强度由 `GenericModelOutput` 解析。
- 帧事务：所有传感器文件先写入 `.v03/transactions`，成功后再原子发布。
- 断点续跑：`.v03/commits.jsonl` 是事实账本，配置指纹不同的任务不能误续跑。
- 外部 supervisor：Isaac Worker 按固定帧数分段；心跳超时、非零退出或 GPU 崩溃后重启该分段。
- PathTracing 优先采用 `variant_major`：一次运行连续采一个场景变体，避免每帧反复切可见性和重建 RTX 历史。
- 变体白名单隔离：`include_paths` 自动隐藏白名单之外的最小 Imageable 根，同时自动保护所有启用传感器 Prim 及其祖先；只在 Session Layer 写可见性。
- 变体模态过滤：`modalities_by_sensor` 可让完整场景输出 RGB+语义，而隔离场景只读取并提交语义结果。
- 可选 CSV 关节回放插件：按物理步插值并控制指定 articulation DOF。

## 目录

```text
semantic_world_v03/
  config.py             严格 schema-v6 配置
  registry.py           传感器类型注册表
  sensors/              Camera/Fisheye/LiDAR 驱动
  timing.py             整数物理步调度
  rendering.py          RenderProfile 与 RenderGroup
  coordinator.py        单帧采集与提交策略
  transactions.py       暂存/提交/回滚
  ledger.py             断点续跑账本与 manifest
  worker.py             短生命周期 Isaac Worker
  supervisor.py         进程监控、分段和重启
  world.py              固定步长世界控制
  variants.py           Session Layer 可见性变体
  motion.py             可选运动驱动
configs/                可运行模板、渲染配置、校准示例
tests/                  不依赖 Isaac Sim 的核心测试
run_capture.py          本地入口
```

## 鱼眼参数到底从哪里来

已有鱼眼 Prim 推荐这样配置：

```json
{
  "type": "camera.fisheye_opencv",
  "source": {"mode": "existing_prim", "prim_path": "/World/Sensors/Fisheye"},
  "calibration": {
    "policy": "read_and_validate",
    "expected_model": "opencv_fisheye"
  }
}
```

此模式不要求在任务配置中重复填写 `fx/fy/cx/cy/k1...k4`。驱动会从指定 Prim 自动读取并写入每帧元数据。任务配置仍负责分辨率、频率、模态、RenderGroup 和输出目录。

如果 Stage 中没有相机，才使用 `source.mode=create`，并提供真实标定文件：

```json
{
  "type": "camera.fisheye_opencv",
  "source": {
    "mode": "create",
    "parent_prim": "/World/Sensors",
    "prim_name": "Fisheye"
  },
  "calibration": {
    "policy": "from_profile",
    "profile": "fisheye_opencv_1280x720.json"
  }
}
```

项目附带的 `.example.json` 只有结构示例，不能当作真实标定值。

## 新增传感器

新增第二台或第 N 台针孔/鱼眼相机，只需复制一个 `sensors[]` 项并修改 `id`、`prim_path`、频率和输出目录。主调度器无需修改。

新增内置 RTX LiDAR 也只需配置：

```json
{
  "id": "roof_lidar",
  "type": "lidar.rtx.rotary",
  "source": {
    "mode": "create",
    "parent_prim": "/World",
    "prim_name": "RoofLidar",
    "config": "Example_Rotary"
  },
  "render_group": "lidar_rtx",
  "clock": {"hz": 10, "acquisition": "interval"},
  "modalities": ["point_cloud", "range", "intensity"],
  "calibration": {"policy": "read_from_prim"},
  "output": {"sink": "filesystem", "required": true},
  "settings": {"scan_rate_hz": 10, "accumulate_outputs": true}
}
```

全新物理传感器家族需要实现 `BaseSensorDriver`，然后仅在配置根节点注册，不修改 worker/coordinator：

```json
{
  "drivers": {
    "radar.custom": "my_sensor_package.radar:CustomRadarDriver"
  }
}
```

## PathTracing 稳定策略

v03 不假设 Python 能捕获 GPU 驱动级卡死。`run` 命令本身是 supervisor，真正加载 Isaac/RTX 的 worker 是子进程：

1. 每个 worker 只处理 `runtime.segment_frames` 帧。
2. worker 在加载、预热、重放、渲染、提交和关闭阶段写原子心跳。
3. supervisor 依据不同阶段使用不同超时。
4. 超时或崩溃后终止 worker，重新打开 Stage，并查询提交账本。
5. 已提交的 `(variant_id, frame_id)` 不再渲染；只重做未提交帧。

示例默认 100 帧一段，比历史上约 205 帧出现的 GPU page fault 更早主动回收进程内 RTX 资源。它不能修复驱动本身，但把一次长任务的故障域限制在一个短分段内。

## 场景隔离与按变体输出模态

`include_paths` 为空或省略时不启用自动隔离，适合 `full_scene`。非空时，v03 在 Session Layer 自动隐藏与白名单无关的最浅层 Imageable Prim；相机和其他启用传感器的 Prim 分支会自动保留。灯光等需要保留的非传感器对象应加入 `include_paths`，或通过显式 `visibility: "inherited"` 保留。

```json
{
  "id": "excavator_only",
  "include_paths": ["/World/Excavator", "/World/Environment/DomeLight"],
  "visibility": {},
  "modalities_by_sensor": {
    "front_camera": ["semantic_segmentation"]
  }
}
```

传感器本身仍应在 `sensors[].modalities` 中声明所有任务可能使用的模态。例如相机声明 `["rgb", "semantic_segmentation"]`，然后由变体选取子集。语义专用变体不会调用相机的 RGB `get_data()`，也不会向事务或输出目录写入 RGB 文件。未知字段、未知传感器、空模态列表以及未在传感器声明的模态都会在启动前被拒绝。

## 运行

先进入 v03 项目根目录。普通 Python 可以验证配置和查看计划，不会导入 Isaac：

```bash
python run_capture.py validate --config configs/capture_multisensor_template.json
python run_capture.py plan --config configs/capture_multisensor_template.json
```

远端运行时，supervisor 使用普通 Python；每个短生命周期 worker 再由
`runtime.worker_command` 指定的 Isaac Python 启动：

```bash
python3 run_capture.py run \
  --config configs/capture_multisensor_template.json \
  --headless
```

如果 Isaac 安装位置不同，修改 `runtime.worker_command`。它是 supervisor 启动 worker 时使用的命令前缀。

若宿主镜像把系统库目录放在 Isaac Sim 运行库之前，可将该命令前缀配置成
`["/bin/bash", "<项目>/isaac_python_abi_safe.sh"]`。包装器只为 worker
进程重排 `LD_LIBRARY_PATH`，确保 Isaac 自带 Python 加载匹配的
`kit/python/lib/libpython`，不会修改 Isaac Sim 安装目录。

## 运动配置

Stage 自带的时间采样动画会随固定 Timeline 自动播放。需要 CSV 关节轨迹时可增加：

```json
{
  "scene": {
    "motion": {
      "driver": "semantic_world_v03.motion:CsvArticulationMotion",
      "trajectory": "/data/trajectory.csv",
      "settings": {
        "articulation_prim_path": "/Excavator",
        "time_column": "time",
        "joint_columns": {
          "cab_joint": "cab",
          "boom_joint": "boom",
          "arm_joint": "small_arm",
          "bucket_joint": "bucket"
        },
        "angle_units": "radians",
        "interpolation": "linear"
      }
    }
  }
}
```

其中 `joint_columns` 的键必须是 Stage articulation 的真实 DOF 名，值是 CSV 列名。

## 输出与恢复

业务输出按 `传感器/场景变体/帧` 组织。RGB 保存为 PNG，普通数组保存为 NPY，原始二进制保存为 BIN，所有包都带 `packet.json`。语义映射启用时，语义结果直接保存为稳定的 `semantic_class_id.npy`（当前映射范围使用 `uint16`）和便于查看的 `semantic_color.png`；不会重复落盘仅对当前渲染进程有效的原始 annotator ID 数组。

内部恢复文件：

- `.v03/commits.jsonl`：只追加的提交账本。
- `.v03/manifest.json`：当前运行状态。
- `.v03/heartbeats/*.json`：worker 心跳。
- `.v03/logs/*.log`：每次 worker 尝试的日志。
- `.v03/transactions/`：未提交暂存；崩溃后的残留不会被当作有效帧。

## 测试

```bash
python -m unittest discover -s tests -v
```

核心测试不需要 Isaac Sim。真正部署前仍必须在目标 GPU 上执行 1 帧、20 帧和跨分段的 PathTracing 冒烟测试，因为本地开发机没有 Isaac/RTX Runtime，无法替代目标机验证。
