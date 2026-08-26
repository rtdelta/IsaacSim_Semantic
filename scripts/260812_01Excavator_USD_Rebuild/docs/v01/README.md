# 挖掘机 USD 重建配置方案 v01

本目录定义“由 3DGS PLY、Mesh USD 和关节标定数据构建浮动式挖掘机 USD”的第一版配置协议。

本目录最初定义配置结构、参数含义和校验规则；当前已经开始实现阶段 0/1 的远端技术探测、输入扫描和候选配置生成工具。路径、Prim、Link、Mesh、3DGS 部件、Joint、物理占位属性、语义和输出方式仍全部由文件描述，Python 代码不硬编码正式资产的部件数量和节点名称。

## 文件清单

| 文件 | 用途 |
|---|---|
| `build_config.template.json` | 主构建配置模板；负责输入、坐标系、部件、拓扑、物理、语义、输出和校验策略 |
| `joint_calibration.template.json` | 新模型关节几何结果模板；负责保存源 Mesh 数值坐标中的中心、轴、来源和验证信息 |
| `配置参数说明.md` | 对两份 JSON 中全部字段逐项说明 |
| `配置关系与校验规则.md` | 说明对象引用、Joint body 解析、默认值继承、构建阶段及错误处理规则 |
| `核心设计与实现方案.md` | 定义完整目标、边界、技术思路、模块层次、实施阶段、测试及验收标准 |
| `阶段00与阶段01执行结果.md` | 记录远端实测结果、真实 PLY/Mesh 清单、候选映射、风险和待确认项 |
| `阶段02实施与验证结果.md` | 记录一次性 Joint 迁移、正式 USD 构建、静态验收与 Isaac Sim 运行时阻塞 |

项目根目录中的实际产物：

| 路径 | 用途 |
|---|---|
| `config/fangshan_candidate.build.json` | 由真实输入清单生成的候选构建配置 |
| `config/fangshan_candidate.joint_calibration.json` | 已通过一次性迁移和 Mesh 几何验证的关节标定配置 |
| `analysis/stage00/` | Gaussian Importer/API 技术探针结果 |
| `analysis/stage01/` | PLY、Mesh、旧 USD 一次性迁移证据、参考清单和候选映射 |
| `analysis/stage02/` | Joint 迁移、正式构建、静态/组合验收和运行环境阻塞报告 |
| `tools/` | 可重复执行的输入扫描、转换探针和候选配置生成工具 |

## 关键约定

1. 所有数组长度都可配置，不在代码中固定 Link、Joint、Mesh、3DGS 或语义标签数量。
2. `id` 是配置内部稳定标识符；USD Prim 路径由 `root_prim_path`、Link 路径和部件相对路径组合得到。
3. 每个 Mesh 和 3DGS 部件必须通过 `link_id` 归属一个 Link。
4. Fangshan 正式配置中的 Joint `body0`、`body1` 直接引用 Link；最终 `physics:body0`、`physics:body1` 指向带 `RigidBodyAPI` 的 Link Xform，绝不指向可视 Mesh Prim。`mesh_part` 间接引用仅作为通用协议的兼容能力，不是本资产的推荐写法。
5. 关节几何由新工程自己的 `joint_calibration.json` 提供。Fangshan 首次迁移时允许一次性读取旧 USD，把旧 Joint 旋转线换算到当前源 Mesh 数值坐标，并用 Mesh 几何验证；迁移结果落盘并通过验证后，正常构建、重复构建和部署不得再读取旧 USD。
6. 当前推荐构建浮动式 articulation：不创建世界固定关节，ArticulationRootAPI 放在根刚体 Link 上。
7. Mesh 默认隐藏并设为 `proxy`，避免和 3DGS 重叠渲染；是否创建碰撞体独立配置。
8. 当前采集用途允许占位质量和惯量，但必须在资产元数据和报告中标明其不是实际动力学参数。
9. 相对路径默认相对于主配置文件所在目录解析；输出 USD 内部资产引用默认使用相对路径。
10. 模板中的示例文件名、Prim 名称和数值不代表最终资产数据，必须结合实际输入填写并通过严格校验。

## 推荐使用流程

1. 复制 `build_config.template.json` 为项目配置，例如 `configs/fangshan_build_config.json`。
2. 复制 `joint_calibration.template.json` 为项目标定文件，例如 `configs/fangshan_joint_calibration.json`。
3. 填写真实 PLY、Mesh USD、输出目录、Link 和部件映射。
4. Fangshan 首次接入时运行一次性 Joint 迁移工具，生成源 Mesh 数值坐标中的中心和轴，再用 Mesh 几何验证；其他没有可信旧 Joint 的资产可改用独立 Mesh 标定工具。
5. 先以 `execution.dry_run=true` 解析配置并生成构建计划。
6. 检查解析后的绝对路径、完整 Prim 路径、Joint body 解析结果和公共坐标变换。
7. 将 `dry_run` 改为 `false` 后执行正式构建。
8. 检查生成的 `resolved_build_config.json`、`build_validation_report.json` 和调试 Stage。

## 模板中的 `null`

`null` 的含义由字段类型决定：

- 覆盖字段为 `null`：继承同类对象的默认值；
- 校验阈值为 `null`：不执行该项数值阈值检查；
- 计数期望为 `null`：数量完全由数组长度决定；
- 标定中心、轴或必要输入为 `null`：表示数据尚未提供，正式构建必须报错；
- 可选 PhysX 属性为 `null`：不在输出 USD 中显式写入该属性。

详细规则见 `配置关系与校验规则.md`。

## 一次性 Joint 迁移边界

旧 `Excavator_Fangshan_01.usda` 不是生产输入，也不是长期标定源。它只在本次旧模型转为新模型时执行一次以下操作：

1. 读取旧 Link Xform 和四个 RevoluteJoint 的 body、localPos、localRot、axis、限位与零位约定；
2. 恢复旧模型坐标中的世界关节中心和轴；
3. 去除旧视觉子 Prim 的公共变换，换算到当前原始 PLY/Mesh 数值坐标；
4. 结合输入摘要和 Mesh 几何检查迁移结果；
5. 将确认后的中心、轴和来源固化到新 `joint_calibration.json`。

第 5 步完成后，旧 USD 即退出依赖图。后续构建只允许读取原始 PLY、组合 Mesh、新主配置和新标定文件；若标定文件丢失，应从受控产物或版本库恢复，不能在正常 pipeline 中悄悄重新读取旧模型。

## 变更记录

### 2026-08-12：Joint Xform 直连与一次性旧数据迁移

- 将 Fangshan Joint body 的推荐形式改为直接引用刚体 Link Xform；
- 明确 Mesh 只承担视觉、拆分和关节几何验证，不承担 Joint body；
- 将旧 Joint 数值定位为仅本次旧模型转新模型的一次性迁移输入；
- 明确迁移落盘后，正常构建、重复构建和部署均不依赖旧 USD。
