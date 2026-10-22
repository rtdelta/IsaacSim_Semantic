# Scene18：mesh 挖掘机替换

状态：已于2026-10-12在单卡实例构建并通过静态、运动与MCAP采集验证。

## 打开新场景

在远端 Isaac Sim 的 **File → Open** 打开：

```text
/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_18_terrain_fisheye_mesh.usda
```

打开资产不需要运行构建脚本。原场景17保留不变；新场景包含五部件mesh挖掘机，铲斗完整保留铲齿，其他场景与传感器沿用场景17。新场景仍依赖原有场景15、传感器和环境素材，不能只拷贝单个combine文件当成独立完整场景。

独立挖掘机资产：

```text
/root/gpufree-data/IsaacSim_Asset/excavator_module_set/Excavator_Mesh_Contract/Excavator_Mesh_Contract.usda
```

该资产及其 `geometry/` 是相对路径的完整mesh挖掘机，默认根节点仍为 `/Excavator`。全部网格、顶点颜色、法线及拓扑保留；顶点颜色通过 UsdPreviewSurface 显示，不需要外部贴图下载。

## 后续采集配置

采集器配置的 `scene` 必须明确指向场景18；原有版本默认仍可能打开场景16。本次没有修改旧版本的默认配置。

沿用之前的 v06 常驻资源方案：`mode=offline`、`capture.resource_policy=keepalive`、RealTimePathTracing、16个预热子帧＋2个正式子帧。旧场景录制的轨迹可能绑定旧场景哈希，应在新场景重新记录，或明确完成轨迹迁移，不能直接关闭哈希检查。

本次三组验证的任务配置可查看：

```text
/root/gpufree-data/semantic/output/mesh_scene18/smoke_20261012_094955/job.json
```

## 本目录脚本

| 文件 | 作用 |
|---|---|
| analyze_alignment.py | 利用同序3DGS点恢复历史刚体变换，跨部件和原始mesh核对 |
| build_assets.py | 构建新mesh资产与场景18；拒绝覆盖已存在的目标 |
| validate_assets.py | 非几何节点、变换、网格数组、材质和9组内存运动验证 |
| runtime.py | 调用已安装Isaac USD解释器，不启动Kit、不下载依赖 |
| prepare_capture.py | 根据场景18本身的传感器安装位姿生成3组测试轨迹 |
| capture_supervisor.py | 复用保留的v06采集代码，有限时运行、录包校验和解码 |
| start_capture.py | 启动一次新的独立测试，遇到已有Kit时不停止它 |
| status_capture.py | 读取本任务采集状态与日志 |
| prepare_operation.py | 本地Windows侧生成审计工具的部署/执行脚本 |
| pull_artifacts.py | 本地Windows侧通过已登记身份拉取生成资产和验证证据 |

这些脚本是资产制作与验证工具，不替换已有Sensor Visualizer面板。

## 记录与回退

- 完整方案：`../docs/20261012_scene17_mesh_excavator_implementation_plan.md`。
- 执行报告：`../docs/20261012_scene18_mesh_excavator_execution_report.md`。
- `build_manifest.json`：文件来源、哈希、校正矩阵、网格统计和备份位置。
- `validation.json`：静态与内存运动检查。
- 本地 `evidence/`：实际采集报告、日志和12张从MCAP解码的图像。
- 本地 `deployed/`：生成mesh资产的校验一致副本；combine场景的旧环境依赖未全部拷贝到此处。
- 回退：重新打开场景17，无需修改旧资产或系统环境。

## 报告与验收证据

正式报告、精选验收摘要和必要配图见 [报告索引](docs/reports/README.md)。原始采集、逐帧状态和性能追踪保留在原运行目录，由仓库忽略规则排除。
