# 并行可行性与运行警告分析（2026-09-23）

本次只读检查新实例；未修改项目功能、远端配置、场景或进程。已保存远端检查脚本、审计返回及脱敏证据。本报告结合上轮实际录制遥测、本轮完整 Kit 日志及本地/远端已安装源码；未进行并行压力测试。

## 性能结论

优先将四路相机 PNG 编码与独立文件写入移出 Isaac 回调，采用有界队列和小型工作池。Isaac 已有多线程：本次 Kit PID 19303 有 400 个线程；上轮生产采样有 419 个线程。实例 CPU 配额为 14 核，不能用宿主机逻辑核数决定工作池大小。

上一轮录制 337.075 秒，仿真推进 8.283333 秒，倍率 0.02457；录制前播放倍率约 0.07318。录制时 CPU 平均 2.51 核、GPU 整卡平均 14.60%；录制前分别约 5.32 核、39.46%。四图保存均值 2.614 秒/组，83 组累计 216.975 秒，占录制墙钟时间约 64.4%。计时包含编码、数组转换与写文件，尚未拆分，不能全部归因于磁盘或压缩。

调用链：`FrameWriter.write -> CameraCapture.receive -> CameraRig.receive -> _consume -> _save_group -> PIL.Image.save`。四相机在 `_save_group` 中逐张处理，后续渲染提交被同步回调延迟，符合录制时 GPU 平均负载下降的现象。未发现 CPU 配额持续限流、OOM 或磁盘饱和证据。

当前配置固定 60 Hz 仿真步长、主循环最多约 6 FPS、倍率不高于 0.1。优化目标是减轻长卡顿并向该上限靠近，不能承诺 CPU/GPU 满载或界面达到 60 FPS。即便解除 PNG 阻塞，渲染、读回及主动限速仍有成本。

## 建议并行边界

- Isaac 线程：运动更新、USD/PhysX/渲染产品操作、帧匹配、采集时刻位姿快照、UI 更新。
- 后台工作池：已经复制并独占的像素数组的 PNG 编码、不同临时文件写入；不查询实时 USD 位姿，不修改场景。
- 单一提交者：保持捕获序号顺序；同组四张全部成功后写元数据，最后写 capture_index 作为整组提交标记。
- 停止流程：截止接收新采集组，等待已接收任务完成，再关闭索引/元数据文件和开始合包；失败要可见，不能把后台异常当作成功。
- 初始建议 2 个工作线程，与 4 个对照。队列限制 4–8 组；每组 1920×1080×4 通道×4 路原始数组约 31.6 MiB，另计编码和副本。满队列明确背压，不能无界积压或静默丢组。背压设计需照顾 GUI 响应，不能在主线程无限阻塞等待。
- 时间戳与全部位姿采用采集时快照，不能在编码完成时重新读取，否则会造成图像/TF 错帧。

远端静态源码显示自带 Pillow 12.2.0，PNG 通过 `_idat -> ImageFile._encode_tile -> encoder.encode`。上游同版本 ZipEncode.c 的主要滤波压缩循环有 `ImagingSectionEnter/Leave`，其绑定通过 `PyEval_SaveThread/RestoreThread` 释放/恢复 GIL，因而多图线程并行有源码依据。实际收益仍须针对当前二进制小规模测试；普通 Python 循环不能因此认为都可跨核并行。如实测线程竞争明显，再考虑独立进程方案并衡量复制开销；不从运行中的 Kit 直接 fork 图形上下文。

不建议为并行直接启用 asyncRendering、Motion BVH 或改变多 tick 渲染开关。这些涉及运动与传感器时序及 3DGS 兼容性，应独立验证。现有 ROS recorder 和资源监测已有独立进程/后台工作，结束后的 MCAP 合并不是这次录制阶段的主要瓶颈。

## 完整日志与警告分布

检查时间约北京时间 10:57。最新日志：`/root/.nvidia-omniverse/logs/Kit/Isaac-Sim Full/6.0/kit_20260923_095639.log`，末条更新约 10:39:40，88 条 Warning，未见 `[Error]` 或 Traceback。按约秒级边界划分：脚本启动前 25 条，初始化/预览 46 条，实际录制区间 0 条，结束后 17 条。当前控制台可能继续显示旧警告，日志并未显示每个采集帧持续新增 warning。

这次范围包括启动阶段与结束清理，较先前按脚本运行时间窗口报告的 46 条更完整。没有 Error 不代表没有功能性故障：例如 anim.graph 注册失败本身以 Warning 级别输出。

| 警告 | 数量 | 判断与建议 |
|---|---:|---|
| MotionBVH for lidar model not enabled | 1 | 涉及运动相关回波的物理准确性。当前启动器有意关闭 Motion BVH，全部 Instant 降低扫描跨时刻影响，但不能由此证明移动的 3DGS、姿态与遮挡完全准确。先做静止和已知运动对照，再判断影响；不要为消除警告直接开启。 |
| texture directly to host buffer is counter-performant | 1 | 图像读回路径有性能改进空间，可能产生同步等待；该路径耗时还未独立测量，不能盖过已测得的 PNG 阻塞证据。 |
| hydratexture interface was already released | 50 | 生命周期提示，集中在北京时间 10:22（17）、10:23（16）、10:39（17），录制区间无新增。应对照初始化/销毁顺序、重复运行后的资源残留，不足以认定泄漏、崩溃或数据损坏，也不能简单屏蔽。 |
| Unexpected reference count for UsdStage while closing | 1 | 启动期关闭匿名 World0.usd 时仍有引用，可能残留；不等于采集场景确定泄漏。结合重复启停和内存趋势检查。 |
| interface acquired 100 times / getCachedInterface | 17 | native 插件接口获取的性能提示；11 条来自 LiDAR 材质。集中初始化期，不能解释为每帧失败；不为此替换系统/插件库。 |
| Writer version not specified | 4 | 已定位项目与当前 Replicator 初始化契约不匹配：基类 `Writer.__new__` 设置实例 version='0.0.0'，覆盖项目类属性 version='1.0'；项目 __init__ 未再次设置实例属性。后续在实例初始化设置版本即可。独立的相机参数与逐帧元数据已保存，本次没有发现因此缺失。 |
| USD Diagnostics muted | 3 | 隐藏了更具体的 USD 警告，属于诊断缺口。若后续验证资产/引用异常，应在受控复现中临时显示详细诊断；本次未修改该设置。 |
| Unhandled attribute type VtArray<string>, channels | 2 | usdrt population 对 channels 属性类型处理不完整；当前日志不含具体 prim 路径，无法仅凭这条判断受影响资产或传感器。应与 3DGS/材质属性验证一并定位。 |
| omni.anim.graph.core import/node registration failed | 1 | 动画图扩展部分节点注册确实失败。当前关节脚本使用 Articulation/PhysX 状态更新，未直接使用该动画图模块；本次运动消息存在，但将来使用动画图可能受影响。 |
| timeline / pxr.Semantics deprecated | 各 1 | 未来 API 兼容性风险，不能据此认定当前采集错误。调用来源可能含扩展内部，不应仅凭消息归咎项目一行代码。 |
| PerfSDK disabled / ECC / Cache Server / snippets 等 | 若干 | 性能分析工具不可用、设备配置或可选资源提示；本次无证据指向图像点云损坏，不需要为消除提示安装缓存服务、关闭 ECC 或更新驱动。 |

本轮 MCAP 已通过上一轮回读，四相机各 83 张、13 雷达各 83 帧，无空点云或非有限 XYZ。这证明产出可读取、帧数一致，尚不是运动中几何准确性的完整验收。另有 1 ns 时间戳取整差异已在上轮报告说明，与上述 warning 不应混为一谈。

## 后续顺序（尚未执行）

1. 小规模拆分编码/写盘/读回时间，比较 1、2、4 个图像工作线程，保持图像、时间戳、元数据语义。
2. 实现有界异步保存与顺序提交；验证无丢组、无错误位姿匹配、停止能排空队列、失败能显示。
3. 修正 Writer 实例版本、检查渲染资源生命周期；定位 channels 和被隐藏的 USD 诊断。
4. 独立验证 Motion BVH 关闭时的运动精度；按测量结果再决定读回路径优化。

## 文档依据与证据

- `20260923_review/warnings.json`：完整警告分类、当前 Kit 线程信息。
- `20260923_review/warning_context.json`：阶段计数、已安装 Replicator/Pillow 源码摘录。
- `docs/reports/20260923_latest_run_review.md`：实际录制数据和资源遥测。
- OpenUSD 同一 stage 多读/单写规则：https://openusd.org/23.02/api/_usd__page__multi_threading.html
- Python 线程与 GIL：https://docs.python.org/3/library/threading.html
- Pillow 12.2.0 PNG 编码：https://github.com/python-pillow/Pillow/blob/12.2.0/src/libImaging/ZipEncode.c
- Pillow GIL 绑定：https://github.com/python-pillow/Pillow/blob/12.2.0/src/_imaging.c
- NVIDIA Motion Raytracing：https://docs.omniverse.nvidia.com/materials-and-rendering/latest/sensors.html

文档通过浏览工具读取，未在云端下载或执行外部内容。浏览访问登记属于自报审计，不是网络抓包。最新 NVIDIA 文档的开关名不能直接套用于当前安装，本文未建议改变运行开关。
