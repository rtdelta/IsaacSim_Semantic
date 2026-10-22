# 网页依赖下载批次

状态：用户于 2026-10-09 明确选择“暂不下载，先完成其余代码”。本批次未下载、未安装、未构建。默认网页后端改用 Python 标准库 HTTP；可选 ASGI 后端保留源码，尚未运行验证。后续安装仍须取得本批次确认。

- 来源：`pypi.org`（发布元数据与发布 SHA-256）、`files.pythonhosted.org`（wheel 文件）。
- 版本清单：[requirements-web.txt](../requirements-web.txt)，共 14 项，显式锁定传递依赖。
- 用途：FastAPI/Uvicorn 独立网页进程和 WebSocket；不用于修改 Isaac、ROS、桌面或系统 Python。
- 本地下载位置：本项目 `vendor/wheels`，限 Python 3.12/Linux x86_64 二进制 wheel。
- 远端落点：`/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v05/vendor/wheels`，离线安装至项目 `.venv-web`。
- 校验：比对发布元数据给出的具体 wheel SHA-256，保存文件清单与安装日志。仅自行计算哈希不足以证明来源可信。
- 执行：创建项目 venv、仅从已校验本地 wheel 安装依赖，启动项目网页服务；不执行源码构建或远程安装脚本。
- 如版本不存在、平台 wheel 缺失或需要新增文件/来源，重新准备变更清单，不静默换版本。
