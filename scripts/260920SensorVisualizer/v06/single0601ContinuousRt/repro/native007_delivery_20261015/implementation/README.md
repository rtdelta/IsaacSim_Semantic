# 007 原生旋转偏差分层实验

本目录是独立诊断入口，代码与输出均不覆盖 005/006。方案在 `docs/Experiments/007_原生旋转偏差分层定位_下一阶段测试方案.md`，实际执行记录在相邻 008 文档。

## 入口和证据

- `run_layers.py`：单推进者、固定输入表、原生四 annotator 与可选官方 LidarSensor API；有界自有字节复制和写盘。
- `math_independent.py`、`normalizer.py`、`ray_model.py`：独立 GMO 布局、SENSOR/WORLD、Cartesian/Spherical、名义射线和六平面求交。
- `analyze_independent.py`：原始文件 SHA 全回读、源时间唯一关联、输入与静态资格、距离/方向/几何分层指标；不能用于“修正”源时间。
- `compare_layers.py`、`compare_interventions.py`：完整射线身份集合、单因素与扫描语义资格；不得以交集筛选替代完整分母。
- `analyze_header_models.py`：对外 GMO 起止姿态的固定预测，仅 E2 证据，不是实际内部消费追踪。
- `coordinator.py`：有限预登记序列，单 Kit，最多四轮资源批次，失败停止，相应分支静态资格失败后阻断动态。
- `continue_declared.py`：只执行已登记阶段；不会自行新增条件、下载、重试失败或修改门槛。

`config/native_rotation_localization/v1/main_code_lock.json` 冻结正式长轮采集与分析代码；后续条件采用新 spec，不能修改锁定文件。每轮原始报告均保留，包括 q01 球坐标交叉检查错误和 q02 官方射线模型修订前结果；最终重放写入 `analysis_final/`。

远端所有动作经本项目 `tools/remote_ops.py` 的固定实例、主机指纹及本地审计执行。各 `*_remote.py` 只在已核验的单 L40 实例使用；切换实例先核验身份和配置。所有实验结果固定 `formal_continuous_acceptance=false`，不发布正式 READY。
