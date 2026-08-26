# 260731PostProcessChain_v02

挖掘机五颗斗齿的离线后处理项目。当前 pipeline v3 严格配对三类输入：

- `full_scene` RGB；
- `full_scene` 稳定 semantic ID；
- `front_teeth_only` 稳定 semantic ID。

`excavator_only` 图像不再参与像素比例、参考旋转框或碰撞框计算。

## 当前处理逻辑

每个目标 semantic label 分别执行 4 邻域连通区域分析。默认删除小于 5 像素的连通区域，保留所有等于或大于 5 像素的区域。清理后的 mask 统一用于：

- 完整场景与参考场景像素数；
- 可见比例；
- 参考旋转框与填充比例；
- 最终 YOLO 轴对齐框；
- 高宽比；
- 单齿和碰撞模型过滤。

高宽比方向由 `height_width_axis_mode` 控制。默认 `x_over_y` 表示：

```text
x 方向框长度 / y 方向框长度
```

该比值直接使用清理后的 full-scene 目标像素生成的最终 YOLO 框计算。

## 整帧规则

配置中有两个互相独立的数量阈值：

```text
single_tooth.drop_all_single_boxes_if_bad_teeth_at_least
collision_model.drop_collision_box_if_bad_teeth_at_least
```

默认都为 3，判断使用“大于或等于”。单齿阈值触发时删除该帧全部单齿框；碰撞阈值触发时只删除该帧碰撞框。

## 配置与运行

配置 schema 版本为 2。可从下列文件开始修改：

```text
configs/example.json
```

运行：

```powershell
python run_pipeline.py --config configs/your_run.json
```

旧特征缓存不兼容当前连通区域与 front-only 参考逻辑。cache schema 已升级，指纹不匹配时会重新分析。

## 输出

```text
dataset/
├── rgb/
├── tooth_boxes/
└── tooth_collision_model/

reports/
├── tooth_features.csv
├── tooth_decisions.csv
├── collision_decisions.csv
├── frame_summary.csv
├── anomalies.csv
└── summary.json
```

报告同时记录清理前/后的像素数、被删除的连通区域和像素数、两套不合格斗齿计数以及整帧删除结果。

## 测试

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```
