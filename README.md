# Isaac Sim 项目与实验

本仓库保存挖掘机可视化、轨迹录制与重放、传感器采集及配套实验代码。各项目根目录沿用现有位置，具体依赖、资产要求和启动命令以项目说明为准。

| 项目 | 入口 |
| --- | --- |
| 连续交互、轨迹录制与 Headless 采集 | [single0602Headless](scripts/260920SensorVisualizer/v06/single0602Headless/README.md) |
| 原生连续采集与相关诊断 | [single0601ContinuousRt](scripts/260920SensorVisualizer/v06/single0601ContinuousRt/README.md) |
| 传感器可视化及历史版本 | [SensorVisualizer](scripts/260920SensorVisualizer/README.md) |
| Semantic World Studio v04 | [项目说明](scripts/260820semantic_worldModule_v04/README.md) |
| 其它项目及早期实验 | [scripts/](scripts/) |
| 共享标准 | [docs/standards/](docs/standards/) |
| 历史资产核验与分析 | [docs/audits/](docs/audits/) |

正式报告、精选验收摘要和必要配图集中在各项目的 `docs/reports/`。采集结果、录制轨迹、逐帧状态、性能追踪、临时部署包与备份由 `.gitignore` 排除，仍保存在本地或原远端运行目录。

目录职责、迁移索引和复核方式见 [仓库文件布局](docs/RepositoryLayout.md)。2026-10-19 的目录整理没有重新执行历史实验，也没有同步、迁移或修改远端实例。

本轮 GitHub 更新范围、分组与验证记录见 [上传与提交方案](docs/github_update/20261019/UploadPlan.md)。
