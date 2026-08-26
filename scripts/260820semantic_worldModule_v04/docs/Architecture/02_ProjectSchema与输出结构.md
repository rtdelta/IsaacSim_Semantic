# Project Schema 与输出结构

## `.swproject` 项目

v04.3 项目使用 `schema_version: 2`。Repository 可读取 v1 并迁移；首次保存迁移项目时保留旧 manifest 备份。保存后结构如下：

```text
demo.swproject/
├─ project.json
├─ project.schema_v1.backup.json       # 仅迁移旧项目后存在
├─ .revisions/<content_sha256>/
│  ├─ stage.json
│  ├─ sensors.json
│  ├─ variants.json
│  ├─ modalities.json
│  ├─ render.json
│  ├─ capture.json
│  ├─ motion.json
│  ├─ semantics.json
│  ├─ execution.json
│  ├─ rigs.json
│  └─ output.json
└─ jobs/<job_id>/job_spec.json
```

`project.json` 是原子更新的 manifest，指向一个完整 revision。保存相同内容是幂等的。

## 主要模型

- `StageReference`：USD 路径、payload 策略和单位覆盖。
- `PluginManifest`、`SensorCapabilities`：插件版本、契约、payload/time/trigger/sync/renderer 能力和 Runtime requirements。
- `SensorDefinition`：`sensor_id`、插件 ID/版本、backend、`prim_path`、同步组、Stage 参数、编译参数和参数来源。
- `RigDefinition`：成员传感器、同步策略、失败策略和可选参考坐标 Prim。
- `SensorBinding`：一个传感器 × 变体的模态选择视图；持久化形式是 `VariantDefinition.modalities_by_sensor`。
- `VariantDefinition`：策略、include/exclude/protected paths 和模态矩阵。
- `RenderProfile`：渲染器、分辨率、warmup、subframes、SPP 与设置覆盖。
- `CaptureSchedule`：physics/capture rate、起始帧、帧数和 Segment 大小。
- `ExecutionPolicy`：分段策略、启动/心跳/无进度/停止超时和 telemetry 间隔。
- `MotionSpec`、`SemanticProfile`、`OutputPolicy`。
- `JobSpec`：编译后的完整快照和 `content_digest`。
- `SegmentSpec`：绑定 Job digest 的不可变帧区间、预期 capture group 和 motion 定位方式。
- `SegmentStatus`：单段 PID/token、心跳、commit、进度、退出码和失败代码。
- `JobStatus`：任务状态、PID/token、两级进度、GPU、ETA、心跳、退出码和失败报告路径。
- `FrameLedgerEntry`：原子采集组的帧、传感器、变体、模态和文件表。
- `BatchLedgerEntry`：`frame + variant + sync_group` 的完整批次标记与成员 Frame key。
- `CaptureContext`、`SensorSample`、`TypedPayload`：Runtime 中的时间、标定、dtype、shape、单位、坐标系和字段描述。

所有 `from_dict` 都拒绝未知字段。ID 只允许字母、数字、点、下划线和连字符，防止配置拼写错误或输出路径逃逸。

## 传感器参数来源

以 `prim_path` 为入口。针孔/鱼眼 Camera 的投影与内参、RTX LiDAR 的 Schema/扫描属性保存在 `stage_parameters` 并标记为 `stage`；用户修改项标记为 `override`；插件默认值标记为 `default`。JobCompiler 同时固化 Stage 原值、合并后的配置值和来源。有效参数快照还记录组合 Stage 的最终值和世界变换。

Runtime 只把插件 Schema 允许且来源为 `override` 的项写入匿名 Session Layer；`resolution` 等纯 Runtime 参数不写 USD。Driver 初始化后从组合 Stage 回读有效参数。源 USD 不会被保存或修改。

## 路径规则

- `omniverse://` 等 URI 保持不变。
- Linux/Windows 绝对路径保持不变。
- 相对 Stage 和 motion 路径以 `.swproject` 目录解析。
- 相对输出根也以 `.swproject` 目录解析。

## 输出

```text
output/<job_id>/
├─ job_spec.json
├─ host_preflight_snapshot.json
├─ runtime_snapshot.json
├─ sensor_effective_parameters.json
├─ semantic_mapping.json
├─ status.json
├─ ledger.jsonl
├─ batch_ledger.jsonl
├─ calibrations/
│  ├─ <sensor_id>.json
│  └─ rigs/<rig_id>.json
├─ segment_plan.json
├─ failure_report.json                 # 仅发生过失败时存在
├─ logs/
│  ├─ supervisor.log
│  └─ job_runner.log
├─ telemetry/
│  ├─ gpu.jsonl
│  ├─ progress.jsonl
│  └─ segment_timing.jsonl
├─ segments/<segment_id>/
│  ├─ segment_spec.json
│  ├─ status.json
│  ├─ host_preflight_snapshot.json
│  ├─ runtime_snapshot.json
│  └─ runtime.log
├─ sensors/<sensor_id>/<variant_id>/
│  ├─ rgb/<frame>.png
│  ├─ semantic_id/<frame>.npy
│  ├─ semantic_color/<frame>.png
│  ├─ depth_linear/<frame>.npy
│  ├─ depth_color/<frame>.png
│  ├─ surface_normal/<frame>.npy
│  ├─ surface_normal_color/<frame>.png
│  ├─ instance_id/<frame>.npy
│  ├─ instance_color/<frame>.png
│  ├─ point_cloud/<frame>.npz
│  ├─ point_cloud_ply/<frame>.ply
│  └─ metadata/<frame>.json
└─ .staging/
```

Segment 不改变数据集目录和 Ledger key。未请求的模态不会创建目录或文件。Frame key 是 `(frame_index, sensor_id, variant_id)`；Batch key 是 `(frame_index, variant_id, sync_group_id)`。Resume 只有在 Ledger 存在、成员完整且条目声明的所有文件通过检查时才跳过；损坏条目会明确失败，避免静默覆盖。已提交 capture group 即使位于未完成 Segment 内也会被逐项协调并补齐 Batch marker。

`sensor_effective_parameters.json` 按传感器保存插件/backend/sync group、`stage_parameters`、`configured_parameters`、`parameter_sources` 和 `effective_parameters`。每帧 metadata 还保存 payload descriptor、序列元数据和标定；`calibrations` 保存独立传感器与 Rig 快照，使数据集脱离项目目录后仍可审计投影、扫描模型、单位和坐标系。

JobSpec 的顶层 frozen dataclass 和内容摘要共同提供完整性：即使调用方修改内部对象，`JobCompiler.verify()` 也会拒绝被篡改的任务。
