# combine_scene_10：08 环境 + 05 挖掘机 + 原传感器层级

已在远端实现。主文件：

`/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_10.usda`

说明、采集样例和验收记录位于同目录的 `combine_scene_10_data/`。本地目录是交付镜像和构建记录；本地 USD 的相对依赖指向远端原有资产布局，请在远端 Isaac 中打开主文件。

## 打开方式

1. 已有 Isaac Sim 窗口：File → Open，选择上述 `combine_scene_10.usda`。可切换到 `/World/Stage10Overview` 查看总览，或 `/Excavator_Fangshan_05/boom_prim/Camera` 查看大臂相机。
2. 需要启动新的 Isaac 进程时：使用 `combine_scene_10_data/IsaacSim_Stage10.desktop`，然后按第 1 步打开场景。它直接执行 Kit 二进制，并设置雷达原生组件需要的库搜索路径，没有调用 `.sh` 或场景装配脚本。文件管理器若把 desktop 文件当成文本，可使用“允许启动/信任此启动器”。
3. 点击 Play 后，保存在 USD 中的 `/World/Stage10SensorPipeline` 自动启用 14 个既有 RenderProduct。无需运行 Python 才能加载、显示或装配挖掘机。

若已有 Isaac 进程能显示场景但雷达返回空数据，可使用第 2 种入口重新启动测试。本次直接启动 Kit 的早期测试出现 `No impl loaded in validateParams`，默认雷达也无法测到测试墙；为测试进程补齐传感器原生组件库目录后，默认雷达和全部迁移雷达均恢复有效输出。未改系统库、旧启动器或共享传感器配置。

这些资产仍有 NVIDIA 在线 USD 依赖，保留了 08 的引用方式；本次在 Isaac 中全部解析成功。独立系统 Python/OpenUSD 没有同样的网络解析环境，会报告这些 URL 的解析警告。

## 资产、尺寸和初始姿态

- `/Excavator_Fangshan_05` 的 Payload 指向原有 `Excavator_Fangshan_05.usda`。05 本体文件没有修改，仍可单独作为 Payload 使用。
- 五个部件的 GS 和 Mesh 配准缩放均为 `(2.4, 2.4, 2.4)`；整机根、刚体和传感器本体保持单位缩放。
- 关节沿用 05 的 `swing / boom / arm / bucket`，零点、转轴和正方向不变。05 的关节平移来自统一放大后的扫描铰点，不能把“全部 2.4 倍”表述成“所有长度精确等于原始 URDF”。
- 新场景初始角度为 `[0, 38, -106, -5.8741577631]` 度。它是场景中的折臂摆放，参考 08 外观并抬高大臂，为原栏杆留出间隙；不是重新定义关节零位。
- 同时保存了刚体初始变换、Drive 目标和 PhysX JointState 初始角度，避免点击 Play 后由零角度向折臂姿态跳变。
- 根位置为 `(-1.18304673796, 1.56634215620, 0.52528070927)` m。XY 对齐原回转轴；高度以现有世界 Z=0 网格地面和履带 GS 中心点最低处加 2 cm 为预览基准，未做地形贴合或真实接触标定。
- `/World/Stage10BaseAnchor` 是场景专用底盘固定约束，便于关节预览；没有写入可复用的 05。
- 保留 08 环境的引用、位姿、栏杆与测试 Cube。质量、惯量、驱动真实性和碰撞安全性没有实机标定。

默认 `visualization=3dgs`。在 stage 10 自己的 3dgs 变体内，Mesh、URDFReference 和 URDFOverlay 被停用，防止比较几何参与正常测距。其他显示变体仍来自 05；05 自身的 URDF 叠加功能保留。

## 传感器迁移

13 个雷达仍直接挂在 `cab_prim`，1 个相机仍直接挂在 `boom_prim`。没有新增 Sensors 中间节点。根前缀由 `/Excavator_Fangshan_03` 变为 `/Excavator_Fangshan_05`，根以下的设备名称、父子关系及设备内部子节点保持原样。

- 12 个普通雷达和相机：位置、朝向按所属部件的 05 几何配准迁移；设备本体不随几何放大。
- `MyOS0_up`：直接复制原子树，保留原 xform 字段、精度和操作顺序；没有进行位置缩放或重新定向。
- `MyOS0_up` 相对 `cab_prim` 的位置仍为 `(-1.1807208058471677, -1.300093821681328, 8.03211418882543)` m，四元数 wxyz 为 `(6.123234e-17, 1, 0, 0)`，Scale=1。内部 sensor 的 Z=0.03622 m 偏移也保留。
- 全部设备内参、扫描 profile、原外壳隐藏状态和内部光学偏移保持原值。大臂相机原有画面滚转也保留，没有额外扶正。

精确安装矩阵、新旧路径、frame_id、RenderProduct 和关节路径见 `manifest.json`。13 个普通安装矩阵的误差仅来自原 quatf 字段的浮点精度；MyOS0_up 原始挂载子树文本比较一致。

## 输出与控制

固定设备输出为 `/Render/Products/<设备名>`，共 14 个；雷达使用 GenericModelOutput，相机分辨率 1280×720。旧的多代 RenderProduct 和失效 SDGPipeline 连接没有搬入新文件。编辑器运行时可能在会话层额外创建视口渲染产物。

需要落盘样例时，在 Isaac Script Editor 打开并运行 `combine_scene_10_data/capture_sensors.py`。它在 `captures/<时间>/` 写入 13 份 NPZ、相机 PNG 和坐标系说明，不保存 USD，不发布 ROS 消息。仅打开场景或点击 Play 不会自动连续写磁盘。

控制根为 `/Excavator_Fangshan_05/track_prim`，关节路径为 `/Excavator_Fangshan_05/Joints/<关节名>`。USD 的角度 Drive 与 JointState 属性使用度；控制接口如使用弧度，应明确转换。旧 CSV 播放器未迁移，不能仅替换根路径就认为旧轨迹的零点、方向和根位姿已经兼容。

## 验收结果

- 场景在远端 Isaac Sim 6.0.1-rc7 / NVIDIA L40 中加载成功，无合成错误。
- 14 个设备的相对层级、原始非挂载属性和有效内参比对通过。
- 全部 13 路雷达同时输出有效数据；按输出时间戳测得的扫描频率均为仿真时间 10 Hz。
- 最新短测每路记录 39 个不同时间戳的扫描；约 4 秒仿真采集耗时约 19 秒墙钟时间。这不是实时运行性能保证，也没有做长时间稳定性压测。
- 大臂相机输出 1280×720 图像，总览输出 1440×900。
- 四个关节正负 10° 驱动检查通过，最大角度误差约 `1.1e-6 rad`；初始角度误差约 `7.6e-6°`。所有传感器在平台和臂运动中的刚性随动检查通过。
- NZ3 对隔离的 5 m 平面靶返回 1622 个点，最大 X 距离数值误差约 `1.43e-6 m`。这验证仿真单位和变换，不表示现实雷达具备此精度。
- 停用 Mesh 与 URDF、只保留 GS 后，MyOS0_up 在其下方 0.75 m 半径内仍返回 4647 个高于地面 0.5 m 的点。该局部对照证明本运行环境能测到 GS 机体，未把 RGB 可见性当作测距证明；没有据此宣称全表面或实机测距已标定。
- 原有输入文件的 SHA-256 前后检查结果见 `final_validation.json`；检查覆盖 08、09、03/04/05、共享传感器、环境及旧代码等 73 个文件。
- 新进程重新打开最终文件后，交付的采集工具对每路雷达收齐 5 个扫描并保存相机图像，且主 USD 文件哈希不变，见 `reopen_validation.json`。

记录：`structural_validation.json`、`physics_validation.json`、`runtime_validation.json`、`distance_validation.json`、`final_validation.json`。预览：`overview.png`、`boom_camera.png`。构建和 QA Python 文件用于复现与审计，不是场景打开的前置步骤。
