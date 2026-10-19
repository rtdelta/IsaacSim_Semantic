# Semantic World Module v04

v04 是一套自包含、模块化的语义数据采集系统，由四个彼此分离的进程职责组成：

- Semantic Capture Studio：独立 Omniverse Kit 项目编辑器，只负责轻量查看 USD、选择传感器和编排任务。
- Same-host Supervisor：在同一台云电脑提交、启动、监控、停止和恢复任务。
- Job Runner：不启动 Kit/RTX，按确定性计划编排 Segment Worker。
- Segment Worker：每段独立启动 headless Isaac Sim/Replicator，执行正式 RGB 与语义采集，段结束后释放整个 Runtime。

Studio 不是完整 Isaac Sim GUI 的插件，正式采集也不依赖 Studio 存活。生产采集推荐使用“Run headless & exit”，让 Studio 退出后只保留 headless Runtime，避免编辑器占用采集期 GPU。

## 当前已实现

- 严格、带版本的纯 Python Project/Job/Status/Ledger 模型；新项目使用 Schema v2，并兼容迁移 v1 项目与 JobSpec。
- 可复用 `.swproject` 项目目录、内容摘要、不可变任务快照和原子保存。
- 独立 Kit Studio，支持 Stage 搜索和选择、相机发现、传感器/变体/模态配置及任务控制。
- v04.4 任务式 Studio：Project、Sensors、Variants、Capture Outputs、Render、Review 六步导航，并把低频参数收进 Advanced。
- 云电脑文件/目录选择器、最近项目、打开项目后自动加载 USD 和自动发现兼容传感器。
- Sensor 插件自动识别和一键启用；专用鱼眼插件优先于通用针孔回退，Sensor ID 自动生成。
- 从标准 Stage/Viewport 当前选择创建 Isolate Variant，自动生成 ID、保护传感器和可选保留全部灯光，并支持 Session Layer 预览。
- Sensor × Variant 采集矩阵；RGB、Depth NPY、Depth Color、Semantic ID、Semantic Color 五种输出完全独立勾选，能力不兼容项直接禁用。
- 输出批量预设、Capability 驱动的更多输出，以及明确的 Sensor × Variant 启用开关。
- Render Preset；新项目默认 `Path Tracing 正式质量`，旧项目保留既有配置，Realtime 只作为显式快速验证选项。
- Review 页面集中显示绑定、真实输出、渲染参数、帧数、Preflight、Job 控制、日志和失败报告。
- USD Camera 参数自动读取；项目只需要以 `prim_path` 指向相机，可对个别参数显式覆盖。
- 所有传感器覆盖只写匿名 USD Session Layer，不修改源 USD；任务输出保存 Stage 原值、配置值、来源和 Runtime 有效值。
- 多个针孔相机只需增加配置实例，无需修改 Coordinator。
- `full_scene` 和 `include_paths` 变体；可见性只写 Session Layer，并保护传感器及祖先路径。
- Pinhole、OpenCV Fisheye、RTX LiDAR 真实 headless Driver。
- RGB、语义 ID/Color、Depth Raw/Color、Surface Normal Raw/Color、Instance ID/Color、Point Cloud NPZ/PLY。
- Plugin Manifest/Capability/参数 Schema 自动发现，新增插件不需要修改 Coordinator。
- `SensorSample`/`TypedPayload` 通用数据契约、传感器/Rig 标定快照、严格内容校验。
- Rig/Sync Group、trigger domain 去重、Atomic Batch Writer 与 Batch Ledger。
- Realtime 与 Path Tracing headless 渲染，Stage 打开后再应用并回读渲染配置。
- 原子 capture group、append-only ledger、文件完整性检查和断点恢复。
- 独立子进程、稳定进程身份、GPU 文件锁、心跳、日志、优雅停止和恢复。
- v04 专属 ABI-safe 启动脚本，阻止 Isaac Python 与系统 `libpython` 混装。
- Sensor Catalog、兼容 Prim 发现、参数 Schema/Effective Preview、Rig Editor，以及通用传感器 × 变体 Modality Matrix。
- 采集前校验、采集组/文件/空间估算和同项目任务历史。
- `segment_frames` 对应真实独立 Isaac Worker，段计划与 JobSpec digest 绑定。
- Ledger 驱动的分段完整性检查；停止、崩溃或重新启动后跳过所有已提交 capture group。
- Worker 心跳、启动超时、无进度看门狗、GPU/进度/段耗时 telemetry。
- 失败自动生成结构化 `failure_report.json`，Studio 和 CLI 均可查看。
- Studio 可配置分段策略与 timeout，并显示 Segment 进度、GPU 显存和 ETA。

RTX LiDAR 属于连续扫描窗口传感器。Runtime 会为包含此类传感器的 Worker 开启连续 Replicator 调度并从零回放 Segment；这保证扫描历史正确，但混合任务会比纯相机任务更慢。

## 目录

```text
apps/                              独立 Kit experience
extensions/semantic.capture.studio Studio UI adapter
src/semantic_world_v04/core        领域模型与协议
src/semantic_world_v04/project     项目存储和路径规则
src/semantic_world_v04/stage       USD 索引与 Kit adapter
src/semantic_world_v04/plugins     Sensor/Variant/Modality 插件
src/semantic_world_v04/compiler    Validator 与 JobCompiler
src/semantic_world_v04/studio      UI-neutral Application Service
src/semantic_world_v04/supervisor  同机进程管理
src/semantic_world_v04/runtime     Headless Isaac Runtime
src/semantic_world_v04/output      原子输出、状态与 Ledger
scripts/                            Studio/Runtime 启动脚本与示例生成器
tests/                              不依赖 Omniverse 的本地测试
docs/                               架构、Schema、插件和验证文档
```

## 云电脑最短使用流程

项目预期整体运行在已经部署 Isaac Sim 的云电脑。本次验证位置是：

```text
/root/gpufree-data/semantic/scripts/260820semantic_worldModule_v04
```

启动 Studio：

```bash
cd /root/gpufree-data/semantic/scripts/260820semantic_worldModule_v04
./scripts/launch_studio.sh
```

在 v04.4 Studio 中：

1. 打开已有项目：在 `Project & Stage` 点击 `Open Existing…`，选择 `.swproject` 文件夹或其中的 `project.json`；项目和 USD Stage 会自动加载。
2. 创建新项目：填写 Project ID，点击 `Choose New Parent…` 选择父目录，Studio 自动生成 `<project_id>.swproject`；再点击 `Choose USD…`、`Create New Project` 和 `Save Project`。空 USD、缺失 USD、非 `.swproject` 目录和覆盖已有项目都会被提前阻止。
3. 在 `Sensors` 勾选自动发现的 USD 相机或 LiDAR；插件和 Sensor ID 由系统确定。
4. 在 `Variants` 从标准 Stage 树或 Viewport 当前选择创建 Isolate Variant，可保留灯光并直接预览。
5. 在 `Capture Outputs` 选择 Sensor，为每个 Variant 勾选是否启用，并独立选择 RGB、Depth NPY、Depth Color、Semantic ID 和 Semantic Color。
6. 在 `Render & Frames` 使用默认 `Path Tracing 正式质量` 或显式选择快速验证预设，再设置帧数和 Segment 大小。
7. 在 `Review & Run` 查看完整摘要、执行 `Validate` 和 `Preflight`。
8. 选择 `Run Headless & Exit`。Studio 会提交独立进程后退出。

不要继续使用缺少 USD 路径的旧测试草稿 `example.swproject`；云端现有的有效项目是 `/root/gpufree-data/semantic/projects/my_capture.swproject`。

Rigs、Sensor Overrides、Motion、Semantic Mapping、Execution Policy 和 Plugin Catalog 位于 `Advanced`。

不使用 UI 时，可通过 CLI 管理任务：

```bash
export PYTHONPATH="$PWD/src"

# 编译项目
/root/isaacsim/python.sh -m semantic_world_v04.cli.project_cli \
  compile /path/to/example.swproject --job-id job-demo

# 提交并启动已编译 JobSpec
/root/isaacsim/python.sh -m semantic_world_v04.cli.supervisor_cli \
  run /path/to/example.swproject/jobs/job-demo/job_spec.json

# 查询、分段、失败报告、日志、停止、恢复
/root/isaacsim/python.sh -m semantic_world_v04.cli.supervisor_cli \
  status job-demo --output-root /path/to/output
/root/isaacsim/python.sh -m semantic_world_v04.cli.supervisor_cli \
  segments job-demo --output-root /path/to/output
/root/isaacsim/python.sh -m semantic_world_v04.cli.supervisor_cli \
  failure-report job-demo --output-root /path/to/output
/root/isaacsim/python.sh -m semantic_world_v04.cli.supervisor_cli \
  logs job-demo --output-root /path/to/output --lines 50
/root/isaacsim/python.sh -m semantic_world_v04.cli.supervisor_cli \
  stop job-demo --output-root /path/to/output
/root/isaacsim/python.sh -m semantic_world_v04.cli.supervisor_cli \
  resume job-demo --output-root /path/to/output

# 完成后独立复核 Ledger、文件、分辨率、NPY 和 renderer readback
python3 scripts/validate_dataset.py /path/to/output/job-demo
```

正式 Runtime 不应直接调用普通 Python。Supervisor 默认启动轻量 Job Runner，后者再启动独立 Segment Worker：

```bash
./scripts/launch_job_runner.sh --job-spec ... --output-dir ... --gpu-lock ...
./scripts/launch_runtime.sh --job-spec ... --segment-spec ... --output-dir ... --gpu-lock ...
```

## Python API

```python
from pathlib import Path
from semantic_world_v04.studio import StudioController

studio = StudioController()
project = studio.open_project(Path("/data/demo.swproject"))
issues = studio.validate()
if issues:
    raise RuntimeError("\n".join(map(str, issues)))

job = studio.compile_job(job_id="job-demo")
status = studio.run_headless(job_id="job-demo-2")
print(status.state, status.pid)
```

生产工作流 API 还包括：

- `set_render_profile`、`set_capture_schedule`、`set_execution_policy`、`set_motion_spec`、`set_semantic_profile`
- `set_sensor_overrides`、`set_modalities`
- `sensor_plugin_catalog`、`discover_sensors`、`add_sensor_from_stage`、`effective_sensor_preview`
- `discover_sensor_candidates`、`set_stage_sensor_selected`
- `capture_matrix`、`set_binding_enabled`、`set_modality_enabled`、`apply_modality_preset`
- `create_isolate_variant`、`duplicate_variant`、`capture_plan_summary`
- `render_presets`、`apply_render_preset`、`current_render_preset_id`
- `add_rig`、`delete_rig`、`clear_sensor_overrides`
- `preflight_summary`、`list_jobs`、`list_segments`、`read_failure_report`

更底层的稳定入口包括：

- `ProjectRepository.save/load`
- `ProjectValidator.validate`
- `JobCompiler.compile/verify`
- `SameHostSupervisor.submit/start/status/stop/resume/tail_logs`
- `StageIndex.search/by_type/children`
- `PluginRegistry.sensor/variant/modality`

## 本地测试

本地不需要 Omniverse：

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests -v
python -m compileall -q src extensions scripts tests
```

当前结果：79/79 通过。Kit、USD、GPU、鱼眼、RTX LiDAR、Realtime/Path Tracing、Schema v2 和 v04.4 Studio 工作流验证结果见 `docs/Validation/`。

## 重要说明

- 本目录是源码真相；云电脑用于部署和集成验证。
- 可执行代码不导入、不调用任何旧版本项目文件。
- `Run + monitor` 会保留 Studio，适合短调试；正式长任务推荐退出 Studio。
- v04.4 已自动验证 7 个页面、文件/目录选择器、真实 USD 发现和 Path Tracing 数据输出；可见 UI 的逐项人工视觉验收仍建议由使用者完成。
- 输出损坏时 Runtime 会明确失败，不会在已有 ledger 后静默覆盖文件。
- `scripts/validate_dataset.py` 可在任务完成后独立复核所有 capture group 与产物头信息。

延伸阅读：

- `docs/Architecture/01_架构与模块链路.md`
- `docs/Architecture/02_ProjectSchema与输出结构.md`
- `docs/Architecture/03_插件开发指南.md`
- `docs/Troubleshooting/故障处理.md`
- `examples/README.md`
