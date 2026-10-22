# 本次 300 组 MCAP 合并操作

源是 `20261013_142507_300` / `20261013_142524_685978_f13b03ee` 中的 `bag_unified`。三个分段保持原样；新包为同一采集目录下的 `bag_merged/bag_merged_0.mcap`，有独立 `metadata.yaml`。

合并使用实例现有 ROS 2 Jazzy 的 `ros2 bag convert`，所有话题均包含，大小和时长分段均设为 0。没有下载或安装依赖。

`merge_and_verify.py` 对全部源消息和输出消息逐条比较：完整 Schema、Channel、序号、log_time、publish_time 及原始序列化字节都相同；检查未压缩 Chunk 的非零 CRC、300 个组时间和 9006 条消息，再分别用官方 ROS Reader 读取目录和单文件。

本实例生成的 `metadata.yaml` 中总消息数为 9006，但 `files[0].message_count` 为 18012。依据完整实际计数将新包该字段改为 9006；原始生成元数据保留在采集目录的 `merge_control_20261013/metadata.generated.yaml`。源包元数据保持原样。

`pull_merged_mcap.py` 使用已登记的 Windows 凭据引用、SSH 主机指纹和实例身份检查，通过 SFTP 并行范围读取项目自行生成的数据；不在命令行或源码中放置秘密值。接收文件先使用临时范围文件，合并后与远端 SHA-256 观察值核对，再使用正式文件名。审计事件由锁串行记录。SFTP 不属于 ops CLI 的能力，由脚本调用同一身份核验和审计模块。

`verify_local_merge.py` 在接收完成后，再将本地三个源分段与合并包逐条比较，并检查 group_id 为连续 0～299、仿真时间间隔为 100,000,000 ns。

运行状态及最终交付见本地 `output/20261013_scene18_single06_300_mcap/bag_merged` 的验证报告和传输收据。源/输出哈希证明字节一致及传输一致，不作为源实例安全认证；此次合并不重新采集，也不对点云几何错帧作出新结论。

首次运行 `run_merge_remote.py` 会创建输出，并拒绝覆盖现有目录。中断后先检查远端状态；已有单文件合并结果可用审阅后的 `resume_verification_remote.py` 继续验证，不重复转换。
