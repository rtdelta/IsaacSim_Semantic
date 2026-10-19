# 挖掘机 mesh 资产精确重建交接包

请先阅读 [完整报告](MeshRawToExcavator_Reconstruction_Handoff.md)。本包封存了实际使用的五部件 mesh 输入、装配蓝图、重建程序、当前资产金标准和验收证据。

本包保证的起点是 `inputs/waji_mesh_corrected.usdc`。更早的单一合并 mesh 仅作为历史溯源，不冒充已经闭合的精确拆分流水线。

## 最短复现流程

1. 完整复制本文件夹到 Linux 机器，保留相对目录。
2. 执行 `python3 verify_package.py`，结果应为 `passed: true`。
3. 使用现有 Isaac SDK 执行：

```bash
cd /root/gpufree-data/semantic/scripts/260920SensorVisualizer/mesh_scene18/handoff
python3 -I -S -B launch_usd.py --isaac-root /root/isaacsim rebuild.py --output /root/gpufree-data/semantic/scripts/260920SensorVisualizer/mesh_scene18/my_reconstructed_excavator
```

输出目录必须不存在。脚本不启动 Isaac GUI，不需要 GPU、3DGS 或 Blender，不联网安装依赖。其他已有 OpenUSD/NumPy 环境可直接执行 `python rebuild.py --output 新目录`，但跨 SDK 不保证 USDC 序列化字节相同。

4. 查看新目录 `rebuild_verification.json`。本次已验证 `passed`、`composed_usda_identical`、`all_six_usd_files_byte_identical` 全部为 `true`。
5. 在 Isaac 中打开新目录的 `Excavator_Mesh_Contract.usda`。完整场景中的位置、传感器和背景接入见报告第 8 节。

主 USDA 和五个 USDC 的 SHA256 都应与 `evidence/rebuild_verification.json` 一致。`reference/Excavator_Mesh_Contract` 是已经部署资产的原样副本；其 `manifest.json` 是历史生成记录，不由新重建重复生成。

`scene_context` 保存场景根层作对照；背景、传感器等完整外部资产没有打进本交接包。它不是整套 combine scene 的离线包。
