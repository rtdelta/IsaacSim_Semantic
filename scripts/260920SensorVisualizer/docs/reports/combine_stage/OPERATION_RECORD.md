# 2026-09-21 新传感器组合场景部署记录

- 目标：把最新旧项目传感器接到合同版 3DGS 挖掘机，生成独立 combine stage。
- 目标实例：`root@120.209.70.195:30729`；通过已知主机记录校验身份。未连接旧实例 30162。
- 授权：用户明确要求接入传感器并组装新场景；沿用新项目本地和远端保存源代码的要求。
- 执行渠道：Codex 经本地 Paramiko SSH/SFTP；无凭据落入此记录。
- 项目路径：`/root/gpufree-data/semantic/scripts/260920SensorVisualizer`。
- 操作前：GPU L40 约 606 MiB、利用率约 2%；没有发现正在运行的 Isaac GUI 进程。相关 donor 为 scene12，尚无 scene13。

## 实际操作

1. 只读核对 scene12：7 台 MyAiry、6 台 MyNZ3、1 台大臂相机及 Fangshan 环境。
2. 使用已安装 OpenUSD/NumPy 读取新旧几何。验证 track/cab/boom 为相同同序高斯集合，求刚体坐标转换，保留物理安装位置。
3. 新增 `config/combine_stage.json`、构建器、验证器、项目使用说明；生成 `combine_scene_13_3dgs_contract.usda`。首次构建遇到目标父节点在当前层尚无 spec 的异常，补上父 spec 后成功。失败中间文件归档于 `attempts/missing_parent_spec.building.usda`。
4. 启动独立无窗口验证。第一次在旧在线地面引用的加载阶段等待较久；只终止本任务创建且核验命令行的测试 PID 104868。保留 `attempts/online_grid_runtime.log`。
5. 将同一 NVIDIA 官方网格 USD 和三张贴图原样缓存至项目 `assets/NvidiaGrid/`，并部署到 `IsaacSim_Asset/environment_module_set/NvidiaGrid_6_0/`。来源 URL 和 SHA-256 在 `source_manifest.json`。新场景改用该本地引用，旧场景不变。
6. 第二次验证完成安装/运动/点云检查，但退出时超过进程文件句柄软上限 2450，出现 `Too many open files` 和 CUDA/Vulkan 资源创建错误。仅终止本任务测试 PID 119681，保存 `attempts/fd_limit_runtime.*`。该尝试的 JSON 检查结果为 true，不代表进程成功退出。
7. 为验证启动器增加进程级 `ulimit -Sn 16384`；同时检查测试结果和进程退出码。最终验证在北京时间 10:35 左右正常完成，退出码 0，无 Error。提供同样进程级上限的 GUI 启动器，未代替用户新开 GUI。
8. 同步工具默认 SSH 端口从旧实例更新为 30729，并排除历史 `diagnostics/`、`migration/`。仅选择本次源码/文档进行上传，没有运行全目录旧版 push。

## 结果与证据

- 最终 scene13 SHA-256：`780cab54e1067c3fef6c2a66b0e6b5776c06164645957f7716bbc159c9e8c4d6`。
- `build.json`：14 个挂载的全量几何比对、传感器属性一致性、4 关节零位、渲染关系目标。
- `runtime.json` / `runtime.log`：场景组合无缺失；零位与组合姿态通过；13 路各 2 个完整新帧；退出码 0。
- `bind_scene.png` / `combined_scene.png`：已人工视觉检查的实际渲染预览。
- 原 donor 场景与独立挖掘机资产指纹保持不变；源传感器文件未写入。
- 未安装、卸载或升级库/系统；未修改桌面组件、SSH、preload、服务和全局资源上限。
- 仍有 Motion BVH 关闭、音频/性能/Fabric 数组类型等警告；未验证运动畸变补偿、ROS/MCAP 联调和长期采集。

## 恢复依据

新增场景独立命名，停止使用它即可回到旧场景。在线网格版本的 scene13 在 `backups/` 保留；旧 donor 和独立资产没有被替换。缓存文件位于新增专用目录。资源上限随本次进程退出而结束。未实际执行回退，因为最终验证通过。
