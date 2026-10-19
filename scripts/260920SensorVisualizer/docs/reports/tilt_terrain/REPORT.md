# 整机倾斜与起伏地面交付报告

日期：2026-09-22。目标实例：isaac-new。代码位于本地及云端的 260920SensorVisualizer 项目。

## 交付

- Whole Excavator Motion 新增 World Z / Apply Height。
- Pitch、Roll 各自支持 Direct set、Target + speed、Periodic，沿用关节角度控制器的匀速到达与往复规则。
- 倾斜为相对启动姿态的偏移；旋转顺序、数学范围、控制按钮和复位规则见 TILT_TERRAIN_USAGE.md。
- 车体运动后统一刷新 Articulation、USD/Fabric、TF、四路相机及雷达位姿；相机帧元数据新增 base_control，录制会话记录地形配置和资产哈希。
- 在已有 Blender 5.1.1 中生成 40×40 米、40401 顶点、80000 三角面的地形，峰谷高差 0.9 米；保存 .blend、.usdc、配置和生成脚本，本地云端都有源码和地形资产。
- 新场景：/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_16_terrain_fisheye.usda。
- scene 15、鱼眼源资产保持原字节；无自动贴地、地形高度补偿或履带动力学。

## 验收证据

- 12 项数学测试通过：原平面运动兼容、四元数组合、直接角度、目标停止、双轴周期、时间步长独立、原点保持、手动 Z、Hold/Reset 和批量参数原子校验。
- 独立 Isaac GUI 验证 23 项通过，包括实际面板回调、暂停时设置姿态、Tilt 与整机/关节组合运动、重置、scene 15 兼容。测试使用 ROS domain 141，测试进程均已退出。
- 完整采集：12 个采集组、48 张 1920×1080 PNG、13 路雷达共 156 帧非空点云。每个图像组均匹配所有 13 路点云及 TF；缺失组 0、图像位姿匹配失败 0。
- 直接设置整机姿态的矩阵误差：4.25e-08；安装相对矩阵最大误差：4.22e-07。
- 渲染相机矩阵与保存元数据最大元素差：1.78e-15；组合 TF 四元数与图像位姿最大分量差：7.26e-08。
- LiDAR 抽样点在地形区域中存在高于 +0.12 米和低于 -0.12 米的地面回波，分别 18769、13046 个抽样点；不是只替换平面的颜色。
- 正式验收包：/root/gpufree-data/semantic/scripts/260920SensorVisualizer/reports/tilt_terrain/recordings/20260922_145340_385006_241b77。

## 起始边界与日志

第一组图像（仿真 0.8 秒）未对应到附加的 volatile `/excavator/root_pose` 消息；后续 11 组全部准确匹配。该首组完整姿态存在于 `/tf` 以及四路 frames.jsonl，因此本次验收要求的每帧位姿有来源。报告保留 `root_pose_topic_covers_every_image=false`，没有补写、插值或伪造缺失消息，也没有改动原采集节拍。

最终 Kit 日志没有 Error 或 Python traceback。保留现有 SDK 的 Hydra 释放、传感器材质接口、Writer 元数据等警告，详见 log_summary.json；没有通过修改系统设置来压制这些信息。

## 本次发现并处理的问题

- Blender 在继承其他程序运行库路径时出现 TBB 符号冲突。使用仅作用于 Blender 子进程的 LD_LIBRARY_PATH=/opt/blender/lib 后正常运行，没有修改系统库。
- Blender 5.1 USD 导出接口与旧参数不同，已按安装版本修正，成功导出。未完成的 .blend 留存在远端 reports/tilt_terrain/before_metadata_fix 中，发布资产目录仅保留完成文件。
- 第一版 scene 16 遗漏 scene 15 的根层元数据，原生 LiDAR buffer 始终为空。补齐源场景顶层元数据后，scene 16 与 scene 15 的前后暂停对照均正常出点。构建工具现已保留这批元数据；首次失败证据在 before_metadata_fix/ 中。
- 独立诊断曾更新自动生成的 RViz 配置；已恢复默认 domain 0 和正式输出目录。诊断脚本后续使用独立 artifact_dir，正常入口仍会重新发现当前场景。

## 文件、回退和完整性

- 使用：项目根目录 TILT_TERRAIN_USAGE.md。
- 本地地形：assets/UndulatingGround_20260922/；云端地形：/root/gpufree-data/IsaacSim_Asset/environment_module_set/UndulatingGround_20260922/。
- 本地新场景副本：reports/tilt_terrain/combine_scene_16_terrain_fisheye.usda；新场景 SHA256：dd7fa9efa0d5edf6e4ddef4bff42555023b22d4705efed1d6c6e0293f07abb41。
- 新场景副本保留云端资产的相对引用；在本地单独打开它仍需对应的完整资产目录。terrain.blend 是可独立编辑的地形文件。
- 改动前代码备份：本地和云端 reports/tilt_terrain/before/。回到旧地面可打开 scene 15；新增倾斜偏移设 0 即恢复旧姿态行为。需要完整旧源码时关闭会话后恢复 before 中对应文件。
- 传输文件逐一校验 SHA256，清单见 artifact_transfer.json；远端部署使用原文件哈希检查、备份、临时文件替换。哈希只证明本次内容一致。

## 下载规则

已更新本地安装的 cloud-instance-ops Skill 及 scripts/260922CloudInstanceOps/skill 中的维护副本。新增外部文件下载前要提供批次清单并取得用户确认；已有具体批准的批次不反复询问。本次使用既有软件和程序化素材，没有安装/升级库或新增第三方文件下载。

此确认规则由 agent 执行，CLI 没有弹窗或系统联网拦截功能。操作审计保存在本地 CloudInstanceOps 状态目录，SSH 使用已登记凭据引用和主机指纹。
