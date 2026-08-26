# `06_lidar_profile.example.json` 参数说明

这是 RTX LiDAR 的数据集标定/审计 Profile。当前 v03 会把整个对象纳入 LiDAR `calibration_hash` 和 packet 元数据。

重要区别：真正决定 Isaac 内置 LiDAR 扫描模型的是主配置中的 `sensors[].source.config`（如 `Example_Rotary`）或 `source.usd_path`；本文件不会替代 Isaac 的内置 LiDAR JSON/RTX 传感器资产。

字段按 JSON 顺序说明如下：

| 顺序 | JSON 路径 | 类型 | 必填 | 含义与填写要求 |
|---:|---|---|---:|---|
| 1 | `schema_version` | 整数 | 建议 | 本审计 Profile 的文档版本，示例为 `1`。LiDAR 驱动允许整个文件是任意 JSON 对象。 |
| 2 | `model` | 非空字符串 | 建议 | 使用的传感器模型或 Isaac 配置名称。应与主配置 `source.config` 保持一致。 |
| 3 | `scan_rate_hz` | 正数 | 建议 | 期望扫描频率，单位 Hz。应与主配置 `clock.hz` 和 `settings.scan_rate_hz` 一致。 |
| 4 | `coordinates` | 字符串 | 建议 | GenericModelOutput 元素坐标约定，例如 `SPHERICAL` 或 `CARTESIAN`。应与传感器实际输出一致。 |
| 5 | `aux_output_level` | 字符串 | 建议 | 期望辅助输出级别，例如 `BASIC`、`EXTRA`。具体值取决于 Isaac RTX LiDAR API。 |
| 6 | `accumulate_outputs` | 布尔值 | 建议 | 是否按完整扫描周期累积输出。旋转 LiDAR 通常为 `true`。 |
| 7 | `note` | 字符串 | 否 | 人类可读说明，也会进入 Profile 和标定哈希；修改它会改变任务配置/标定审计结果。 |

主配置中的对应写法：

```json
{
  "source": {
    "mode": "create",
    "parent_prim": "/World/Sensors",
    "prim_name": "CreatedRotaryLidar",
    "config": "Example_Rotary"
  },
  "clock": {
    "hz": 10,
    "phase_seconds": 0,
    "acquisition": "interval"
  },
  "calibration": {
    "policy": "from_profile",
    "profile": "06_lidar_profile.example.json"
  },
  "settings": {
    "scan_rate_hz": 10,
    "accumulate_outputs": true,
    "aux_output_level": "EXTRA",
    "coordinates": "SPHERICAL"
  }
}
```

`clock.hz`、主配置 `settings.scan_rate_hz` 和本文件 `scan_rate_hz` 应写成相同值。前两者不一致会触发 v03 预检错误；本文件主要用于审计，因此也应人工保持一致。
