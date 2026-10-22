# 2026-09-20 资产与代码迁移

来源：120.209.70.195:30162。目标：120.209.70.195:30729。
迁移根目录保持为 `/root/gpufree-data`，不修改资产内容或项目源代码。

## 范围

- IsaacSim_Asset：场景、挖掘机、环境、相机与 LiDAR 资产，以及原有 Git/LFS 数据。
- semantic/scripts：各版本项目代码、配置、文档、测试脚本和输入素材。
- semantic/projects、semantic/Materials、semantic/docs：项目配置与说明资料。
- Blender 工程、原始 PLY/网格、Test0/Test1 中的装配与参考素材、NZ3 标定数据。
- 诊断项目保留源码、说明、配置和测试场景，不搬运大体积实验结果。
- 轨迹文件可能作为回放输入，予以保留。资产预览图属于项目说明资料。

不迁移 `semantic/output` 历史采集结果、MCAP、DB3、运行日志、字节码、运行缓存、旧虚拟环境、诊断第三方二进制环境和 alist 文件服务状态。
具体范围以 `selection.json` 和 `excluded.json` 为准。

## 传输与验证

1. 通过旧实例的原始目录读取系统调用建立文件清单。
2. 新实例公网回连旧实例被拒绝，改用可达的内网地址 `100.122.231.108:22`。
3. 内网连接仍严格校验本地已知的旧实例 SSH 公钥；没有关闭主机密钥检查。
4. 新实例主动拉取；旧实例只收到只读导出脚本和文件清单，未收到新实例凭据。
5. 旧实例存在已确认的 LD_PRELOAD 读取过滤，导出使用直接 read 系统调用，SSH 数据流全部用 Base64 编码，避免过滤破坏文件内容。
6. 核对源文件尺寸、修改时间及传输前后状态。源端计算 SHA-256，目标端校验接收字节，再从目标磁盘读取并复核 SHA-256。
7. 文件先写入 `.migration-partial`，校验通过才发布为正式文件；不覆盖未核验的同名目标文件。

密码仅经标准输入和目标端临时进程环境传递，没有保存在这些脚本、清单或日志中。
不安装/升级系统软件、不修改桌面、SSH、cron 或 `/etc/ld.so.preload`，不克隆旧系统环境。
文件一致性校验不代表对旧源码进行了完整安全审计；迁移过程中不执行旧项目代码。

## 文件说明

- `source_inventory.json`：迁移前源数据盘文件清单。
- `selection.json` / `selection_summary.json`：选定文件及容量统计。
- `excluded.json`：排除项与理由。
- `export_source.py`：通过 SSH 标准输入执行的只读源端导出器。
- `receive_files.py`：目标端接收、断点恢复与校验程序。
- `askpass.py`：从进程环境读取源实例密码的 SSH 辅助程序，不含密码。
- `source_known_hosts`：源实例 SSH 公钥，非私钥。
- `verified.jsonl`：每个迁移文件的 SHA-256、尺寸和磁盘复核结果。
- `status.json`：迁移状态；`state=complete` 才表示所选文件已全部完成。
- `asset_dependencies.json`：使用新实例原装 USD 库检查场景引用；不启动 Isaac GUI 或仿真。

远端作业目录：`/root/migration_jobs/assets_code_20260920_to_30729`。
本地目录：`D:\learning\IntelligentDepartment\CodesSet\Self\260707IsaacSIm\scripts\260920SensorVisualizer\migration\20260920_to_30729`。

新实例已有 Isaac Sim 6.0.1-rc.7 和 ROS 2 Jazzy。此次迁移不等同于逐个应用的运行环境安装或 GUI 验收。
