# 整机俯仰、横滚与 Blender 起伏地面

## 启动

云端桌面终端运行：

```bash
bash /root/gpufree-data/semantic/scripts/260920SensorVisualizer/tools/open_terrain_stage.sh
```

打开的是新场景：

```text
/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_16_terrain_fisheye.usda
```

在 Isaac Script Editor 中打开并运行：

```text
/root/gpufree-data/semantic/scripts/260920SensorVisualizer/run_in_isaac.py
```

保持 `Scripted control + publish` 模式，点击 `Play Simulation` 完成初始化。面板在 `Whole Excavator Motion` 中提供下列新增控件。

## 高度与倾斜

- `World Z (m)` → `Apply Height`：直接设置挖掘机根参考点的世界 Z；它不是履带底部离地高度。不会读取地形高度，也不会自动贴地。
- Pitch：绕 Y 轴的俯仰分量；Roll：绕 X 轴的横滚分量。使用右手正方向，面板角度单位为度。
- 两行均显示相对启动姿态的偏移角。0 表示恢复启动倾斜，不保证车身绝对水平。
- `Direct set`：填写 `Target`，点击 `Apply`，立即设置；初始化后暂停时也可使用。
- `Target + speed`：填写 `Target` 和正值 `Speed`，点击 `Start`，在 Play 时以指定速度移动，到达后保持。
- `Periodic`：填写 `Lower / Upper / Speed`，点击 `Start`，在上下限之间往复。默认上下限 ±15°、速度 5 度/仿真秒。
- `Start Both Tilts` 只启动设置为 Target 或 Periodic 的行。Direct set 用各行 Apply。
- 单行 `Hold` 只停止该项；`Hold Both Tilts` 停止两项；`Hold Base` 停止整机平移、Yaw 和两项倾斜。
- `Reset Base` 恢复整机初始 XYZ、Yaw、Pitch、Roll，不改变大臂等关节角度。Stop 恢复完整启动状态。
- 切换某一倾斜模式时，该项先保持当前角度，填写后再 Apply/Start。Pause 冻结时间，恢复 Play 后继续原命令。

角速度按仿真时间计算。真实时间倍率仍不高于 0.1；四相机渲染可能进一步降低倍率。

## 坐标和旋转约定

列向量约定：`R = Rz(Heading) Ry(initialPitch + pitchOffset) Rx(initialRoll + rollOffset)`，内部使用四元数，交给 USD/Gf 时转换为其矩阵约定。Heading 控制车体 X 轴在世界 XY 平面的朝向；前后移动沿该水平朝向，不沿倾斜后的三维 X 轴爬升。

旋转中心是现有挖掘机根参考点，保留原 robot-reference / articulation-root 偏移关系。cab–track 关节维持原初始角；传感器安装相对变换保持不变。

Pitch 的绝对 Euler 分量限定在 ±89° 内，避免 Heading 奇异；面板显示的是换算后的偏移范围。Roll 偏移范围为 ±180°。这些是本控制器的数学范围，不是实车机械限位。

旧 scene 15 仍可使用同一脚本。Pitch/Roll 偏移为零时保持旧版本的姿态行为。

## 起伏地面资产

```text
/root/gpufree-data/IsaacSim_Asset/environment_module_set/UndulatingGround_20260922/
  terrain.blend
  terrain.usdc
  terrain_config.json
  build_report.json
```

地面由云端已有 Blender 5.1.1 的脚本生成，40×40 米、网格步长 0.2 米、峰谷高差 0.9 米，固定随机种子 20260922。世界中心为 (-1.8, 1.5, 0)。起始车体附近保留平缓区域，周围为平滑凸起、浅坑和坡面。使用程序化地表色块，无外部贴图、插件或模型下载。

新的 scene 16 引用 scene 15，保留旧平面、3DGS 地面、原背景与材质贴图，并增加起伏地面。2026-09-22 按用户要求取消旧平面的隐藏覆盖，并在新场景层恢复被旧场景停用的 3DGS `changjing4` 节点。各背景默认全部保留并启用，由用户选择显示项；不改动旧场景或原素材。新地面不驱动车体接触运动。

在 Stage 面板通过以下节点的可见性分别控制背景（`inherited` 显示、`invisible` 隐藏）：

| 内容 | 节点 |
| --- | --- |
| 旧网格平面及其贴图 | `/FlatGrid/Environment/Geometry` |
| 旧 3DGS 地面/重建背景 | `/environment_Fangshan_02/changjing4` |
| 旧环境天空贴图和环境光 | `/environment_Fangshan_02/DomeLight` |
| 新起伏地面 | `/World/UndulatingGround` |
| 旧场景围栏等带贴图物体 | `/environment_Fangshan_02/langan`、`langan_01` 等 |

网格材质仍在 `/FlatGrid/Looks/theGrid`，纹理文件保留原路径；其他物体的材质和纹理保留在原 USDZ 中，不重新下载或复制绑定。3DGS 的外观来自自身高斯颜色数据，不是单独的地面贴图。原碰撞平面 `/FlatGrid/GroundPlane/CollisionPlane` 恢复源资产的碰撞设置；显示开关与 `physics:collisionEnabled` 是两项独立属性。

这些地面可能彼此遮挡，选择需要的组合即可；只想看起伏地面的凹陷时，应隐藏挡在上方的旧平面和 3DGS 地面。编辑目标选 scene 16 根层再保存，可保留选择且不改变旧文件。若只写 Session 层，普通保存不会保留这项选择。若场景已打开，请先另存自己尚未保存的修改，再重新打开磁盘上的 scene 16；无需重启实例。

生成源码：`tools/build_terrain_blender.py`；参数：`config/terrain.json`；组装：`tools/build_terrain_stage.py`。生成工具拒绝覆盖已有资产或场景，改参数后应输出到新的目录/场景。

启动 Blender 时使用它自己的运行库，避免继承其他程序的 TBB 路径。示例（另存新资产目录）：

```bash
env -u LD_PRELOAD -u PYTHONPATH -u PYTHONHOME -u VIRTUAL_ENV -u CONDA_PREFIX LD_LIBRARY_PATH=/opt/blender/lib /opt/blender/blender --background --factory-startup --disable-autoexec --python-exit-code 1 --python /root/gpufree-data/semantic/scripts/260920SensorVisualizer/tools/build_terrain_blender.py -- --config /root/gpufree-data/semantic/scripts/260920SensorVisualizer/config/terrain.json --output /root/gpufree-data/IsaacSim_Asset/environment_module_set/UndulatingGround_next
```

这是单个进程的环境设置，不修改系统库。可在 Blender GUI 打开 `terrain.blend` 手工编辑，再另存和导出；已发布的 USD 不会因只保存 `.blend` 自动更新。

## 预览、录制和保存

在 `Fisheye Cameras` 选择方向并 `Open Camera View`。`Save All Camera Snapshot` 保存四路同时间戳图片。RViz 启动方式保持不变：

```bash
python3 /root/gpufree-data/semantic/scripts/260920SensorVisualizer/launch_rviz.py
```

在 Play 状态点击 `Start Recording`；结束时先 `Stop Recording`，等完成提示后再 Pause/Stop。

正式输出仍位于 `/root/gpufree-data/semantic/output/sensor_visualizer/<会话>/`。图片独立保存为 PNG；`cameras/<方向>/frames.jsonl` 新增 `base_control`，包含初始倾斜、当前偏移、模式、目标、角速度、上下限和手动高度。已有 `root_position`、`root_orientation_xyzw` 是实际运动状态。

`session.json` 的 `scene` 中新增录制开始时的整机控制状态和地形配置、资产哈希。ROS `/excavator/root_pose` 及 TF 保留实际完整旋转；没有把倾斜角作为虚构关节写入 `/joint_states`。

验收过程及样例保存在 `reports/tilt_terrain/`。测试采集使用私有 ROS domain 141，不是正常运行的默认 domain 0。

最后一轮验收保存 12 个四相机采集组，每组均有 13 路非空点云和对应 TF。第一组额外的 `/excavator/root_pose` 消息未录到，后续 11 组均准确匹配；首组的完整实际位姿仍存在于 TF 和图像元数据。按时间戳关联数据，不能要求录制开始边界上每个独立 ROS 话题都有消息；未补写或伪造缺失消息。
