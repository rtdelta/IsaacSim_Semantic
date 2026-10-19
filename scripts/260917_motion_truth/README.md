# 260917_motion_truth

## 离线分析依赖

在 Python 3.9 环境中执行 `python -m pip install -r requirements-analysis.txt`。几何分析从环境导入 `trimesh`，不再把项目内的 `vendor/` 加入模块搜索路径。本地原安装副本保留，但不随代码上传。

运行 `python -m unittest test_deskew test_geometry_dependency -v` 可核对插值与几何依赖的距离约定。`analyze_geometry.py` 还需要原实验的 `geometry/geometry.json` 和对应数组；这些属于外部实验数据，仓库不包含它们。本次依赖验证使用已存在的 4.12.2 副本复制到本地隔离依赖区，没有联网安装或升级全局环境，也没有重新计算整场景几何实验。

## 报告与验收证据

正式报告、精选验收摘要和必要配图见 [报告索引](docs/reports/README.md)。原始采集、逐帧状态和性能追踪保留在原运行目录，由仓库忽略规则排除。
