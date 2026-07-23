# 语义相机脚本项目代码实现与更新修改方案

> 2026-07-23 更新：本文记录早期渲染与同步改造设计。当前业务启动入口已经收敛为唯一的
> `--config <json>`；本文原 CLI 字段均应理解为业务配置 JSON 中的下划线字段。

## 1. 文档目的

本文档给出 `260714_01semantic_worldModule` 的代码级修正方案，目标是在允许显式选择任意有效 `UsdGeom.Camera`、保留固定步长物理、RGB 与语义联合输出等现有能力的前提下，解决当前采集管线中已经确认或高度怀疑的以下问题：

1. 脚本输出与 GUI Synthetic Data Recorder 缺少同条件、可复现的 A/B 基线。
2. RenderProduct 的 Hydra 更新在预热和每次采集后被关闭，底层 viewport/RenderProduct 资源可能反复注销，导致 RTX/DLSS 时序历史无法连续积累。
3. GUI 使用 `rt_subframes=16`，脚本当前默认仅为 4，且没有形成显式、可审计的渲染质量配置。
4. `SimulationApp` 强制使用 `RaytracedLighting`，随后又无条件调用 `reset_render_settings()`，请求值、Stage 值与最终生效值没有被统一管理和保存。
5. `capture(frame_id, simulation_time)` 丢弃外部帧上下文，而 Writer 使用自己的内部计数器，RGB、语义图、运动状态与时间戳之间缺少帧级完成确认。
6. Timeline、物理步进与 Replicator step 之间没有显式的“冻结采集屏障”，无法通过代码不变量证明 RT subframes 期间场景没有继续推进。
7. Stage 存在缺失 DomeLight 纹理、负质量或无效惯量、Xform 类型冲突等问题，但当前启动流程只输出警告并继续采集。
8. 每帧出现 OmniGraph/WriterSyncGate 循环连接警告，尚未隔离到自定义 Writer、重复启停 RenderProduct 或 Isaac Sim 内部图构建中的哪一层。
9. 当前输出缺少 Stage 哈希、layer 栈、外部资产、有效渲染参数和完整相机光学参数，无法可靠复现实验。

本文档只定义修改方案，不直接包含本轮业务代码修改。

---

## 2. 修正目标与非目标

### 2.1 修正目标

- 每次运行通过业务配置中的 `camera_prim_path` 显式选择一台有效 Camera，不限制其父级。
- 整段采集使用同一个 RenderProduct、同一组 annotator 和同一个 Writer attach 生命周期。
- 每一帧都具有明确且一致的 `frame_id`、数据集时间、Timeline 时间、物理步号、相机矩阵和运动状态。
- RT subframes 渲染期间场景变换和 Timeline 时间保持冻结。
- 渲染质量由显式 profile 决定，不依赖 GUI 用户目录中的持久化设置。
- 对外部资产、物理参数、相机、语义 schema 和渲染设置执行启动前检查。
- 输出目录包含足以复现本次运行的配置快照和资产指纹。
- 修正后仍保持 RGB、稳定 dataset semantic ID、semantic color、runtime ID 和逐帧 metadata 的输出结构。

### 2.2 非目标

- 不在相机、场景状态和渲染设置未匹配时用不同 Camera 的结果代替同条件画质基线。
- 不把 1280×720 文件尺寸本身当成内部渲染分辨率或画质保证。
- 不在没有匹配相机和匹配场景状态的情况下，用整图文件大小或整图锐度判定修正是否成功。
- 不在管线尚未稳定前直接重训 Gaussian Splat 资产。
- 不在第一版正确性修正中优先优化吞吐量或异步写盘速度。

---

## 3. 总体设计

建议保留现有模块化结构，并新增 `RenderProfile` 与 `StagePreflight` 两个独立责任模块：

```text
SimulationOrchestrator
├─ StagePreflight
│  ├─ layer/reference/payload/texture 检查
│  ├─ Camera 与 Semantics 检查
│  └─ Physics/Xform 检查
├─ RenderProfileManager
│  ├─ 加载并校验请求配置
│  ├─ 应用渲染设置
│  └─ 回读实际生效设置
├─ WorldScheduler
│  ├─ 固定步长物理
│  ├─ 数据集时间与 Timeline 时间
│  └─ capture freeze barrier
├─ ExcavatorJointMotion
│  └─ 轨迹采样与 Drive target
└─ SemanticCameraScheduler
   ├─ 单一持久 RenderProduct
   ├─ 无输出预热
   ├─ 帧上下文与采集触发
   └─ SemanticDatasetWriter 完成确认
```

推荐的正式采集状态机：

```text
APP_STARTED
  -> STAGE_LOADED
  -> PREFLIGHT_PASSED
  -> RENDER_PROFILE_APPLIED
  -> WORLD_INITIALIZED
  -> INITIAL_STATE_READY
  -> RENDER_PRODUCT_READY
  -> RENDER_WARMED
  -> CAPTURING
  -> WRITES_COMPLETED
  -> CLOSED
```

任何阶段失败都应中止采集并在输出目录写入失败原因；不得在严重 Stage 或物理错误下继续生成正式数据。

---

## 4. 文件与模块变更总览

| 文件 | 变更类型 | 主要内容 |
|---|---|---|
| `simulation_orchestrator.py` | 重点修改 | 初始化顺序、单配置入口、render profile、preflight、帧调度、运行取证 |
| `capture_launch_config.py` | 新增 | 严格加载版本化业务配置、校验字段、解析相对路径 |
| `semantic_capture_custom.py` | 重点修改 | 持久 RenderProduct、预热、冻结采集、逐帧完成确认 |
| `semantic_dataset_writer.py` | 重点修改 | 外部 CaptureContext、显式帧号、ack、数据一致性检查 |
| `world_scheduler.py` | 重点修改 | 明确 pause/resume/freeze、目标步号、双时间轴、时间不变量 |
| `validate_semantic_output.py` | 扩展 | 输出 schema、帧同步、渲染快照和时序校验 |
| `excavator_joint_motion.py` | 小幅扩展 | 初始目标应用、实际关节/刚体状态校验、更多运行元数据 |
| `run_capture_remote.sh` | 小幅扩展 | 只接受 `--config`、配置路径绝对化；保留隔离 HOME |
| `render_profile.py` | 新增 | 渲染配置数据模型、应用、回读、差异检查 |
| `stage_preflight.py` | 新增 | Stage、资产、相机、物理和语义启动前检查 |
| `capture_context.py` | 可新增 | 跨 Scheduler/Writer 使用的不可变帧上下文模型 |
| `compare_render_quality.py` | 新增 | 匹配帧画质比较，不参与生产采集 |
| `configs/render_*.json` | 新增 | 可复现的质量 profile 与 A/B profile |
| `tests/` | 扩展 | 调度、profile、上下文、preflight、验证器测试 |

`capture_context.py` 也可先放在 `semantic_capture_custom.py` 中；当 Writer、验证器和 orchestrator 都需要引用时再独立成文件。

---

## 5. `simulation_orchestrator.py` 修改方案

### 5.1 当前问题位置

当前关键行为位于：

- `SimulationApp` 启动配置：约第 118～124 行。
- Stage 加载后的 `reset_render_settings()`：约第 154 行。
- Camera Scheduler 初始化与预热：约第 176～190 行。
- 每帧先推进 6 个物理步、随后采集：约第 219～246 行。
- `run_config.json` 信息不足：约第 193～211 行。

### 5.2 单配置入口

当前命令行只接受：

```text
--config <capture-config.json>
```

Stage、Camera、render profile、采集模式、初始帧、pre-roll、严格性、subframes、预热和
headless 等全部业务字段均在 JSON 中配置。入口拒绝其他业务参数和额外 Kit 参数，不允许
命令行覆盖配置文件。

### 5.3 初始化顺序重排

建议将 `main()` 改造成以下控制流：

```python
args = parse_and_validate_args()
profile = RenderProfile.load(args.render_profile, overrides=args)

app = SimulationApp(profile.launch_config(headless=args.headless))
stage = open_stage_and_wait(args.usd)

preflight_report = StagePreflight(stage, args).run()
preflight_report.raise_if_blocking(strict=args.strict_stage)

effective_render_settings = RenderProfileManager(app, stage).apply_and_snapshot(profile)

world = WorldScheduler(...)
world.initialize()

motion = ExcavatorJointMotion(...)
motion.initialize()
motion.apply_initial_targets()

run_pre_roll_if_requested(world, motion)
world.freeze_for_capture()

camera = SemanticCameraScheduler(...)
camera.initialize_render_product()
camera.warmup(args.warmup_render_frames)
camera.attach_writer()

write_run_manifest(...)
run_capture_loop(...)
validate_completion(...)
```

关键约束：

1. 渲染 profile 必须在 RenderProduct 创建之前应用。
2. 预热必须使用最终相机、最终 RenderProduct 和正式采集使用的 renderer。
3. Writer 在预热之后 attach，避免预热帧进入正式输出，也减少 Writer 图在预热阶段参与调度的复杂性。
4. Timeline 在进入正式 capture 前必须有显式状态检查。
5. `reset_render_settings()` 不再无条件执行。

### 5.4 处理 `reset_render_settings()`

推荐删除当前无条件调用，改成由 `RenderProfileManager` 完成以下操作：

1. 记录 Stage 打开后的初始设置。
2. 根据 profile 应用目标设置。
3. 创建 RenderProduct 前回读设置。
4. 如果关键请求值未生效，立即失败。

如果某个 renderer 必须通过 `SimulationApp.launch_config` 设置，则 profile 同时生成 launch config，并在 Stage 加载后只补充其余设置，不再用一次全局 reset 覆盖 Stage 状态。

### 5.5 正式帧时间定义

推荐将默认规则定义为：

```text
frame_id = i
dataset_time = i / capture_fps
physics_step = pre_roll_steps + i * steps_per_capture
```

这样 `frame_0000` 对应数据集时间 0.0。推荐流程：

```python
if args.capture_initial_frame:
    capture_frame(frame_id=0, dataset_time=0.0)

for frame_id in range(1, args.frames):
    world.advance_exact_steps(steps_per_capture, motion)
    capture_frame(frame_id, frame_id / capture_fps)
```

如果选择保留旧行为，则必须明确记录：

```text
frame_id = i
dataset_time = (i + 1) / capture_fps
```

两种规则不能混用，验证器必须根据 `capture_initial_frame` 检查。

### 5.6 pre-roll 双时间轴

物理稳定阶段不能悄悄混入数据集时间。建议记录两个时间：

- `timeline_time`：Isaac Sim Timeline 的实际时间。
- `dataset_time`：正式数据集从 0 开始的逻辑时间。

pre-roll 期间保持轨迹初始目标，不推进 trajectory time。pre-roll 结束后，将该物理状态定义为 `dataset_time=0`，但保留真实 `timeline_time` 供取证。

### 5.7 `run_config.json` 升级为 manifest v2

建议至少增加：

```json
{
  "schema_version": 2,
  "status": "running|complete|failed",
  "command_line": [],
  "source_stage": {
    "path": "...",
    "sha256": "...",
    "layers": [],
    "external_assets": []
  },
  "render": {
    "profile_path": "...",
    "profile_sha256": "...",
    "requested": {},
    "effective": {},
    "differences": []
  },
  "camera": {
    "path": "...",
    "resolution": [1280, 720],
    "intrinsics": {},
    "optics": {}
  },
  "timing": {
    "physics_hz": 60,
    "capture_fps": 10,
    "steps_per_capture": 6,
    "capture_initial_frame": true,
    "pre_roll_steps": 0
  },
  "software": {},
  "hardware": {},
  "preflight": {},
  "warnings": []
}
```

运行开始先写入 `status=running`；成功完成后原子更新为 `complete`；异常退出时写入 `failed` 和异常摘要。这样可以区分完整数据集与中途退出的目录。

---

## 6. 新增 `render_profile.py`

### 6.1 数据模型

建议定义不可变 profile：

```python
@dataclass(frozen=True)
class RenderProfile:
    name: str
    renderer: str
    antialiasing: str
    dlss_mode: str | None
    render_scale: float
    rt_subframes: int
    motion_blur: bool
    depth_of_field: bool
    denoiser: bool | None
    exposure_mode: str
    settings: dict[str, Any]
```

另定义生效快照：

```python
@dataclass(frozen=True)
class EffectiveRenderSettings:
    renderer: str
    values: dict[str, Any]
    unresolved_keys: tuple[str, ...]
    mismatches: tuple[SettingMismatch, ...]
```

### 6.2 责任边界

`RenderProfileManager` 只负责：

- 校验 profile 值；
- 生成 `SimulationApp` launch config；
- 在 Stage 加载后设置 Kit/RTX 参数；
- 回读最终值；
- 区分 required 与 best-effort 设置；
- 输出 requested/effective 差异。

它不负责创建 RenderProduct，也不负责物理或 Writer。

### 6.3 第一批 profile

建议新增：

```text
configs/render_gui_parity_720p.json
configs/render_quality_dlss_720p.json
configs/render_quality_native_720p.json
configs/render_diagnostic_minimal_720p.json
```

用途：

- `gui_parity`：使用从 GUI 同次基准实验中导出的有效设置。
- `quality_dlss`：RaytracedLighting、DLSS Quality、16 subframes，作为第一版生产候选。
- `quality_native`：原生分辨率 AA，用于判断 720p 下 DLSS 是否导致 Gaussian 细节变软。
- `diagnostic_minimal`：关闭非必要后处理，用于定位原始渲染结果。

renderer 名称和底层 setting key 必须以 Isaac Sim 6.0.1 运行时实际可接受值为准。配置加载阶段不能静默接受拼写错误或未知枚举。

### 6.4 设置选择原则

- 初始质量基线使用 `rt_subframes=16`，与已确认 GUI Recorder 配置对齐。
- DLSS 的第一候选为 Quality，但不能未经 A/B 就认定是 Gaussian Splat 在 720p 下的最终最优解。
- motion blur、光学 DOF 和 auto exposure 在语义数据 profile 中显式关闭或固定。
- 内部 render scale 必须显式记录；输出分辨率 1280×720 不等于内部渲染也是 1280×720。
- Path Tracing 只作为兼容性允许时的参考上限，不直接承诺为生产模式；需要先验证 Gaussian/Particle Field、语义 annotator 和性能是否完整支持。

---

## 7. 新增 `stage_preflight.py`

### 7.1 报告模型

```python
@dataclass(frozen=True)
class PreflightIssue:
    severity: Literal["error", "warning", "info"]
    code: str
    prim_path: str | None
    message: str

@dataclass
class PreflightReport:
    issues: list[PreflightIssue]
    resolved_assets: list[AssetRecord]
    semantic_prim_count: int
```

### 7.2 检查内容

Stage 层面：

- 根 layer 和所有 sublayer 可读取；
- reference、payload 和纹理路径可解析；
- 保存 path、size、mtime 和 SHA-256；
- 检测缺失 DomeLight HDR；
- 检测打开后仍处于 loading 的资产。

相机层面：

- Camera prim 存在且类型正确；
- Camera Prim path 是显式提供的绝对路径，不限制其父级；
- 世界矩阵有限且可逆；
- focal length、aperture、clipping range 合法；
- 记录 focusDistance、optical fStop、exposure 与 shutter 属性；
- 分辨率和相机 aperture 的宽高比差异产生 warning。

语义层面：

- 至少存在一个 `SemanticsLabelsAPI`；
- mapping 中的类都能在 Stage 中找到；
- Stage 中未映射的 class 在 strict 模式下报错；
- semantic filter 与 mapping schema 兼容。

物理层面：

- 四个目标 Joint 存在且类型正确；
- body0/body1 关系有效；
- mass 为有限正数；
- inertia 合法或具备可计算惯量的 collision；
- 关节 limit 和 Drive target 有效；
- 没有冲突的嵌套 rigid body；
- XformOp 的声明类型和值类型一致；
- 对已知 `rotateZYX` 类型冲突给出阻断性错误。

### 7.3 严格模式

生产运行默认 `--strict-stage`。以下问题必须阻断：

- 缺失被引用资产或纹理；
- Camera 无效；
- 没有语义标签；
- mapping 不完整；
- 负质量、零质量或无效惯量；
- Joint/body 关系无效；
- 关键渲染设置无法生效。

诊断模式可允许部分错误继续，但 manifest 必须标记 `non_production=true`。

---

## 8. `world_scheduler.py` 修改方案

### 8.1 当前问题

当前 `step()` 只是调用一次 `self._app.update()` 并增加内部计数，没有显式证明：

- Timeline 是否恰好推进一个 physics dt；
- Replicator step 是否又推进了 Timeline；
- RT subframes 前后 Timeline 是否保持不变；
- pause/resume 的所有状态转换是否合法。

### 8.2 增加状态机

```python
class WorldState(Enum):
    INITIALIZED = auto()
    RUNNING = auto()
    FROZEN = auto()
    STOPPED = auto()
```

公开接口建议为：

```python
start()
advance_exact_steps(count, before_step_callback=None)
freeze_for_capture() -> FrozenWorldSnapshot
assert_still_frozen(snapshot)
resume_after_capture()
stop()
```

禁止 Camera Scheduler 自己控制物理时间。Camera Scheduler 只接收已经冻结的 snapshot。

### 8.3 冻结快照

```python
@dataclass(frozen=True)
class FrozenWorldSnapshot:
    physics_step: int
    dataset_time: float
    timeline_time: float
    stage_time_code: float
```

`assert_still_frozen()` 至少比较：

- Timeline time；
- physics step；
- 关键相机和刚体世界矩阵，可在诊断模式启用；
- 允许浮点误差，但不能允许一个完整 physics dt 的变化。

### 8.4 防止双重步进

每次 `rep.orchestrator.step()` 前后记录 Timeline time。如果在 `delta_time=0` 和冻结状态下仍发生变化，应立即中止并记录为 scheduler 错误，而不是继续生成错位数据。

---

## 9. `semantic_capture_custom.py` 修改方案

### 9.1 当前问题位置

- 第 83 行硬编码 DLSS setting。
- 第 85～89 行创建 RenderProduct。
- 第 98 行在预热前 attach Writer。
- 第 107～110 行预热后关闭 Hydra 更新。
- 第 116～122 行每次采集开关 Hydra 更新。
- 第 115 行丢弃 `frame_id` 与 `simulation_time`。

### 9.2 类状态机

```python
class CameraSchedulerState(Enum):
    CREATED = auto()
    RENDER_PRODUCT_READY = auto()
    WARMED = auto()
    WRITER_ATTACHED = auto()
    CAPTURING = auto()
    CLOSED = auto()
```

每个公开方法校验状态，避免重复 initialize、重复 attach、未 warmup 就 capture 或 close 后继续使用。

### 9.3 拆分初始化职责

将当前 `initialize()` 拆为：

```python
resolve_and_validate_camera()
initialize_render_product()
warmup(render_frames)
attach_writer()
```

RenderProfile 不再由 Camera Scheduler 设置。删除：

```python
carb.settings.get_settings().set("rtx/post/dlss/execMode", 2)
```

该设置迁移到 `RenderProfileManager`，避免 Camera 模块同时承担全局 renderer 配置。

### 9.4 RenderProduct 持久化

推荐生命周期：

```python
self._render_product = rep.create.render_product(...)
self._render_product.hydra_texture.set_updates_enabled(True)

# warmup、物理推进、全部 capture 期间均不关闭

self._writer.detach()
self._render_product.destroy()
```

必须删除 warmup 和 capture 末尾的 `set_updates_enabled(False)`。日志验收要求：正式运行中 RenderProduct/viewport 只注册一次，直到 close 才注销一次。

### 9.5 预热

预热必须满足：

- 使用正式 RenderProduct；
- 使用最终相机世界姿态；
- Timeline 冻结；
- Writer 尚未 attach，或具备明确的“丢弃预热输出”机制；
- 预热结束后 RenderProduct 不销毁、不禁用。

伪代码：

```python
def warmup(self, render_frames: int, frozen_world: FrozenWorldSnapshot) -> None:
    self._require_state(RENDER_PRODUCT_READY)
    for _ in range(render_frames):
        self._render_one_temporal_frame_without_writer()
        self._world_assertion(frozen_world)
    self._state = WARMED
```

具体使用 `app.update()` 还是无 Writer 的 Replicator render step，应通过一帧日志和 RenderProduct 持续性测试确认；不变量是必须真正更新同一个 Hydra texture，并且不能触发正式 Writer 帧号。

### 9.6 帧级 capture

建议接口：

```python
def capture(
    self,
    context: CaptureContext,
    frozen_world: FrozenWorldSnapshot,
) -> CaptureReceipt:
    ...
```

伪代码：

```python
self._require_state(WRITER_ATTACHED, CAPTURING)
self._assert_render_product_alive()
self._writer.arm_capture(context)

timeline_before = frozen_world.timeline_time
rep.orchestrator.step(
    rt_subframes=self._rt_subframes,
    delta_time=0.0,
    pause_timeline=True,
)
rep.orchestrator.wait_until_complete()

receipt = self._writer.require_completed(context.frame_id)
self._assert_timeline_unchanged(timeline_before)
self._assert_output_files_exist(receipt)
return receipt
```

`pause_timeline=True` 的最终组合需要在 Isaac Sim 6.0.1 上用集成测试确认；如果外部已经暂停 Timeline，API 的最佳参数组合不同，也必须以“前后时间完全不变”为验收条件，而不是依赖参数名称推断。

### 9.7 第一版使用 blocking frame sync

第一版每帧 `wait_until_complete()`，优先保证正确性。未来优化为 queued 模式时，必须满足：

- CaptureContext 使用 FIFO 队列；
- Writer 每次回调只消费一个 context；
- 队列不能 underflow 或 overflow；
- close 前所有 context 都收到 receipt；
- motion state 只能在 receipt 完成后标记为已提交。

---

## 10. 新增 `CaptureContext` 与 `CaptureReceipt`

建议的数据模型：

```python
@dataclass(frozen=True)
class CaptureContext:
    frame_id: int
    dataset_time: float
    timeline_time: float
    physics_step: int
    camera_path: str
    camera_world_transform: tuple[float, ...]
    body_world_transforms: dict[str, tuple[float, ...] | None]
    joint_targets: dict[str, float]

@dataclass(frozen=True)
class CaptureReceipt:
    frame_id: int
    rgb_path: str
    semantic_id_path: str
    semantic_color_path: str
    runtime_id_path: str | None
    metadata_path: str
```

CaptureContext 在触发渲染前生成且不可变。Writer 不再自行推断 simulation time，也不再使用与 orchestrator 无关的内部帧号作为文件名真值。

---

## 11. `semantic_dataset_writer.py` 修改方案

### 11.1 使用外部 frame ID

将：

```python
self._frame_id = 0
```

改为：

```python
self._pending_contexts: deque[CaptureContext] = deque()
self._completed: dict[int, CaptureReceipt] = {}
```

提供：

```python
arm_capture(context)
require_completed(frame_id)
pending_count
completed_count
```

`write(data)` 开始时必须消费一个 pending context；没有 pending context 时收到回调属于错误。同一 frame ID 重复写入也属于错误。

### 11.2 RGB 数据检查

保存前检查：

- shape 为 `(height, width, 3)` 或明确允许的 RGBA；
- dtype 为 `uint8`；
- 数组连续或在写出前转为 contiguous；
- 实际尺寸与 semantic runtime ID 完全相同；
- Alpha 如果存在，记录是否全不透明；
- 不进行 resize、色彩转换、锐化或 JPEG 编码。

### 11.3 metadata v2

逐帧 metadata 至少包含：

```json
{
  "schema_version": 2,
  "frame_id": 2,
  "dataset_time": 0.2,
  "timeline_time": 0.3666666667,
  "physics_step": 22,
  "render_product": "...",
  "resolution": [1280, 720],
  "camera": {
    "path": "...",
    "world_transform": []
  },
  "files": {},
  "runtime_id_mapping": {},
  "dataset_pixel_counts": {},
  "unknown_labels": []
}
```

如果后端成本可接受，可在全部文件写完后生成独立 `checksums.json`；不要在 Writer 回调的热路径中同步计算大文件哈希。

### 11.4 Writer graph cycle 隔离

不能直接假设循环警告来自 Writer 某一行。实现以下集成测试矩阵：

1. 单 RenderProduct + BasicWriter + RGB。
2. 单 RenderProduct + BasicWriter + RGB/semantic。
3. 单 RenderProduct + CustomWriter + RGB。
4. 单 RenderProduct + CustomWriter + RGB/semantic。
5. 持久 Hydra 与旧式反复开关 Hydra 对比。

定位后再决定：

- 修正 annotator attach 顺序；
- 调整 `data_structure`；
- 避免重复 attach；
- 或确认是 Isaac Sim 版本问题并采用已验证的替代写法。

正式发布标准是无 graph-cycle 警告。

---

## 12. `excavator_joint_motion.py` 修改方案

现有轨迹解析、SHA-256、关节限制和线性插值逻辑可以保留。

建议增加：

```python
apply_initial_targets()
validate_runtime_bodies()
get_actual_joint_state()
```

### 12.1 初始目标

初始化完成后显式写入 `t=0` 的 Drive target，不能只读取 USD 当前 target。pre-roll 阶段持续保持这些目标。

### 12.2 目标值与实际状态分离

当前 `get_state()` 主要记录 target 和 body transform。建议明确区分：

- `target_degrees`：轨迹要求值；
- `actual_joint_position`：物理系统实际值，如 API 可稳定获得；
- `tracking_error`：目标与实际值差异；
- `body_world_transform`：实际刚体姿态。

这能判断模糊/构图变化来自正常轨迹、物理滞后还是非法质量/惯量造成的抖动。

---

## 13. Stage overlay 修改方案

Stage 和物理修正应尽量通过新的 capture overlay 完成，不直接修改原始资产。

建议新增或扩展：

```text
configs/Sim_FangShan_02_capture_quality_overlay.usda
```

其中只包含采集所需 override：

- 修复四个运动刚体的质量与惯量；
- 必要时补充合法 collision；
- 修复 `rotateZYX` 属性类型冲突；
- 修复或移除失效 DomeLight HDR 路径；
- 如果需要，增加非物理的 `SemanticCameraRig` Xform；
- 保留语义 label override。

CameraRig 建议结构：

```text
/root/Xform/operator_cab_mesh
└─ SemanticCameraRig
   └─ Camera_01
```

CameraRig 不应用 rigid body，只继承已经合法求解的驾驶室世界变换。单纯增加 CameraRig 不能替代对父级负质量和无效惯量的修复。

修复 DomeLight 后会改变亮度和数据分布，修复物理后会改变设备姿态，因此输出必须升级为新的数据集版本，不能与旧数据无标记混用。

---

## 14. `validate_semantic_output.py` 修改方案

### 14.1 保留现有检查

- 文件数量；
- semantic ID dtype/shape；
- semantic color 可由 dataset ID 完整重建；
- unknown label；
- 关节目标范围；
- 刚体和相机确实运动。

### 14.2 新增结构一致性检查

- `run_config.schema_version == 2`；
- manifest 状态为 `complete`；
- 每个 frame ID 恰好存在一组文件；
- Writer metadata、motion state、文件名 frame ID 一致；
- dataset time、timeline time、physics step 单调且符合调度公式；
- RGB 与 semantic 分辨率完全一致；
- requested/effective render setting 无阻断性 mismatch；
- CaptureReceipt 数量等于预期帧数；
- pending Writer context 为 0；
- preflight 没有 error；
- 日志没有被分类为阻断项的 PhysX、USD、OmniGraph 错误。

### 14.3 静态模式与运动模式分开验证

当前验证器要求刚体和相机必须移动，这会让静态 A/B 模式必然失败。建议根据 `capture_mode` 分支：

- `static`：要求相机和关键刚体矩阵在全部帧中保持不变。
- `motion`：要求期望运动的 body 发生变化，并检查最大单步变化是否超过合理阈值。

---

## 15. 新增 `compare_render_quality.py`

该脚本只用于匹配帧的质量验收，不参与生产采集。

输入：

```text
--reference <GUI 或基准 RGB>
--candidate <脚本 RGB>
--reference-metadata <optional>
--candidate-metadata <optional>
--roi <optional x,y,w,h>
--output-report <json>
```

比较前必须检查：

- 相同分辨率；
- 相同相机路径或相同世界矩阵；
- 相同相机内参；
- 相同 Stage hash；
- 相同时间与关键刚体矩阵。

不满足时输出 `not_comparable`，不生成误导性总分。

指标建议：

- RGB 绝对差与平均亮度；
- SSIM/PSNR；
- 匹配 ROI 的 Laplacian variance；
- 梯度幅值和边缘扩展宽度；
- near-black 比例；
- 可选语义边界附近的 RGB 梯度统计；
- 相邻运动帧的鬼影/双边诊断。

整图锐度只能作为辅助指标，因为大面积黑色或平坦地面会显著改变结果。

---

## 16. `run_capture_remote.sh` 修改方案

现有隔离运行目录应保留：

```text
.runtime/home
.runtime/cache
.runtime/config
.runtime/cuda_cache
.runtime/optix_cache
```

这样可以避免 GUI 用户配置污染脚本运行。

建议补充：

- 严格检查参数形式只能是 `--config <json>`；
- 在切换隔离工作目录前把配置路径转成绝对路径；
- 保存 Isaac Sim 启动入口和关键环境变量名称；
- 保持 `exec`，确保退出码来自 Python 主程序；
- 不在 shell 中暗中覆盖 renderer、DLSS 或 subframes。

`rt_subframes` 和 `warmup_render_frames` 在业务配置中可设为 `null`，表示沿用 render
profile；最终有效值必须写入 `run_config.json`。

---

## 17. 测试方案

### 17.1 单元测试

新增：

```text
tests/test_render_profile.py
tests/test_capture_context.py
tests/test_world_scheduler_math.py
tests/test_stage_preflight_rules.py
tests/test_output_manifest.py
```

覆盖内容：

- profile 缺字段、错误枚举、覆盖优先级；
- CaptureContext frame ID 重复、队列 underflow/overflow；
- frame/time/physics step 映射；
- pre-roll 双时间轴；
- preflight issue 分级和 strict 行为；
- manifest running/complete/failed 状态；
- static/motion 验证器分支。

### 17.2 Isaac Sim 集成测试

最小测试序列：

1. 静态 Camera_03，3 帧，16 subframes。
2. 静态 Camera_01，3 帧，16 subframes。
3. 运动 Camera_01，3 帧，60 Hz/10 FPS。
4. 运动 Camera_01，10 帧，验证 Writer 队列和时间。
5. BasicWriter/CustomWriter graph-cycle 隔离矩阵。
6. 故意提供缺失 HDR、负质量和错误 mapping，验证 strict preflight 会失败。

### 17.3 画质 A/B 矩阵

| 测试 | 相机 | 运动 | RenderProduct | subframes | AA | 目的 |
|---|---|---:|---|---:|---|---|
| A | Camera_03 | 否 | 持久 | 16 | GUI 对齐 | 验证 GUI/脚本渲染基线 |
| B | Camera_01 | 否 | 持久 | 16 | DLSS Quality | 隔离视角与 Gaussian 资产 |
| C | Camera_01 | 是 | 持久 | 4/8/16 | DLSS Quality | 选择子帧数 |
| D | Camera_01 | 否 | 持久 | 16 | DLSS/TAA/native | 判断 720p 重建柔化 |
| E | Camera_01 | 是 | 持久 | 16 | 最终候选 | 完整生产验收 |

旧式反复关闭 Hydra 的行为只保留在临时诊断分支用于证明差异，不应保留为正式运行选项。

---

## 18. 分阶段实施与提交边界

### 阶段 0：可观测性，不改变采集视觉行为

实施：

- manifest v2；
- Stage、mapping、trajectory 哈希；
- 相机完整状态；
- requested/effective render snapshot；
- 日志错误分类。

验收：旧采集逻辑仍能运行，新增元数据完整。

### 阶段 1：静态基准模式

实施：

- `capture_mode=static`；
- `capture_initial_frame`；
- Camera_03/Camera_01 固定姿态基准；
- `compare_render_quality.py`。

验收：同一静态状态可重复采集，并能证明 GUI/脚本样本是否可比较。

### 阶段 2：RenderProduct 生命周期修正

实施：

- Hydra updates 全程开启；
- RenderProduct 只创建和销毁一次；
- 预热移到最终相机状态之后；
- Writer 在预热后 attach。

验收：日志中无逐帧 viewport 注册/销毁，静态和运动画质均无回退。

### 阶段 3：帧级同步与调度修正

实施：

- CaptureContext/Receipt；
- World freeze barrier；
- 每帧 blocking wait；
- frame/time/physics step 公式；
- Writer 外部 frame ID。

验收：每次 capture 恰好产生一组同步文件，Timeline 在 RT subframes 前后不变。

### 阶段 4：渲染 profile

实施：

- 删除硬编码 DLSS；
- 删除无条件 reset；
- profile apply/readback；
- 默认 16 subframes；
- DLSS/TAA/native A/B。

验收：同一 profile 重跑的有效设置一致；关键设置不匹配时启动失败。

### 阶段 5：Stage 与物理修正

实施：

- StagePreflight；
- capture overlay；
- HDR、质量、惯量、Xform、CameraRig 修正；
- pre-roll 与实际关节状态记录。

验收：无缺失资产、负质量、无效惯量和 Xform 类型错误。

### 阶段 6：Writer graph 修正与完整回归

实施：

- BasicWriter/CustomWriter 隔离；
- 修正 Writer 图；
- 499 帧完整运行；
- 校验所有输出和日志。

验收：零 graph-cycle、零丢帧、零 frame context 残留。

### 阶段 7：Gaussian 与性能优化

实施：

- 确定最终 AA/subframes；
- 识别剩余资产侧模糊；
- 必要时调整或重建 Gaussian 资产；
- 在不破坏质量门槛的情况下恢复 queued 写盘或降低 subframes。

验收：Camera_01 的最终质量达到约定基线，吞吐量满足数据生产要求。

每个阶段应独立提交，禁止把生命周期、物理资产和 Gaussian 调整混在同一次提交中，否则无法定位收益和回归来源。

---

## 19. 发布验收门槛

### 19.1 正确性门槛

- RenderProduct 整段运行只创建一次、销毁一次。
- RT subframes 期间 Timeline 与 physics step 不变化。
- 每帧恰好一组 RGB、semantic ID、semantic color、runtime ID 和 metadata。
- 所有 frame ID、dataset time、timeline time、physics step 和 camera matrix 一致。
- semantic ID 输出在同条件重跑时保持稳定。
- Writer pending context 在结束时为 0。
- manifest 状态为 `complete`。

### 19.2 日志门槛

- 零缺失纹理或资产。
- 零负质量和无效惯量。
- 零关键 Xform 类型错误。
- 零 OmniGraph cycle。
- 零 RenderProduct 每帧注销/重建。
- 零 unknown semantic label。

### 19.3 画质门槛

- 只使用同 Stage hash、同相机矩阵、同相机内参、同仿真状态的图片比较。
- Camera_03 静态脚本图应接近同条件 GUI Recorder 基准。
- Camera_01 静态图不得因脚本管线产生明显额外柔化。
- Camera_01 运动图无明显双边、拖尾或时序闪烁。
- RGB 边界与语义边界无系统性错帧。
- 全黑/全背景帧必须能由相机视锥和轨迹状态解释。

建议在第一次新基准采集后，根据实际噪声建立 SSIM、ROI 锐度和亮度差的数值阈值；在没有严格配准基准前不要预设看似精确但缺乏依据的阈值。

### 19.4 性能门槛

- 正确性和画质通过后才统计平均/百分位采集耗时。
- 记录 GPU 显存、单帧渲染时间、写盘时间和总吞吐量。
- 只有在画质指标仍通过时，才允许从 16 subframes 下调到 8，或从 blocking 改为 queued。

---

## 20. 风险与回滚策略

### 20.1 主要风险

- 全程开启 Hydra 更新会增加物理推进期间的 GPU 成本。
- 每帧 blocking wait 会降低吞吐，但能显著简化同步正确性。
- 修正质量和惯量后，设备运动轨迹的实际姿态会与旧数据不同。
- 修复 DomeLight 会改变背景亮度和训练数据分布。
- DLSS Quality 在 720p 下未必是 Gaussian Splat 的最佳方案。
- Path Tracing 可能无法完整支持当前 Gaussian/semantic annotator 组合。
- Writer graph-cycle 可能涉及 Isaac Sim 版本行为，无法只靠局部 Python 改动解决。

### 20.2 回滚

- 每个阶段独立 Git commit。
- 渲染设置全部由 versioned JSON profile 控制。
- Stage 修正只写入新 overlay，不覆盖原始 USD。
- 旧输出目录永不覆盖，新数据使用新的版本目录。
- 生命周期旧行为只在临时对照分支保留，不成为生产配置。
- 如果某阶段失败，回退该阶段提交并保留 manifest、日志和对照图片用于分析。

---

## 21. 推荐最终生产配置候选

在 A/B 结果出来之前，建议把以下配置视为“首个候选”，而不是最终定论：

```text
Camera: Camera_01
Resolution: 1280x720
Physics: 60 Hz
Capture: 10 FPS
RenderProduct: persistent
Hydra updates: enabled for full run
Warmup: final pose, same RenderProduct, no Writer output
RT subframes: 16
AA: DLSS Quality candidate, native/TAA must A/B
Motion blur: explicitly off
Optical DOF: explicitly off
Exposure: fixed and recorded
Frame sync: blocking
Stage validation: strict
Output manifest: schema v2
```

只有当静态 Camera_03 基准、静态 Camera_01 基准和运动 Camera_01 三类测试全部通过后，才将该候选标记为 production profile。

---

## 22. 参考资料

- NVIDIA Isaac Sim Synthetic Data Recorder：<https://docs.isaacsim.omniverse.nvidia.com/latest/replicator_tutorials/tutorial_replicator_recorder.html>
- NVIDIA Replicator RTSubframes：<https://docs.omniverse.nvidia.com/extensions/latest/ext_replicator/subframes_examples.html>
- NVIDIA RTX Real-Time 2.0 与 DLSS：<https://docs.omniverse.nvidia.com/materials-and-rendering/latest/rtx-renderer_rt.html>
- NVIDIA Camera、曝光和景深属性：<https://docs.omniverse.nvidia.com/materials-and-rendering/latest/cameras.html>
- NVIDIA Gaussian Splat/Particle Fields：<https://docs.omniverse.nvidia.com/materials-and-rendering/latest/particle-fields.html>

---

## 23. 结论

代码修正的核心不是单独把 `rt_subframes` 从 4 改成 16，而是同时建立以下四个基础保证：

1. 同一个 RenderProduct 在整段运行中保持有效，预热和时序历史不会被逐帧清空。
2. 物理推进与图像采集之间存在可验证的冻结屏障。
3. Writer 使用外部帧上下文，并对每一帧给出完成确认。
4. renderer、AA、DLSS、相机、Stage 和资产状态全部显式配置并可复现。

在这四点完成后，才能可靠判断 Camera_01 剩余的柔化究竟来自 DLSS、Gaussian Splat 近景表达、场景照明还是资产本身。物理和 Stage 错误也必须在正式生产前清零，否则即使单张 RGB 变清晰，数据集的姿态真实性、时序一致性和可复现性仍然不合格。
