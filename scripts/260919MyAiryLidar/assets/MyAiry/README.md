# MyAiry

入口：`MyAiry.usda`；配置：`config/MyAiry_scan.usda`。请整体保留本目录，入口使用相对引用。

- NZ3 式瞬时发射，MyOS0 的 360° 水平、0–90° 仰角方向表。
- 默认局部 +Z 半球；绕安装节点 X 或 Y 转 180° 可朝下。
- 96×892=85,632 个采样，10 Hz 配置，量程 0.1–60 m，最大 2 个回波。
- 根节点与 `sensor` 发射节点重合，`rangeOffsetM=0`，保留近处几何的遮挡。
- 第一版无可见外壳 Mesh；通过根节点变换设置安装位姿。
- `peakPowerW=8920` 是瞬时展开后的合成归一化参数，不是真实设备功率或实机标定值。

在 Isaac Sim 中将本入口作为 Reference 放到选定挖掘机下的安装节点，再启动 LidarVisualizer 发现新传感器。资产本身不发布 ROS，也不改变现有场景。

源代码、参数说明、验证报告：
`/root/gpufree-data/semantic/scripts/260919MyAiryLidar/README.md`
