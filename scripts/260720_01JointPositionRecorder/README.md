# 四关节挖掘机位置控制与角度记录器

这是一个独立的 Isaac Sim GUI 脚本项目。它不导入、不复用旧的
`ExcavatorActionRecorder` 项目，也不依赖关节 Angular Drive。

控制器以每个关节的目标角度和指定角速度为输入，每帧计算不超过
`speed × dt` 的下一个角度，再通过 Articulation 直接位置接口一次性写入四个
DOF。CSV 中保存的是写入后从 Articulation 回读的实时角度，单位均为度。

## 适用的 USD

默认配置以 `Sim_Fangshan_07.usda` 的结构为样本，但并不绑定该文件。兼容的
USD 必须满足：

- 一个固定基座 Articulation Root；
- 按 Cab、Boom、Small arm、Bucket 排列的四个 RevoluteJoint；
- 四个关节保持 `physics:jointEnabled = true`；
- 四个关节都没有 `PhysicsDriveAPI:angular`；
- 五个 link 都是启用的非 kinematic 刚体，并具有正质量和正对角惯量；
- 每个 RevoluteJoint 都有有限的上下限和唯一的父、子刚体关系。

如果同类挖掘机使用不同的关节名称或路径，只需复制并修改
`profiles/excavator_four_joint_default.json` 中的候选名称、候选路径和默认值。

## 在 Isaac Sim GUI 中启动

1. 将整个项目复制到 Isaac Sim 所在电脑，例如：
   `/root/gpufree-data/repositories/260720_01JointPositionRecorder`。
2. 在 Isaac Sim 中打开目标 USD。
3. 打开 `Window > Script Editor`，执行以下代码（按实际路径修改第一行）：

```python
import runpy

entrypoint = "/root/gpufree-data/repositories/260720_01JointPositionRecorder/entrypoints/show_panel.py"
runpy.run_path(entrypoint, run_name="__main__")
```

脚本会打开 `Articulation Joint Position Recorder` 面板，并自动尝试绑定当前
Stage。若物理 Timeline 尚未运行，绑定操作会启动 Timeline 并等待
Articulation tensor 初始化。

## 面板操作

- `Bind current stage`：重新检查当前 Stage 并绑定关节；
- `Target (deg)`：目标角度，必须位于显示的安全限位内；
- `Speed (deg/s)`：该关节的正角速度；
- `Move all`：四关节同时开始、各自按指定速度独立到达；
- `Stop`：停在回读到的当前角度，并将目标同步为当前角度；
- `Targets = current`：只重置输入框，不触发运动；
- `Move home`：使用当前速度输入移动到配置的 Home 角度；
- `Start recording` / `Stop recording`：开始或完成实际角度 CSV 记录。

只修改目标值或速度不会让挖掘机运动，必须显式点击 `Move all` 或
`Move home`。

## 记录文件

默认输出目录是项目内的 `trajectories`，CSV 格式为：

```csv
time,cab,boom,small_arm,bucket
0.000000000,0.000000000,0.000000000,0.000000000,0.000000000
```

正常停止后同时生成同名 `.metadata.json`。为防止意外覆盖，若目标 CSV、
元数据或同名 partial 文件已经存在，记录器会拒绝开始。异常中止时保留
`.partial.csv`，方便排查或恢复数据。

## 测试

纯 Python 单元测试不需要 Isaac Sim：

```powershell
python -m pytest
```

Isaac Sim 集成冒烟测试见 `tests/isaac_articulation_smoke_test.py`。该测试会短暂
写入四个关节位置并在结束前恢复初始角度，因此只应在没有其他控制器写入同一
Articulation 时运行。

`tests/isaac_gui_smoke_test.py` 还会在 headless Kit 中创建真实面板、等待自动
绑定为 `IDLE`，随后关闭面板，用于提前发现 Isaac UI API 或更新事件兼容问题。

## 目录

```text
entrypoints/    Isaac Sim Script Editor 启动入口
profiles/       可复用的机型关节映射和默认参数
src/            完全独立的控制、校验、GUI 和记录实现
tests/          纯 Python 测试与 Isaac Sim 冒烟测试
trajectories/   默认运行输出（首次记录时自动创建）
docs/           USD 运动链与设计说明
```
