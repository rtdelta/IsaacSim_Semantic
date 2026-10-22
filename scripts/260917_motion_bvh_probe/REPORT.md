# Gaussian / Motion BVH 远端实验报告

日期：2026-09-17。结论针对本次机器和安装版本。

## 结论

当前 RTX 实现确实存在 Gaussian 与 Motion BVH 的兼容限制。绕过业务 Python 的配置检查后，仍能直接从 `rtx.scenedb` 复现 `Gaussians do not support motion BVH`。这不是仅修改应用层 guard 就能解决的问题。

原生 `ParticleField3DGaussianSplat` 也会触发此问题，因此不能把“转换为 ParticleField”当作这台机器上已经验证的修复。

已验证的可行方向是：传感器使用排除 Gaussian 的 Mesh 场景，开启 Motion BVH；Gaussian 视觉场景采用独立进程和关闭 Motion BVH 的配置。此次验证了传感器侧的场景隔离与运行，尚未实现双进程状态同步。

## 环境与文件保护

- Isaac Sim：`6.0.1-rc.7+release.42383.32955d8d.gl`。
- Kit：`110.1.2+production.326809.f9bf0dda.gl`。
- GPU：NVIDIA L40，驱动 `580.126.09`。
- 安装目录：`/root/isaacsim`。
- 远端实验目录：`/root/gpufree-data/diagnostics/motion_bvh_20260917_032416`。
- 真实组合场景：`/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_11_origin03.usda`。

实验前为资产目录及相关两个项目目录中的 93 个既有 USDA 建立 SHA-256 清单。全部实验完成后重新核验：`checked=93, changed=[], missing=[], unchanged=true`。记录在 `evidence/source_usda_before.json` 和 `evidence/source_usda_verification.json`。

每个测试使用新的匿名根层，仅导出到新实验文件。所有被引用的非匿名源层在进程内设置为禁止编辑和保存。Replicator 曾尝试向原始 RenderVar 所在层写入属性，被只读保护拒绝；后续在新根层预先定义 RenderVar 后完成实验。没有为解决这个错误解除原文件保护。

## 实验设置

最小场景由六面内侧距离原点 10 m 的 Mesh 墙体，以及一个引用真实牙齿 Gaussian 资产的对象组成。雷达采用独立覆盖配置：8 通道、10 Hz 扫描、1000 Hz 发射、每圈最多 800 个返回点，关闭测距噪声；通过官方 GenericModelOutput annotator 获取输出。Gaussian 经缩放和平移进入测量范围。

每组测试使用独立进程，包含 Play → Stop → Play → Stop。记录启动参数、实际 Carb 设置、组成后的 USD 类型、GMO 扫描完整标志、点数、有限值、时间戳、部分 NPZ 点云和日志。进程监督器只管理它自己启动的进程组。

真实组合场景测试使用 sublayer 完整组成所有顶层对象，禁用继承的业务 OmniGraph、已有传感器和 RenderProduct，并新增诊断雷达和测试墙体。因此，这是实际几何的兼容性实验，不是原业务流程的端到端验收。

## 主要结果

| 实验目录名 | 结果 | 判断 |
|---|---|---|
| `mesh_on_multi` | 两轮共 40 个完整扫描，每扫描 800 点 | Mesh + Motion BVH + multi-tick 基线通过 |
| `gs_off_multi_rgb` | 41 个完整扫描；798–800 点；保留 Gaussian 近处回波 | Gaussian 可被当前静态雷达路径测到；有 Motion BVH 未启用警告 |
| `gs_on_multi_rgb` | 41 个完整扫描，均为 800 点；Gaussian 近处回波为 0；3 次 Gaussian/Motion BVH 错误 | 输出点云不等于兼容成功，Gaussian 测量被丢失 |
| `gs_on_single_v2` | 关闭 multi-tick 后仍出现 Gaussian/Motion BVH 错误 | multi-tick 开关不是该几何冲突的充分修复 |
| `gs_hidden_on` | 40 个完整扫描 × 800 点；没有该冲突或 Motion BVH 未启用警告 | 全局隐藏 Gaussian 能避开冲突，但也会影响视觉 |
| `gs_inactive_on` | 40 个完整扫描 × 800 点；没有该冲突或 Motion BVH 未启用警告 | 从传感器场景停用 Gaussian 有效 |
| `mesh_moving_on` | 雷达按时间样本移动，两轮共 40 个完整扫描 × 800 点 | 动态输入可运行；没有做逐束运动真值验收 |
| `full_original_bvh_v3` | 组成 15 个 Gaussian 和 127 个 Mesh；记录 30 次 Gaussian 错误；停止后发生 GPU crash，最终进程非零退出 | 当前组合场景配置不可可靠运行；内部崩溃根因未做符号级定位 |
| `full_mesh_bvh_v3` | 停用 15 个 Gaussian，保持原显示变体；31 个完整扫描，798–800 点，正常退出 | 完整几何的隔离对照通过 |
| `full_source_mesh_bvh_v4` | 停用 15 个 Gaussian，并选择 `source_mesh`；31 个完整扫描，784–788 点，正常退出 | 使用原始 Mesh 变体的隔离方案通过兼容性测试 |

完整扫描是 GMO 的 `scanComplete` 标记，不能解释成“800 束都有回波”。真实场景中不同显示变体的返回点数不同，本轮没有进一步分解缺失回波的材质、遮挡及阈值原因。中间进度消息曾把完整场景简述为每扫描 800 点，以上完整统计予以更正。

最小静态对照保存的点云中，关闭 Motion BVH 时有 129 个距离小于 8 m 的返回；开启时为 0。开启后的返回均位于测试墙面，保存点云到最近墙面的最大残差约 `5.72e-6 m`。这个数值只验证静态测试房间，不代表 Gaussian 几何精度或运动补偿精度。

`gaussian_motion_bvh_comparison.png` 叠加第一次播放保存的缓冲，图中的 105 个近处返回是这一子集，不是单帧点数，也不是上述两轮保存数据的总数。

## Hydra 引擎掩码的实测边界

- 正确的字符串设置 `enabledForHydraEngines='0'` 仍触发冲突，近处 Gaussian 回波消失。
- 字符串 `'1'` 保留 Gaussian，但雷达明确提示 Motion BVH 未启用，因此不能作为运动雷达解决方案。
- 官方文档列出的字符串 `'0,1,2,3,4'` 同样复现冲突。
- 早期单编号参数未带字面引号，被 Carb 解释为整数；`gs_mask0` 至 `gs_mask4` 不用于判断有效引擎编号。它们保留在证据中，避免把无效设置误当作修复。

这说明已测掩码组合没有同时满足 Gaussian 和雷达 Motion BVH，不证明所有其他引擎隔离机制都不可行。引擎编号也不应被硬编码成通用的“相机引擎 / 雷达引擎”映射。

## 已生成的干净覆盖层

远端目录下保留以下新文件，本地镜像位于 `evidence/`：

- `sensor_mesh_overlay_v2.usda`：sublayer 引用原组合场景，对 15 个 Gaussian 写入 `active=false`，选择挖掘机 `visualization=source_mesh`。组成 142 个 Mesh，其中 132 个在默认时间可见。不含诊断墙体、诊断雷达或额外灯光。
- `visual_original_overlay_v2.usda`：仅引用原组合场景，保留原视觉组成。
- `isolation_overlay_validation_v2.json`：列出全部停用路径、所选变体及可见 Mesh。

这些覆盖层不修改原始 USDA。干净覆盖层仍继承原业务图和传感器；本轮运行验证使用的实验层额外禁用了它们。因此，干净覆盖层完成的是几何组成检查，不能声称原业务扩展已经集成或验收。

## 实现建议

核心目标应分为三项：保留 Gaussian 图像；让运动雷达有有效 Motion BVH；两者共享相同世界状态和时间。

当前安装版本上，最有实验证据的实现路径为：

1. **传感器进程**加载 Mesh 覆盖层，在进程启动时启用 Motion BVH，使用 multi-tick。所有需要参与雷达测量的动态物体都提供 Mesh 表达。
2. **视觉进程**加载保留 Gaussian 的覆盖层，关闭 Motion BVH。不能据此要求该进程提供经过验证的运动模糊。
3. **共享状态发布器**按仿真帧发布 `frame_id`、仿真时间、机器人各 link 世界变换及传感器外参。两进程按同一帧状态推进；生产实现还应处理超时、重启、丢帧和 Stop/Play 重置。
4. **几何验收**检查 Mesh 与 Gaussian 的配准，选择用于测量的真实表面，避免 URDF 参考外形和展示辅助几何混入雷达测量。
5. **时间验收**使用已知速度和已知表面的运动场景，对每束发射时刻计算交点真值，验证畸变和补偿误差。当前“有完整扫描”只属于兼容性验证。

如果必须直接得到 Gaussian 的运动雷达返回，另一条路线是关闭 Motion BVH 并按发射时间分片推进场景、采样和拼接点云。其时间分辨率、误差和计算成本需要专门实验；本轮未实现该方法。

直接修改 Python guard、关闭报错日志或仅验证点云非空都无法修复此次观测到的底层遗漏。

## 复现与证据

在远端实验目录执行，测试名称必须使用新的名称：

```bash
python3 run_case.py repeat_mesh --geometry mesh --bvh 1 --multi 1
python3 run_case.py repeat_gaussian --geometry gaussian --bvh 1 --multi 1
python3 run_case.py repeat_full_mesh --geometry full \
  --source /root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_11_origin03.usda \
  --exclude-gaussians --bvh 1 --multi 1 --frames 90 --timeout 120
```

`run_case.py` 统一配置动态库路径、文件句柄上限和超时。每组后期测试保存对应的 `probe_case_snapshot.py`，可核对当时真实运行的脚本版本。`process.json` 记录进程退出结果；原生崩溃时应结合 `progress.json`，不能只看不存在的 `result.json`。

核心证据：`analysis.json`、`evidence/summary.json`、各 case 下的日志/JSON/NPZ、源文件哈希和 `evidence.tar.gz`。GPU 崩溃 dump 还保留在远端 `full_original_bvh_v3` 目录中；证据压缩包以脚本、日志及数值数据为主。

被剔除的准备性实验：最初三个 `gaussian_*` 没有正确组成 Gaussian；`full_original_bvh` / `full_mesh_bvh` 只引用 defaultPrim，遗漏其他顶层对象；`full_*_v2` 被原始层只读保护阻止；直接启动导出辅助程序的一次初始化失败不属于 Gaussian 对照。相应日志全部保留。早期未增加内部灯光的黑色 RGB 图也未用于作出视觉结论。

测试结束后所有本任务启动的 Isaac 进程均已结束，GPU 显存恢复到约 668 MiB。其他业务代码、已有运行服务及 SSH 身份配置未修改。

## 官方资料与本次结果的区别

[RTX Sensors 文档](https://docs.isaacsim.omniverse.nvidia.com/6.0.0/sensors/isaacsim_sensors_rtx.html) 说明 Motion BVH 对运动传感器效果的作用及开启方法；本实验记录了实际设置和雷达警告。

[Gaussian Splats / Particle Fields 文档](https://docs.omniverse.nvidia.com/materials-and-rendering/latest/particle-fields.html) 描述较新的原生渲染和相机 motion blur 能力。它不构成这台 `6.0.1-rc.7 / Kit 110.1.2` 安装上 RTX Lidar 与 Gaussian Motion BVH 兼容的保证；本次实测仍然失败。
