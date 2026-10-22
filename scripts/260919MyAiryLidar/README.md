# MyAiry 雷达资产

MyAiry 是合成的 RTX LiDAR：采用当前 MyNZ3 的瞬时方向表发射方式，采用当前 MyOS0 的角度采样及视场。它不是某款实机的标定模型。

## 使用入口

远端资产：

`/root/gpufree-data/IsaacSim_Asset/sensor_set/lidar_set/MyAiry/MyAiry.usda`

远端源代码：

`/root/gpufree-data/semantic/scripts/260919MyAiryLidar/`

在 Isaac Sim 中将入口 USD 作为 Reference 添加到选定挖掘机下的安装位置，操作 `MyAiry` 根节点设置位置、旋转。实际传感器为其子节点 `sensor`，二者坐标系重合。添加传感器后再启动 LidarVisualizer，让其重新发现传感器并生成相应话题；现有自动发现默认只覆盖选定挖掘机的子树。资产没有包含 ROS 发布脚本。本次未修改任何 combine scene。

默认覆盖雷达局部 **+Z 上半球**。要朝下扫描，安装节点绕局部 X 或 Y 旋转 180°。这是一整个半球，没有 NZ3 那样的窄前向视锥。第一版没有可见的外壳 Mesh，`geometry` 是未激活的预留节点；没有看到外壳不表示传感器没有加载。

## 配置

| 项目 | 当前值 |
| --- | --- |
| 发射方式 | `SOLID_STATE`、`instantLidar=true`；方向表同时采样 |
| 水平视场 | 360°，892 个角位置，间隔约 0.403587° |
| 垂直方向 | 保留 MyOS0 的 96 个仰角，90° 到 0° |
| 每次方向表采样数 | 96 × 892 = 85,632；不保证每个采样都有有效回波 |
| 极点重复 | 保留 90° 行的 892 个采样，几何上共 84,741 个不同方向 |
| 配置频率 | 10 Hz，基于仿真时间；实际 ROS 输出仍由现有发布链路节流 |
| 量程 | 0.1–60 m |
| 最大回波数 | 2；受材质和回波筛选影响 |
| 发射与安装节点偏移 | 0；每条射线的水平、垂直偏移和距离修正也为 0 |
| `rangeOffsetM` | 0，不跳过近处几何遮挡 |
| 输出 | 传感器局部 XYZ，GMO BASIC 辅助通道 |

方向表按行保存：`row = emitterId // 892`，`column = emitterId % 892`。第 0 行为 90° 极点；水平角相位从 0 开始，沿源配置 CW 方向展开。RTX 方位角对应局部方向 `(cos(el)*cos(-az), cos(el)*sin(-az), sin(el))`。这保留空间方向分布，但不保留旋转雷达逐时刻扫描的时序。

### 合成模型功率归一化

将 96 个旋转发射器展开为 85,632 个瞬时发射器后，直接照搬 MyOS0 的有效 `peakPowerW=10` 在当前 RTX 版本的封闭房间测试中几乎不产生有效返回。对照实验比较了原旋转配置、原功率瞬时配置、降低反射阈值以及扩大发射功率等方案。

本版本保持 `minReflectance=0.1`，采用经测试的 `peakPowerW=10×892=8920` 作为**合成配置归一化参数**。它不代表真实硬件发射功率，也不说明已经实现物理辐射标定。`avgPowerW` 等仍沿用源配置；不要将这些值组合解释成真实雷达的功耗。强度、远距离探测概率和双回波精度尚未做实机标定。详细对照见 `reports/sensitivity_probe.json`。

## 代码与复现

- `build_asset.py`：仅使用 Python 标准库生成资产。
- `reference/`：制作时读取的原始配置和有效属性快照，供溯源；不是完整的原雷达可运行资产包。
- `assets/MyAiry/`：可整体复制的独立资产包，仅使用相对 USD 引用。
- `tools/validate_isaac.py`：独立场景中的实际 RTX/GMO 验证。
- `tools/probe_sensitivity.py`：功率和反射阈值对照实验。
- `reports/acceptance/validation.json`：保留测距噪声的双雷达验收结果。
- `reports/deployed_smoke/validation.json`：正式部署路径重新加载、关闭测距噪声后的几何验证结果。
- `reports/deployment.json`：部署文件校验和及原资产未变更检查。

在项目目录生成资产：

```bash
python3 build_asset.py
```

在远端单独启动测试进程，默认 Isaac 安装目录为 `/root/isaacsim`，可用 `AIRY_ISAAC_ROOT` 环境变量覆盖：

```bash
bash tools/run_validation.sh --asset "$PWD/assets/MyAiry/MyAiry.usda" --output "$PWD/reports/acceptance"
```

测试会生成匿名 USD 测试房间并退出，不修改用户场景。使用 `--smoke --zero-noise` 可执行单雷达的几何检查。`--zero-noise` 只覆盖测试场景中的属性，不写回资产。Kit 的快速退出可能返回 0，因此启动脚本还会检查最终 JSON 中的 `passed` 字段。

## 已验证与边界

在远端 Isaac Sim `6.0.1-rc.7+release.42383.32955d8d.gl`、NVIDIA L40 上完成双实例、平移旋转、暂停恢复和 Stop/Play 验证。采用现有兼容设置：Motion BVH、Multi-tick、per-sensor TLAS 均关闭；没有验证 Motion BVH 与 3DGS 的兼容性。

在四面封闭测试房间及顶底平面中，普通帧的有效方向覆盖超过 99.9%，若干帧的方向并集覆盖完整的 85,632 个采样编号。近处遮挡测试包含 15,818 条在最小量程内被几何挡住的射线，没有检测到这些方向穿过遮挡返回远处点的情况。测试中的距离误差包含继承的测距噪声，不能作为实机精度承诺。

位姿可通过根节点变换调整。传感器采样配置应在创建 Render Product 之前设定；测试中曾发现已有 Render Product 时修改测距配置并直接 Stop/Play 会触发当前 SDK 的原生进程异常，因此修改扫描配置后应重新创建采集资源或重启 Isaac。该故障日志保留在 `reports/startup_failure.log`，文件名沿用早期排查命名，实际不是加载资产时的错误。

资产制作阶段验证了独立 RTX 输出。随后完成了真实 combine 场景中的 ROS 2 发布、MCAP 录制、逐帧 TF 与频率核对，见 [STAGE12_CAPTURE.md](STAGE12_CAPTURE.md)。本轮没有启动 RViz GUI，不作为长期运行或多雷达性能基准。报告目录中带 candidate/control/probe 的旧日志是研发对照记录；资产验收以 acceptance、deployed_smoke 和 deployment 为准，组合场景结果以 reports/stage12 为准。
