# 本地验证记录

日期：2026-10-08。环境：本地 Windows / Python 3.9。详细版本及结果见 `reports/local_verification.json`。

| 检查 | 结果 |
|---|---|
| 39 个 Python 文件语法与项目内部导入检查 | 通过 |
| 配置文件合并和参数校验 | 通过 |
| 单独复制 v03、隔离解释器执行 24 项单元/异步测试 | 全部通过 |
| 622 个原项目文件 SHA-256 对照 | 0 修改、0 缺失 |
| 命令行入口 `--help` | 通过 |
| 实际 Isaac/RTX 相机、LiDAR 回调与数据来源验收 | 未执行 |
| 实际 ROS 2 / MCAP / RViz 端到端验收 | 未执行 |
| 实际硬件性能 A/B 对比 | 未执行 |
| 远端部署 | 未执行；本次用户范围为本地独立项目 |

测试覆盖：相机/LiDAR 统一启停与相机独立预热；回调晚于 step 返回；旧时钟、错误代次、错误位姿和缺回调拒绝；取消时等原生任务退出；停止在当前组完成后生效；失败后保留已提交组；mmap 槽代次、捕获标识和只读所有权；无命中点云；日志多线程、告警聚合、队列溢出、磁盘失败、残缺行和相对时间线；关节三种模式、TF 矩阵和采样时钟。

`reports/local_tests.txt` 中故意注入的 `test capture failure` 是验证部分采集失败收尾的测试数据，不是一次真实 Isaac 运行失败。

证据文件：

- `reports/isolation_check.json`：内部依赖与旧文件核对结果。
- `reports/original_files_before.json`：修改前原项目文件哈希。
- `reports/local_verification.json`：隔离副本测试元信息。
- `reports/local_tests.txt`：测试输出。

原生验收流程见 [implementation.md](implementation.md)。本地测试不证明驱动、Replicator 构建和场景资产已经兼容，也不构成性能提升百分比的依据。
