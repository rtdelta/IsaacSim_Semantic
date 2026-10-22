# 场景18 mesh挖掘机替换：执行报告

日期：2026-10-12。目标：在场景17基础上替换五个3DGS挖掘机部件，保留坐标、关节、传感器和其他场景内容。用户明确要求采用完整带齿mesh铲斗。

## 交付结果

新组合场景：

```text
/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_18_terrain_fisheye_mesh.usda
```

新挖掘机资产：

```text
/root/gpufree-data/IsaacSim_Asset/excavator_module_set/Excavator_Mesh_Contract/Excavator_Mesh_Contract.usda
```

方案、源代码分别位于项目的 `docs/20261012_scene17_mesh_excavator_implementation_plan.md` 和 `mesh_scene18/`，本地与远端均保存。旧场景、旧3DGS资产及旧采集代码没有被替换。

## 坐标校正依据

从当前原始坐标的track 3DGS和历史校正坐标的track 3DGS恢复同一刚体变换，使用 cab、boom、arm 的同序点独立交叉核对。最大残差为 `1.65613255e-7` 原始坐标单位。不是用最近邻ICP将不同形状强行拟合。

原始完整mesh与现有校正mesh均为317675个顶点；应用该变换后，按1mm网格舍入的顶点匹配率为99.9946486%，128个均匀索引抽样点的最近顶点最大距离为 `1.21677366e-7` 原始坐标单位。舍入匹配率和抽查不等于逐顶点全量精确对应证明，二者作为历史变换的交叉证据。

USD采用行向量记法：

```text
mesh_world = mesh_corrected * corrected_to_raw * existing_Visuals * existing_link_world
```

保留现有Visuals中的原始坐标到当前部件坐标的矩阵，因此2.4倍素材缩放仍只应用一次。校正矩阵存于每个Visuals下的新MeshAlignment节点。根节点、刚体部件节点和关节坐标系不被重新居中。

## 几何与材质

| 当前部件 | 来源mesh | 顶点 | 三角面 |
|---|---|---:|---:|
| track_link | track_mesh | 101771 | 200806 |
| swing_link | operator_cab_mesh | 116099 | 229912 |
| boom_link | boom_mesh | 57635 | 114781 |
| arm_link | small_arm_mesh | 23764 | 47013 |
| bucket_link | bucket_only_full_teeth_mesh | 18406 | 36356 |
| 合计 | | 317675 | 628868 |

逐部件验证原始points、faceVertexCounts、faceVertexIndices、normals和Col颜色数组与新资产完全相同。mesh本身没有材质绑定，故将原有线性RGBA顶点色的RGB映射为displayColor，再绑定UsdPreviewSurface；alpha检查为全1，roughness设为0.8、metallic为0。没有添加外部纹理，没有引入来源文件的相机、灯光或旧关节。

铲斗完整保留铲齿。mesh和3DGS的表面表示及细节本来不同；相同装配尺度和坐标映射不意味着表面轮廓、外包围盒或点云逐点完全相同。本次没有通过非均匀拉伸或修改顶点来消除这些差异。

## 静态与运动检查

- 889个非替换几何节点：类型、活动状态、schemas、自定义数据、属性和关系对比无差异。
- 343个Xformable节点：替换前后世界矩阵最大绝对差为0。
- 13路OmniLidar、4路鱼眼相机保留；其他场景相机也在上述非几何对比范围内。
- 合成后的活动场景中Gaussian prim数量为0。
- 9组内存规定运动检查：初始姿态，组合正负角度＋整机变换，以及大臂、小臂、铲斗各自±15°。保留节点的世界矩阵差为0，mesh变换链最大误差为 `8.88e-16`。
- 内存变换检查不是动力学仿真认证；实际引擎规定运动与录包另见下节。

原场景及依赖文件哈希存于 `mesh_scene18/backups/20261012T094456Z/source_hashes.json`。构建和静态验证时均未变化。源场景17 SHA256：`2e1503a3b34fc23b2f2273fb502c2c0a1e83b39722eaa075bdd4fe94372d51a2`。

## 实际引擎与MCAP验证

独立无窗口Isaac进程，采用保留的 `single06_lab/frozen_runtime` 代码，未修改该版本。单卡L40；RealTimePathTracing、DLSS Quality、16个相机预热子帧＋2个正式子帧、传感器资源常驻。

输入为场景18生成的三组状态：初始状态；大臂/小臂/铲斗+15°并平移、旋转整机；三关节-15°并平移、旋转整机。回转关节保持原控制策略。

测试输出：

```text
/root/gpufree-data/semantic/output/mesh_scene18/smoke_20261012_094955/
  result.json
  engine.log
  job.json
  input_trajectory/
  decoded.json
  images/{front,back,left,right}/
  captures/20261012_175012_482511_75deddca/bag_unified/
```

| 验证项 | 结果 |
|---|---|
| 引擎退出、数据验证、图片解码 | 均通过，退出码0 |
| 采集组数 | 3 |
| 点云 | 13路×3组＝39帧 |
| 图像 | 4路×3组＝12张，1920×1080 RGB |
| MCAP | 41650864字节，约41.65MB |
| 话题、消息 | 32个话题、92条消息 |
| 每组TF边 | 19 |
| 源轨迹时刻 | 0、0.1、0.2秒 |
| 实际消息时刻 | 133333333、233333333、333333333纳秒 |
| TF与记录的传感器矩阵最大误差 | 8.88e-15 |
| 整机位置对输入轨迹最大误差 | 5.29e-8米 |
| 关节角对输入轨迹最大误差 | 7.29e-9弧度 |
| 图像内参与消息内容哈希 | 验证通过 |
| 新场景磁盘文件 | 测试前后哈希一致 |

从实际MCAP解码图片，检查了首组前后鱼眼图像；前向图像可见完整带齿mesh铲斗、大臂和用户摆放的物体，颜色正常。全部图像通过非空、尺寸、格式和时间对应检查；不将这些检查称为像素级复现3DGS。

三组采集含排空约13.79秒，独立引擎进程约67.26秒。与先前场景16的性能实验输入不同，不能据此宣称性能提升倍数。

## 警告与限制

日志0条Error、103条Warning。可见类型包括已有的RobotMotionSchema路径、动画节点注册、音频设备、Cache Server、nvperf库、MotionBVH关闭提示和hydratexture接口释放警告。未观察到新mesh的材质/几何加载失败，录包和位姿验证通过，但不宣称引擎warning已解决。原采集链路的MotionBVH设置未变，本轮为冻结采集。

此次不修改系统、驱动、桌面、SSH或Python依赖，没有新增外部下载。仅使用已有USD、NumPy、Isaac和ROS环境。部署曾因工具把编码文本判为疑似秘密而被拒绝，改用可审阅UTF-8源码传输后成功；一次构建前哈希检查遇到USDZ内部路径，修正为对外层包文件哈希后重新执行。该次失败发生于创建资产之前，没有覆盖源文件。

## 使用与回退

在远端File → Open打开场景18即可检查和编辑资产。采集任务的scene参数需明确指定场景18；旧版本默认配置没有被修改。旧轨迹若绑定场景16哈希，需要在新场景重录或明确迁移，不能直接绕过校验。

回退只需重新打开场景17。所有源资产保留；本地另保存新挖掘机资产及验证报告、日志和解码图片的哈希一致副本。
