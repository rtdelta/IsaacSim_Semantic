# `03_render_realtime.example.json` 参数说明

该文件用于快速预览、标定验证和 RealTimePathTracing 数据采集。字段说明严格按照 JSON 顺序排列。

| 顺序 | JSON 路径 | 类型 | 必填 | 含义与填写要求 |
|---:|---|---|---:|---|
| 1 | `schema_version` | 整数 | 建议 | 渲染配置文档版本，示例为 `1`。 |
| 2 | `name` | 字符串 | 建议 | 人类可读名称，不直接控制 RTX。 |
| 3 | `renderer` | 枚举字符串 | 是 | 本文件填写 `RealTimePathTracing`。加载器只接受它或 `PathTracing`。 |
| 4 | `launch_settings` | 对象 | 否 | 传给 `SimulationApp` 构造器的启动设置。 |
| 4.1 | `launch_settings.anti_aliasing` | 整数 | 否 | 抗锯齿模式枚举；示例值 `3` 是当前项目已验证的实时 RTX 启动值。 |
| 4.2 | `launch_settings.denoiser` | 布尔值 | 否 | 是否启用实时降噪。通常填 `true`。 |
| 5 | `settings` | 对象 | 是 | Stage 打开后写入的全局 RTX 设置。 |
| 5.1 | `settings./rtx/rendermode` | 字符串 | 是 | 固定为 `RealTimePathTracing`，必须与顶层 `renderer` 一致。实际 JSON 键是 `/rtx/rendermode`。 |
| 5.2 | `settings./rtx/post/dlss/execMode` | 整数 | 否 | DLSS 执行模式枚举。示例为当前环境验证值 `2`；具体枚举语义随 RTX/Kit 版本可能变化。 |

使用时把主配置中的渲染组改为：

```json
{
  "profile": "03_render_realtime.example.json",
  "rt_subframes": 1,
  "warmup_frames": 8
}
```

同一 worker 不能同时引用本文件和 PathTracing 文件，因为两者的全局 renderer 不同。实时模式通常更快，但画质、噪声和光照收敛特性与 PathTracing 不同，正式数据集应先固定一种模式并做回归验证。
