# GitHub 上传与分组提交记录

更新于 `2026-10-19T07:48:45.344918+00:00`。范围为仓库内全部近期项目与修改。分支：`codex/repository-update-20261019`，基线 `0abf2e33e4ef`。

当前源码快照共 **3229 个文件、49.92 MiB**，分配到 11 组项目提交，另有 Git 字节身份修正及最终执行记录，共 13 个提交；另有 23 个审阅材料文件，无待定项。

逐文件用途、SHA-256、大小及归属见 [上传清单](upload_manifest.json)。分组路径使用 UTF-8、LF 和 `:(literal)`，见 [提交方案](commit_plan.json)。原审查阶段材料已保存在本地 `_local/github_update/20261019_execution/initial_review/`。

## 已落实的处理

- 两个真实实例配置保留原文件名和原字节，并由精确规则忽略；提供 config.example.json / targets.example.json。既有读取入口继续使用本地原路径，未填写模板会被策略拒绝。CloudOps 测试改用临时合成配置；未运行 Skill 安装器。
- 固定 numpy/scipy/trimesh/rtree 分析依赖。几何分析从环境导入依赖；本地 vendor 副本保留并忽略。通过隔离依赖路径完成五项几何/插值测试，无全局安装。
- 四个包装器无执行解码出 34 个源码、配置和文档文件，并保存原始 SHA-256。现行根目录源码未被覆盖；原包装器归档于 `_local/archive/20261019_github/`。
- 原 180 个暂缓或排除项均有落实结果，见 [处理清单](excluded_paths.tsv)。生成包、媒体分片、完整操作响应和本地依赖副本继续排除。历史源码快照与重复包保留身份。

## 提交顺序

| 分组 | 主题 | 源码快照文件 | 依赖 |
| --- | --- | ---: | --- |
| [C01](commit_groups/C01.paths.txt) | 仓库忽略规则 | 1 | — |
| [C02](commit_groups/C02.paths.txt) | Semantic World v04 Studio 重构 | 22 | C01 |
| [C03](commit_groups/C03.paths.txt) | 资产构建、LiDAR 与轨迹辅助工具 | 155 | C01 |
| [C04](commit_groups/C04.paths.txt) | BVH 与运动几何实验 | 505 | C01, C03 |
| [C05](commit_groups/C05.paths.txt) | SensorVisualizer 基础与 v02–v04 | 519 | C01, C03 |
| [C06](commit_groups/C06.paths.txt) | v05–v07 交互与采集基础 | 466 | C05 |
| [C07](commit_groups/C07.paths.txt) | 原生采集基线与对照实验 | 351 | C03, C05, C06 |
| [C08](commit_groups/C08.paths.txt) | single0601 连续 RT 与诊断复现 | 849 | C06, C07 |
| [C09](commit_groups/C09.paths.txt) | single0602 轨迹与 Headless 链路 | 141 | C06 |
| [C10](commit_groups/C10.paths.txt) | 云端操作与 RViz 查看工具 | 155 | C06, C09 |
| [C11](commit_groups/C11.paths.txt) | 共享标准、目录导航与上传审查记录 | 64 | C01, C02, C03, C04, C05, C06, C07, C08, C09, C10 |
| [C12](commit_groups/C12.paths.txt) | Git byte identity | 1 | C11 |
| [C13](commit_groups/C13.paths.txt) | Final execution record | 0 | C12 |

C11 另外包含本目录的审阅文件。已执行提交的身份见 [执行记录](execution_status.json)；该记录为文档提交前的快照，不包含自身提交哈希，完整结果以 `git log` 为准。

## 验证范围

- 本阶段 13 个测试入口共 356 项：343 通过、13 项平台条件跳过，无失败。v04 Studio 的前阶段 79 项测试通过，相关源码本阶段未改动。
- 当前 2143 个候选 Python 文件语法通过。single0602 的 140 个交付文件哈希通过，四份包装器及 34 份恢复文件逐项核对。
- 远端 main 经 GitHub 连接器和 Git 命令重新核对，仍为本地基线。Git 使用本机已有代理设置的单次命令参数，没有更改系统或全局 Git 配置。
- 所有测试均在本地执行；没有连接云实例、执行 Kit GUI、渲染、ROS2 或重采传感器数据。固定依赖的测试使用现有已安装副本的隔离复制，不代表已从网络重新安装全套依赖。

详细矩阵及限制见 [核验摘要](validation_summary.json)和[审查说明](review_findings.md)。后续推送使用新分支，不覆盖 main；PR 保持草稿以便审阅各项目历史与运行前提。

## Git 字节身份修正

初始 11 组提交后，Git blob 核验发现原 LF 规范化会改变部分已登记交付文件的字节。C12 为明确的交付与审计目录关闭换行转换，保留可读文本 diff，恢复原始工作区字节。没有通过改写历史来源哈希来掩盖差异。

140 个 Headless 交付文件及 34 个恢复文件均与 Git 实际存储内容逐项一致，详见 [字节核验](byte_identity_validation.json)。普通仓库策略文件 `.gitignore` 仍采用 LF；清单分别记录工作区与 Git blob 哈希。历史快照的空白格式警告保留在提交执行记录，不宣称这些格式检查全部通过。

Draft PR: [#1](https://github.com/rtdelta/IsaacSim_Semantic/pull/1). The source and identity fixes are pushed; main is not merged.
