# Semantic World Module v04 端到端实现主 Prompt

> 用途：将本文档交给编码 Agent，要求其在全新的 v04 目录中实现 Semantic Capture Studio、同机任务管理模块和 Headless Runtime。  
> 本地源码目录：`D:\learning\IntelligentDepartment\CodesSet\Self\260707IsaacSIm\scripts\260820semantic_worldModule_v04`  
> 目标运行环境：部署了 Omniverse Kit / Isaac Sim 的云电脑。  
> 重要边界：本地电脑没有安装 Omniverse；不得调用任何旧项目的脚本文件，但允许理解和复用旧项目中的算法与实现逻辑。

---

## 给编码 Agent 的任务指令

你现在负责从零实现 `Semantic World Module v04`。不要只给方案或示例代码，要在指定目录中持续完成实际代码、配置、测试、启动入口、文档和远端验证，直到本 Prompt 定义的 MVP 验收条件满足，或者遇到确实无法在当前权限与环境内解决的外部阻塞。

## 1. 首要目标

在以下目录中实现一个完全自包含的新项目：

```text
D:\learning\IntelligentDepartment\CodesSet\Self\260707IsaacSIm\scripts\260820semantic_worldModule_v04
```

最终产品由三个相互解耦的部分组成：

1. `Semantic Capture Studio`
   - 独立 Omniverse Kit 应用。
   - 运行在云电脑上。
   - 提供轻量 USD 查看、Prim 选择、传感器配置、场景变体配置、模态选择、项目保存、任务校验和任务提交。
   - 不是 Isaac Sim GUI 插件，也不要求先手工启动完整 Isaac Sim GUI。

2. `Semantic Capture Supervisor`
   - 与 Studio、Runtime 部署在同一台云电脑。
   - 负责生成任务实例、启动和监控 Headless Runtime 子进程、GPU 资源锁、状态记录、日志、停止和断点恢复。
   - 当前版本不实现 LocalRunner/SshRunner 选择，也不实现跨机器远端工作流。

3. `Semantic Capture Runtime`
   - 使用 Headless Isaac Sim 正式采集。
   - 负责 Stage 加载、运动控制、传感器创建、场景变体、模态采集、Path Tracing、原子输出、任务账本和断点续采。
   - 正式采集不依赖 Studio 进程继续存活，不依赖 Isaac Sim GUI。

完整应用部署到云电脑后，运行时不得读取本地 Windows 文件，不得要求本地提供服务，也不得通过 SSH Runner 调度自己。

## 2. 必须先阅读的需求文档

开始设计和修改代码前，完整阅读：

```text
docs/QandA/01_轻量USD任务编辑器与v04完整架构_QA.md
docs/QandA/02_云电脑单机部署与模块化v04实现方案_QA.md
```

这两份文档是需求和架构依据。本 Prompt 与它们冲突时，以本 Prompt 中更新后的约束为准，尤其是：

- 选择“Omniverse Kit 独立应用”。
- Studio、Supervisor 和 Runtime 全部运行在同一台云电脑。
- 当前不实现 SSH Runner、跨机器上传、远端机器列表或本机运行模式。
- 正式采集始终 Headless。
- 所有组件尽量模块化。

## 3. 新旧项目隔离规则

这是硬性约束。

### 3.1 禁止事项

v04 的可执行代码、配置、启动脚本和测试不得：

- `import` v01、v02、v03 或其他旧项目的 Python 模块。
- 将旧项目路径加入 `sys.path`、`PYTHONPATH` 或 Kit extension search path。
- 使用 `subprocess`、shell、`source`、软链接等方式调用旧项目入口或旧脚本。
- 从旧项目目录加载运行配置、插件、Writer、Runner、Runtime wrapper 或辅助模块。
- 将旧项目作为 Git submodule、包依赖或运行时 fallback。
- 修改或删除任何旧项目文件。
- 为了让测试通过而把 v04 入口转发到旧项目。

### 3.2 允许事项

可以只读检查旧项目，理解已经验证过的业务逻辑、算法、错误处理方式和 Isaac API 使用方法；可以将有价值的逻辑重新实现或复制改造到 v04 自己的新模块中，但必须满足：

- 新代码实体存在于 v04 目录。
- 使用 v04 自己的命名空间。
- 依赖关系只指向 v04 或明确的第三方/Isaac/Kit API。
- 有对应的新测试。
- 不需要旧项目存在也能部署和运行。

公共 USD、纹理、轨迹 CSV 和数据资产不属于“旧项目脚本”，可以通过 v04 项目配置显式引用；但不得引用旧项目内部的 Python、shell、JSON 配置快照或启动入口。

在交付前，对可执行代码和配置进行引用审计，确认没有残留旧项目路径或旧模块 import。

## 4. 源码与部署原则

### 4.1 本地工作区是源码真相

- 所有正式代码编辑先落在本地 v04 目录。
- 使用补丁方式进行可审查的文件修改。
- 不在远端形成仅存在于云电脑、未同步回本地的“最终代码”。
- 如果为了调试临时修改了远端文件，验证后必须把同等修改落实回本地并重新同步验证。
- 不覆盖用户无关修改，不使用破坏性 Git 命令。

### 4.2 云电脑是完整运行和集成验证环境

由于本地没有 Omniverse/Isaac Sim：

- 本地运行纯 Python 单元测试、Schema 测试、编译器测试和使用 fake adapter 的集成测试。
- USD/Kit/Isaac/Replicator/渲染相关测试必须部署到云电脑执行。
- Studio、Supervisor、Runtime 和所需 v04 配置都要完整上传到云端 v04 目录。
- 云端验证不能调用旧项目脚本。

建议远端部署目录：

```text
/root/gpufree-data/semantic/scripts/260820semantic_worldModule_v04
```

如该目录已经存在，先只读检查内容和正在运行的进程；不要未经检查覆盖用户数据、任务快照、日志或输出。

## 5. 远端连接与安全规则

当前已验证的连接方式：

```text
Host: 183.147.142.40
Port: 30543
User: root
Private key: C:\Users\15452\.ssh\id_ed25519_isaacsim_gpufree
Remote hostname: gpufree-container
Isaac Sim: /root/isaacsim
```

验证命令：

```powershell
ssh -i "$env:USERPROFILE\.ssh\id_ed25519_isaacsim_gpufree" -p 30543 -o BatchMode=yes -o IdentitiesOnly=yes root@183.147.142.40 "printf 'key-auth-ok user='; id -un; printf 'host='; hostname"
```

必须遵守：

- 永远不要输出、复制或读取私钥内容。
- 不在代码、配置、文档、日志或回复中保存密码。
- 始终使用公钥和 `BatchMode=yes`；公钥认证失败就停止并报告，不自动回退密码。
- 不关闭主机密钥检查；主机指纹异常时停止。
- 长时间 Kit/Isaac 测试要持续收集输出，不要因本地命令超时误判为业务失败。
- 运行前检查 `df -h / /root/gpufree-data`、`nvidia-smi` 和 Isaac/Kit 相关进程。
- 如果云端已有采集或 Kit 任务，不终止、不抢占 GPU；先报告并等待安全窗口。
- 未经用户明确授权，不清理旧输出、缓存、日志或数据。
- 不修改原始 USD 资产；需要写 USD opinion 时使用 Session Layer 或 v04 项目自己的 authoring layer。

远端当前 Isaac 版本需要由 Agent再次读取 `/root/isaacsim/VERSION` 记录，不要只依赖本 Prompt 的历史信息。

## 6. 技术架构与依赖方向

代码必须遵守单向依赖：

```text
Studio UI
  ↓
Application Services
  ↓
Project Domain Model
  ↓
Validation / Compilation
  ↓
Immutable JobSpec
  ↓
Same-host Supervisor
  ↓
Headless Runtime Orchestrator
  ↓
Stage / Motion / Variant / Sensor / Modality adapters
  ↓
Atomic Output / Ledger / Status
```

禁止反向依赖，例如：

- Domain Model 不得 import `omni.*`、`isaacsim.*`、Replicator 或 UI。
- Validator 的纯配置部分不得依赖已启动的 Kit。
- Output Writer 不得直接操作 UI。
- Sensor Driver 不得自行控制整个任务生命周期。
- UI 不得直接创建 Annotator、World 或 Render Product。
- Supervisor 不得理解具体传感器实现。

对 Kit/Isaac 的 import 必须延迟到对应适配器或进程已经在正确运行环境中启动之后。普通 Python 环境导入 v04 核心包时，不应因为缺少 `omni`、`pxr` 或 `isaacsim` 而失败。

## 7. 推荐项目结构

可以基于实际 Kit/Isaac 版本调整文件细节，但必须保持职责分离。建议结构：

```text
260820semantic_worldModule_v04/
├─ pyproject.toml
├─ README.md
├─ CHANGELOG.md
├─ apps/
│  └─ semantic_capture_studio.kit
├─ extensions/
│  └─ semantic.capture.studio/
│     ├─ config/extension.toml
│     └─ semantic/capture/studio/
├─ src/
│  └─ semantic_world_v04/
│     ├─ core/
│     │  ├─ models.py
│     │  ├─ errors.py
│     │  ├─ events.py
│     │  └─ protocols.py
│     ├─ project/
│     │  ├─ repository.py
│     │  ├─ schema.py
│     │  └─ migration.py
│     ├─ stage/
│     │  ├─ service.py
│     │  ├─ index.py
│     │  └─ omni_adapter.py
│     ├─ plugins/
│     │  ├─ registry.py
│     │  ├─ sensors/
│     │  ├─ variants/
│     │  └─ modalities/
│     ├─ compiler/
│     │  ├─ validator.py
│     │  └─ job_compiler.py
│     ├─ studio/
│     │  ├─ application.py
│     │  ├─ view_models/
│     │  └─ panels/
│     ├─ supervisor/
│     │  ├─ service.py
│     │  ├─ process_launcher.py
│     │  ├─ gpu_lock.py
│     │  └─ status_store.py
│     ├─ runtime/
│     │  ├─ bootstrap.py
│     │  ├─ orchestrator.py
│     │  ├─ stage_loader.py
│     │  ├─ motion.py
│     │  ├─ coordinator.py
│     │  └─ worker_cli.py
│     ├─ output/
│     │  ├─ atomic_writer.py
│     │  ├─ layout.py
│     │  └─ ledger.py
│     └─ cli/
│        ├─ project_cli.py
│        └─ supervisor_cli.py
├─ scripts/
│  ├─ launch_studio.sh
│  ├─ launch_runtime.sh
│  └─ remote_smoke_test.sh
├─ examples/
│  └─ minimal_project/
├─ tests/
│  ├─ unit/
│  ├─ integration/
│  └─ fakes/
└─ docs/
   ├─ Architecture/
   ├─ Prompts/
   ├─ QandA/
   └─ Validation/
```

不要为了机械匹配目录而创建大量空文件。每个模块必须有明确作用，未实现能力要在文档中标记，不得用看似成功的空实现伪装完成。

## 8. 核心领域模型

建立带 `schema_version` 的稳定领域模型，至少覆盖：

- `ProjectDefinition`
- `StageReference`
- `SensorDefinition`
- `SensorBinding`
- `VariantDefinition`
- `ModalityDefinition`
- `RenderProfile`
- `CaptureSchedule`
- `MotionSpec`
- `SemanticProfile`
- `OutputPolicy`
- `JobSpec`
- `JobStatus`
- `FrameLedgerEntry`

要求：

- 模型可以在没有 Kit/Isaac 的普通 Python 中加载、校验和序列化。
- JSON 输出稳定、可读、可比较。
- 未知字段和拼写错误不能被静默忽略。
- 路径解析规则明确区分项目相对路径、云端绝对路径和 USD asset path。
- 保存项目时不把 UI 临时状态混进 Runtime 配置。
- `JobSpec` 编译后不可变，并保存内容摘要或等价完整性标识。
- 为未来 Schema migration 预留清晰入口。

## 9. 项目持久化

实现可复用项目目录。允许根据实现需要合并配置文件，但逻辑上必须覆盖：

```text
example.swproject/
├─ project.json
├─ stage.json
├─ sensors.json
├─ variants.json
├─ modalities.json
├─ render.json
├─ motion.json
├─ semantics.json
└─ jobs/
   └─ <job_id>/
      ├─ job_spec.json
      ├─ status.json
      ├─ ledger.jsonl
      └─ logs/
```

必须支持：

- 新建项目。
- 打开已有项目。
- 原子保存。
- 另存为新项目。
- 修改后重新编译任务。
- 保留旧任务快照，避免当前项目修改污染运行中的任务。
- 对缺失文件、非法 JSON、版本不兼容给出可操作错误。

## 10. Stage 与轻量 USD 能力

实现独立 Stage Service：

- 打开和关闭 USD。
- 异步等待 Stage 完成加载。
- 遍历 Prim 并建立 `StageIndex`。
- 按类型、名称和路径搜索。
- 读取 Camera Prim 的标准 USD 相机属性。
- 读取 Transform、Visibility、语义标签、灯光和层级关系的必要摘要。
- Stage 变化后按事件增量更新或安全重建索引。
- 不在扫描模块创建 Isaac World 或 Replicator。

传感器配置应以 `prim_path` 为入口：能够从 USD Stage 自动读取的参数默认自动读取；只有 USD 中不存在、属于采集策略或需要用户覆盖的参数才写入项目配置。配置中应记录参数来源：

- `stage`
- `override`
- `default`

不要要求用户重复填写 USD Camera 已经定义的焦距、光圈、裁剪范围和变换。

## 11. Studio MVP

Studio 是独立 Omniverse Kit 应用。启动配置和 extension 必须属于 v04。

至少实现以下可用界面：

1. Project 面板
   - 新建、打开、保存、另存为。
   - 显示项目路径、Schema 版本和修改状态。

2. Stage 面板
   - 打开 USD。
   - 显示可搜索 Prim Tree。
   - 选择 Prim 并与 Viewport 选择同步。

3. Viewport
   - 轻量显示 USD。
   - 支持 Prim 拾取。
   - 显示选中传感器。
   - 不承担正式数据采集。

4. Sensors 面板
   - 从选中 Prim 添加传感器。
   - 自动识别至少 pinhole camera。
   - 显示自动读取参数和用户 override。
   - 支持启用、禁用、复制和删除 SensorDefinition。

5. Variants 面板
   - 至少支持 `full_scene`。
   - 支持基于 `include_paths` 的隔离场景。
   - 显式保护传感器 Prim、祖先路径和必要灯光。
   - 只写 Session Layer 或项目 authoring layer，不修改源 USD。

6. Modality Matrix
   - 按“传感器 × 场景变体”选择输出。
   - 初期至少包括 `rgb`、`semantic_id`、`semantic_color`。
   - 不支持的组合必须在 UI 和 Validator 中禁用或报错。

7. Run 面板
   - 预检查。
   - 编译 JobSpec。
   - 提交任务。
   - 查看状态、帧进度和日志末尾。
   - 停止或恢复任务。
   - 提供“提交并进入监控模式”和“提交并退出 Studio”。

UI 代码必须通过 ViewModel/Application Service 操作领域模型，不得把业务配置散落在 widget 回调中。

## 12. 插件系统

定义小而稳定的插件协议与注册中心，不使用到处出现的传感器类型 `if/elif` 主链路。

### 12.1 SensorPlugin

职责：

- 判断 Prim 是否匹配。
- 从 Stage 提取参数。
- 声明支持的模态。
- 校验配置。
- 编译 Runtime payload。
- 在 Runtime 环境创建 Sensor Driver。

MVP 至少完整实现：

- `PinholeCameraPlugin`

为以下类型保留可验证的扩展入口，但不允许伪装成已经完成采集：

- Fisheye Camera。
- LiDAR。
- Multi-camera Rig。

### 12.2 VariantStrategy

MVP 至少实现：

- `FullSceneVariant`
- `IncludePathsVariant`

所有可见性 opinion 只写 Session Layer 或 v04 authoring layer。算法必须保护传感器路径、祖先路径和明确保留的灯光/环境路径。

### 12.3 ModalityPlugin

MVP 至少实现：

- `RgbModality`
- `SemanticIdModality`
- `SemanticColorModality`

语义 ID 使用无损整数数组格式，例如 NPY；语义彩色图使用便于查看的 PNG。颜色映射必须稳定并随任务保存，不得每次随机变化。

当某变体只请求语义模态时：

- 不创建或不读取无用 RGB payload。
- 不写 RGB 文件。
- Coordinator 仍进行防御性模态过滤。

## 13. Validator 与 JobCompiler

将校验拆成：

1. 纯静态校验
   - 本地普通 Python 可运行。
   - Schema、路径格式、ID 唯一性、引用关系、模态兼容性、帧率关系等。

2. Stage 校验
   - 在 Kit/OpenUSD 环境确认 Prim 和类型。
   - 确认 Variant 不会隐藏传感器或必要祖先。

3. Runtime Preflight
   - 检查 Isaac/扩展能力、GPU、输出空间、渲染器和 Annotator。

`JobCompiler` 必须：

- 将可编辑 ProjectDefinition 编译为自包含 JobSpec。
- 解析默认值和显式 override。
- 固化 Stage、Sensor、Variant、Modality、Render、Motion、Output 配置。
- 生成确定性内容摘要。
- 不把 UI 对象或运行中 USD 对象写入 JSON。

任何校验失败都必须阻止启动正式任务，并返回结构化问题列表，而不是在数千帧任务运行后才失败。

## 14. Same-host Supervisor

当前只实现云电脑同机 Supervisor，不创建远端 Runner 抽象的用户功能。

至少提供：

```text
submit(job_spec)
start(job_id)
status(job_id)
stop(job_id)
resume(job_id)
tail_logs(job_id)
```

要求：

- Runtime 使用独立子进程。
- Studio 退出后任务仍能继续。
- JobSpec 在启动前已保存。
- PID、启动时间、退出码、错误摘要和最后心跳可查询。
- 使用文件锁或等价机制避免同一 GPU 上误启动互斥任务。
- 不能仅凭 PID 文件认定进程仍活着，要防止陈旧 PID。
- 停止任务先尝试可控的优雅终止，再按明确超时策略处理。
- 不执行来源不可信的 shell 字符串；参数以列表或安全配置传递。
- 状态更新使用原子写入。

Supervisor 只负责同机进程管理。未来是否添加跨机器功能，不影响当前实现和验收。

## 15. Headless Runtime

Runtime 必须是 v04 自己的新实现，至少包含：

- Bootstrap 与运行环境检查。
- SimulationApp/Kit 生命周期。
- Stage Loader。
- Motion Controller。
- Variant Controller。
- Sensor Registry。
- Capture Coordinator。
- Output Writer。
- Checkpoint Ledger。
- 清晰的退出和异常收尾。

### 15.1 渲染设置顺序

对 Path Tracing：

1. 创建 Headless SimulationApp。
2. 打开 Stage 并等待完成。
3. 在需要时 reset render settings。
4. 应用 Path Tracing profile。
5. 回读关键设置并写入日志/任务状态。
6. 创建传感器和 Render Product。
7. 在目标姿态 reset render history。
8. 执行 warmup。
9. 正式采集。

不要只在打开 Stage 前应用渲染设置，因为 Stage 加载可能改变相关设置。

### 15.2 运动与分段

- 明确区分绝对状态轨迹与增量/动力学轨迹。
- 只有 MotionSource 明确声明支持绝对 seek 时，非首段才能快跳到目标位置。
- 快跳后同步 timeline、world step、绝对姿态和传感器可见状态。
- Path Tracing 在快跳后重置历史并 warmup。
- IMU、速度、接触动力学和运动畸变 LiDAR 不得未经声明沿用视觉采集的快跳假设。

### 15.3 原子帧提交

每帧或每个 capture group 先写 staging，再在所有请求模态成功后原子提交：

- 崩溃不能留下看似完整的正式帧。
- Ledger 只记录已提交帧。
- Resume 从 Ledger 和文件完整性共同判断。
- 临时 staging 可以在安全验证后清理，但不得误删已提交数据。

## 16. 远端运行包装与 ABI 安全

远端 Isaac Sim 的 Python/Kit 运行必须避免系统 `libpython` 与 Isaac bundle 的 Python 扩展发生 ABI 混装。

为 v04 新建自己的启动 wrapper，至少做到：

- 将 `/root/isaacsim/kit/python/lib` 放在运行时库搜索路径最前面。
- 使用 `/root/isaacsim/python.sh` 或经远端版本验证的 Kit 入口。
- 将 HOME、TMPDIR、XDG/Omniverse/Kit/CUDA/OptiX 缓存放到 v04 在 `/root/gpufree-data` 下的运行目录。
- 启动前记录 `sys.executable`、`sys.version` 和实际加载的 `libpython` 来源。
- wrapper 完全属于 v04，不能调用旧项目 wrapper。

先执行一个最小 `asyncio.get_running_loop()`/Kit 启动探针和最小 SimulationApp 生命周期测试，再运行完整采集。不要把启动期原生崩溃误归因于 Path Tracing。

## 17. 输出和状态结构

输出布局必须由统一模块生成，建议：

```text
output/<job_id>/
├─ job_spec.json
├─ semantic_mapping.json
├─ status.json
├─ ledger.jsonl
├─ logs/
│  ├─ supervisor.log
│  └─ runtime.log
├─ sensors/
│  └─ <sensor_id>/
│     └─ <variant_id>/
│        ├─ rgb/
│        ├─ semantic_id/
│        ├─ semantic_color/
│        └─ metadata/
└─ .staging/
```

要求：

- 未请求模态不创建伪输出。
- 文件扩展名与数据类型一致。
- 每帧 metadata 能追溯 frame index、simulation time、sensor、variant、requested modalities 和已写文件。
- 状态至少包含 queued、preflight、running、stopping、completed、failed、cancelled。
- 日志不能包含密码、私钥、敏感环境变量或大段二进制内容。

## 18. 本地测试策略

本地没有 Omniverse，因此核心代码必须可用 fake adapter 测试。

至少覆盖：

- Schema 严格解析和未知字段拒绝。
- 项目原子保存/加载。
- 相对路径解析。
- JobSpec 确定性编译和摘要。
- 插件注册、重复 ID 和未知插件。
- Sensor × Variant × Modality 兼容矩阵。
- IncludePaths 路径保护算法。
- Semantic-only 不产生 RGB 请求和输出。
- Supervisor 状态转换和陈旧 PID 处理。
- GPU lock 的互斥行为。
- Atomic Writer 崩溃前后行为。
- Ledger resume。
- 绝对 seek 能力声明和非支持 motion 的回退。
- 核心包在没有 `omni`/`isaacsim` 时仍可 import。

优先使用标准库和项目明确声明的依赖。不要让单元测试依赖云电脑或真实 GPU。

## 19. 云端验证矩阵

每次远端验证先同步 v04 自身到独立目录，并记录实际命令和日志路径。

### 19.1 环境探针

- SSH 公钥连接成功。
- 记录 Isaac Sim 版本。
- 检查磁盘、GPU 和进程。
- 验证正确 `libpython`。
- v04 核心包编译和 import。

### 19.2 Studio 探针

- 独立 `.kit` 应用或等价 Kit 启动入口能加载 v04 extension。
- 能打开一个有效 USD。
- 能建立 StageIndex。
- 能发现 Camera Prim 并读取标准相机参数。
- 能创建、保存并重新打开一个 v04 项目。
- 如果云桌面显示环境可用，完成一次真实界面视觉检查。
- 如果当前环境无法进行可见 UI 检查，仍执行自动化 extension 启动测试，并明确记录未验证的视觉部分，不能虚构通过。

### 19.3 Runtime 最小冒烟

先使用小分辨率和极少帧，不直接启动长任务：

- Headless 启动并正常关闭。
- RTX Realtime 最小采集。
- Path Tracing 最小采集。
- Full Scene：RGB + Semantic ID + Semantic Color。
- IncludePaths 隔离场景：Semantic ID + Semantic Color，确认没有 RGB 文件。
- 检查数组 shape/dtype、PNG 可读性、文件数量、metadata 和 Ledger。

可使用云端已有公共测试资产或下面的真实场景进行明确配置的冒烟验证：

```text
USD:
/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_05.usda

Trajectory:
/root/gpufree-data/semantic/scripts/trajectories/trajectory_0813_01.csv

Known camera prim:
/Excavator_Fangshan_03/boom_prim/Camera
```

这些只是公共数据输入。必须为 v04 新建项目配置和 JobSpec，不得读取旧项目 JSON、Python 或 shell 文件。

### 19.4 Supervisor 验证

- 提交任务。
- Runtime 独立启动。
- Studio/提交进程退出后任务继续。
- 状态和心跳更新。
- 正常完成。
- 人为终止一个只写测试目录的短任务后能够识别失败或取消。
- Resume 不重复提交已经完成的帧。

所有远端测试只写 v04 专用测试输出目录，不覆盖正式采集数据。冒烟输出是否删除必须遵守用户授权；默认保留日志和小型验证结果。

## 20. 实施阶段

按以下顺序推进，每个阶段完成代码、测试和简短文档后再进入下一阶段，但不要因为完成文档就停止编码。

### 阶段 0：审计与兼容性确认

- 检查 v04 现状和工作区修改。
- 阅读需求文档。
- 连接云电脑做只读环境探针。
- 检查 Isaac/Kit 自带示例、extension manifest 和实际可用 API。
- 在 `docs/Validation` 记录版本与兼容性选择。

### 阶段 1：纯 Python 核心

- 项目骨架。
- Domain Model。
- Project Repository。
- 插件协议和注册中心。
- Validator。
- JobCompiler。
- Output/Ledger 纯逻辑。
- 本地单元测试。

### 阶段 2：USD 与插件实现

- StageIndex 抽象。
- Fake Stage adapter。
- Omniverse/OpenUSD adapter。
- Pinhole Camera plugin。
- FullScene/IncludePaths。
- RGB/Semantic ID/Semantic Color。
- 本地测试和远端 Stage 探针。

### 阶段 3：独立 Studio MVP

- v04 Kit app 配置。
- v04 Studio extension。
- Project、Stage、Viewport、Sensors、Variants、Modality Matrix、Run 面板。
- UI 与领域模型绑定。
- 云端启动和项目保存验证。

### 阶段 4：同机 Supervisor

- Job 生命周期。
- 进程启动。
- ABI-safe v04 wrapper。
- GPU lock。
- 状态、心跳和日志。
- CLI 和 Studio Run 面板接入。

### 阶段 5：Headless Runtime MVP

- Stage、Motion、Variant、Sensor、Coordinator、Output、Ledger。
- Realtime 和 Path Tracing。
- 原子帧提交。
- Resume。
- 远端端到端冒烟。

### 阶段 6：收尾与交付

- 完整测试。
- 旧项目引用审计。
- README 快速上手。
- 架构、Schema、插件开发、远端验证、故障处理文档。
- 示例项目。
- 记录未完成的未来功能，不伪装完成。

原方案中的“远端工作流”阶段已经取消。这里的云端验证是开发验证手段，不是在产品中实现 SSH Runner。

## 21. MVP 完成标准

只有同时满足以下条件，才能声明 v04 MVP 完成：

- v04 是全新、自包含项目，不依赖旧项目脚本。
- 普通 Python 可以 import 核心包。
- 本地纯 Python 测试全部通过。
- 项目可新建、保存、重新打开和编译。
- Stage 能发现 Camera Prim 并自动读取相机数据。
- 独立 Kit Studio extension 能在云电脑启动。
- Studio 能配置至少一个相机、两个场景变体和三种基础模态。
- 同机 Supervisor 能启动独立 Headless Runtime。
- Studio 退出不导致 Runtime 被动退出。
- Headless Realtime 冒烟通过。
- Headless Path Tracing 冒烟通过。
- Full Scene 正确输出 RGB、Semantic ID、Semantic Color。
- Semantic-only 变体不输出 RGB。
- 输出使用 staging + 原子提交 + Ledger。
- 短任务的停止、失败识别和 Resume 至少经过一次测试。
- README 给出云电脑上的实际启动步骤。
- 远端验证报告包含命令、版本、日志路径和结果。
- 可执行代码中不存在旧项目 import、调用或路径依赖。

如果独立 Kit UI 的视觉验证受当前云桌面条件阻塞，必须完成其余代码和自动化启动测试，并准确说明这一项尚未视觉验收；不得因此把整个任务停留在方案阶段。

## 22. 编码质量要求

- 公共 API 有类型标注和简洁文档。
- 模块职责单一，避免超大文件和全局单例。
- 使用依赖注入或 Protocol 隔离 Kit/Isaac adapter。
- 错误类型结构化，用户可操作。
- 配置严格校验，不静默吞掉未知字段。
- 文件写入原子化。
- 日志包含 job/sensor/variant/frame 上下文。
- 不捕获宽泛异常后假装成功。
- 不在模块 import 时启动 Kit、连接 Stage 或创建 GPU 对象。
- 不硬编码业务场景 Prim 到通用代码。
- 不硬编码特定传感器到 Coordinator 主链路。
- 示例配置可以引用已知场景，但核心实现必须通用。
- 对官方 API 名称和 Isaac 版本兼容性进行实际验证，不凭记忆编造。

## 23. 工作方式

执行过程中：

1. 先检查再修改。
2. 维护一个有状态的实施计划，一次只有一个进行中步骤。
3. 优先完成纵向可运行链路，而不是一次创建大量空壳。
4. 每完成重要模块立即运行相关测试。
5. 本地无法验证的 Kit/Isaac 行为及时部署远端做最小实验。
6. 不让远端长任务无输出运行；持续读取日志并定期报告进度。
7. 对失败先保留证据、定位根因，再修复；不要反复盲目重跑。
8. 未经用户授权不执行破坏性清理。
9. 不要求用户为可以通过代码、现有文档或只读环境检查解决的问题重复做选择。
10. 只在确实需要新权限、外部资源或会改变产品方向的选择时询问用户。

## 24. 最终交付报告格式

最终回复必须以完成结果为主，并包含：

1. 已实现能力。
2. 关键架构和模块链路。
3. 本地测试命令与结果。
4. 远端 Isaac/Kit 验证命令、版本、日志位置与结果。
5. Realtime/Path Tracing 冒烟输出位置及检查结果。
6. 旧项目隔离审计结果。
7. 尚未完成或受环境限制的部分。
8. 云电脑上的最短启动步骤。
9. 重要源码和文档的可点击路径。

不要只回复“代码已完成”，也不要用计划代替实现证据。

## 25. 模块化链路总结

```text
USD Stage
  ↓
StageService / StageIndex
  ↓
Project Domain Model
  ↓
SensorPlugin + VariantStrategy + ModalityPlugin
  ↓
Validator
  ↓
JobCompiler
  ↓
Immutable JobSpec
  ↓
Same-host Supervisor
  ↓
Headless Runtime Orchestrator
  ↓
StageLoader + MotionController + VariantController
  ↓
SensorRegistry + CaptureCoordinator
  ↓
AtomicOutputWriter + CheckpointLedger
  ↓
Dataset + Status + Logs
```

这条链路中：

- Studio 只编辑“采集任务定义”。
- 插件层决定传感器、场景和模态如何扩展。
- Compiler 建立 UI 与 Runtime 之间的稳定边界。
- Supervisor 只管理同机任务生命周期。
- Runtime 只负责稳定执行不可变 JobSpec。
- Output/Ledger 只负责可靠落盘和恢复。

未来新增鱼眼相机、LiDAR、新模态、新场景选择策略或新的任务调度方式时，应扩展对应模块，不修改主采集链路。
