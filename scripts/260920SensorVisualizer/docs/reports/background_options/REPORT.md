# 背景选项恢复记录

- 日期：2026-09-22；目标：isaac-new。
- 用户要求：在新起伏地面场景中保留旧平面、3DGS 地面和全部原贴图，由用户自行控制使用哪些。
- 修改场景：`/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_16_terrain_fisheye.usda`。
- 原场景 scene 13、scene 15、原地面及材质资产未修改。

## 实际改动

1. 恢复 `/FlatGrid/Environment/Geometry` 显示，保留其 `/FlatGrid/Looks/theGrid` 材质和三张原网格贴图。
2. 恢复 `/FlatGrid/GroundPlane/CollisionPlane` 的源资产碰撞设置和显示属性。
3. 在 scene 16 根层将 `/environment_Fangshan_02/changjing4` 设为 active=true，覆盖旧场景对这个 3DGS 地面节点的停用。源高斯数据保持原样。
4. 保留原 DomeLight 天空贴图、围栏及其贴图、现有起伏地面，默认全部启用；不添加自动互斥开关。
5. 更新地形组装工具，后续生成不再自动隐藏旧地面；更新使用说明及对应场景检查。

使用 Stage 可见性控制选择背景，建议将编辑目标设为 scene 16 根层再保存。碰撞属性独立于显示属性。若多个地面相互遮挡，可隐藏其中不需要的项。新旧场景节点路径保持原样，未搬移传感器或改变采集逻辑。

## 验证范围

- USD 场景组合无错误；3DGS 节点恢复后含 981377 个高斯中心。
- 8 个唯一旧贴图资源均可通过 USD 解析并打开读取，包括 USDZ 内嵌纹理。
- 13 个 OmniLidar 和挖掘机下 5 个 Camera 节点保持完整（4 个鱼眼相机加原相机）。
- scene 13、scene 15 哈希与修改前相同；新场景仅改变背景覆盖及说明元数据。
- 本次未启动额外 Kit 渲染、未重新录制数据。历史 tilt_terrain 渲染验收对应修改前的地面显示组合，不代表全部背景同时显示时的效果。
- 无外部下载、无安装、无系统配置或进程变更。

## 文件与回退

改动前 scene 16、改动后副本和验证明细保存于本地及云端项目的 `reports/background_options/20260922_072143_460316/`。当前本地场景副本另存 `scenes/combine_scene_16_terrain_fisheye.usda`，相对资产路径对应云端资产目录布局，并非独立打包的场景。

恢复原先“仅新地面”的版本，可在停止编辑后用该目录的 `before_combine_scene_16_terrain_fisheye.usda` 还原 scene 16。更简单的显示选择可直接在 Stage 面板修改并保存。

执行渠道：Skill 的审计 SSH 包装器；连接指纹和已登记实例身份经过核验，执行日志保留在本地 CloudInstanceOps 审计目录。诊断和部署输入位于项目 `diagnostics/20260922_background_options/`，代码部署也记录在既有 tilt-terrain 任务审计中。
