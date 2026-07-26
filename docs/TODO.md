# TODO

## 关节逻辑名由 profile 统一驱动

当前 `260714_01semantic_worldModule` 在运动控制、CSV 解析、运行前校验和输出校验中，
固定使用以下逻辑关节顺序：

```text
cab, boom, small_arm, bucket
```

`Combine_Scene_02.usda` 中对应的物理关节名称为 `boom_arm_joint`，但现阶段业务代码内部
仍继续使用逻辑名 `small_arm`，不修改 Python 代码和现有轨迹格式。

后续建议：

1. 取消业务代码对四个逻辑关节名及顺序的硬编码。
2. 以 joint profile 中的 `joints` 顺序作为运动控制、CSV 表头、轨迹 metadata 和输出校验的唯一来源。
3. 将逻辑名 `small_arm` 统一迁移为 `arm`。
4. 为旧轨迹提供 `small_arm -> arm` 的输入兼容或一次性迁移工具。
5. 同步更新两个项目的 profile、CSV/metadata 校验和相关自动化测试。

在上述改造完成前，新场景配置必须继续使用：

```text
cab, boom, small_arm, bucket
```
