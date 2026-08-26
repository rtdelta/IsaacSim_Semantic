# `02_render_pathtracing.example.json` 参数说明

该文件是 PathTracing 渲染配置，由主配置的 `render_groups.<组ID>.profile` 引用。字段说明严格按照 JSON 出现顺序排列。

## 顶层和 `launch_settings`

| 顺序 | JSON 路径 | 类型 | 必填 | 含义与填写要求 |
|---:|---|---|---:|---|
| 1 | `schema_version` | 整数 | 建议 | 渲染配置文档版本。当前示例使用 `1`；加载器保留但不据此分支。 |
| 2 | `name` | 字符串 | 建议 | 人类可读的配置名称，便于日志和审计；不控制 renderer。 |
| 3 | `renderer` | 枚举字符串 | 是 | 只能是 `PathTracing` 或 `RealTimePathTracing`。本文件固定为 `PathTracing`。 |
| 4 | `launch_settings` | 对象 | 否 | 在构造 `SimulationApp` 时合并到启动字典中的设置。 |
| 4.1 | `launch_settings.anti_aliasing` | 整数 | 否 | SimulationApp 抗锯齿模式枚举。PathTracing 示例使用 `0`，主要依靠路径追踪采样。 |
| 4.2 | `launch_settings.denoiser` | 布尔值 | 否 | 是否在启动阶段启用降噪。低采样 PathTracing 通常设为 `true`。 |
| 4.3 | `launch_settings.samples_per_pixel_per_frame` | 正整数 | 否 | 每次更新每像素的采样数提示。应与 RTX `/rtx/pathtracing/spp` 保持一致。 |
| 4.4 | `launch_settings.max_bounces` | 非负整数 | 否 | 最大路径反弹次数提示。较大值提高间接光质量并增加成本。 |
| 4.5 | `launch_settings.max_specular_transmission_bounces` | 非负整数 | 否 | 镜面和透射路径的最大反弹次数。 |
| 4.6 | `launch_settings.max_volume_bounces` | 非负整数 | 否 | 体积路径的最大反弹次数。没有体积材质时可以调低。 |
| 5 | `settings` | 对象 | 是 | Stage 打开并 reset render settings 后写入 Carb/RTX 的全局设置。键是完整 RTX 设置路径。 |

## `settings` 字段

| 顺序 | JSON 键 | 值类型 | 含义与填写要求 |
|---:|---|---|---|
| 1 | `/rtx/rendermode` | 字符串 | 固定为 `PathTracing`，必须与顶层 `renderer` 一致。 |
| 2 | `/rtx/pathtracing/spp` | 正整数 | 每次 PathTracing 更新的每像素采样数。示例为 `8`。 |
| 3 | `/rtx/pathtracing/totalSpp` | 正整数 | 累积目标/上限采样数。示例为 `64`，通常不小于 `spp`。 |
| 4 | `/rtx/pathtracing/adaptiveSampling/enabled` | 布尔值 | 是否开启自适应采样。固定数据集常关闭以减少帧间策略差异。 |
| 5 | `/rtx/pathtracing/maxBounces` | 非负整数 | RTX 路径追踪最大反弹次数。 |
| 6 | `/rtx/pathtracing/maxSpecularAndTransmissionBounces` | 非负整数 | 镜面与透射合计最大反弹次数。 |
| 7 | `/rtx/pathtracing/maxVolumeBounces` | 非负整数 | 体积最大反弹次数。 |
| 8 | `/rtx/resetPtAccumOnAnimTimeChange` | 布尔值 | 动画时间变化时是否重置 PathTracing 累积。动态采集应设为 `true`，防止上一姿态污染当前帧。 |
| 9 | `/rtx/pathtracing/fractionalCutoutOpacity` | 布尔值 | 是否使用分数式 cutout opacity。植被、栅格、透明遮罩较多时通常开启。 |

## 与主配置的配合

- `render_groups.<组>.rt_subframes` 决定一次 Replicator 触发使用多少 RTX 子帧；它不在本文件中。
- `render_groups.<组>.warmup_frames` 决定 Stage/变体切换后预热多少次；它也不在本文件中。
- 同一个 worker 引用的多个渲染配置不得选择不同的 `renderer`，也不得对同一 RTX 设置键给出不同值。
- RTX 设置路径和枚举值与 Isaac Sim/Kit 版本有关。本示例已在当前 Isaac Sim 6.0.1 环境使用；升级版本后应重新做单帧验证。
