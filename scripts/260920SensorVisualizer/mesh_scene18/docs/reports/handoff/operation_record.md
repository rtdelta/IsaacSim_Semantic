# 本次交接生成记录

日期：2026-10-12（报告按北京时间）。目标：冻结从当前五部件 mesh 输入到 scene18 所用挖掘机资产的完整、可重建链路。

- 通过已有 `cloud-instance-ops` 实例别名、凭据引用、主机指纹及实例身份检查，读取实际源资产、几何属性、关节/根矩阵、传感器矩阵、USD 层依赖与 SDK 版本。
- 从项目云端复制 `waji_mesh_corrected.usdc` 到本地交接包。62465254 字节，传输后 SHA256 与原始文件一致。使用现有 Paramiko/SFTP，未下载第三方内容。
- 在本地生成重建脚本、蓝图、机器可读契约和报告，将重建材料放入远端项目新建的 `mesh_scene18/handoff/`。
- 仅在远端 `mesh_scene18/handoff_rebuild_validation/Excavator_Mesh_Contract/` 生成验证输出。没有覆盖正式资产、scene17、scene18 或旧项目脚本，没有启动图形引擎、改变系统/桌面/驱动/依赖。
- 重建环境是现有 Python 3.12.13、OpenUSD 0.25.11、NumPy 2.3.1。六个输出 USD 与正式资产字节一致，55 项源数值属性一致，组合后 USD 全文一致。结果在同目录 `rebuild_verification.json`。
- 中间数据提取曾遇到 USDZ 内部路径不能当作普通磁盘文件读取，后改为哈希容器文件；输出脱敏器把 schema 的 allowedTokens 误判成敏感字段，后从事实提取中省去该冗余 schema 元数据。首次部署手段的 UTF-8 文本换行转换触发哈希保护，未写入文件；改为保持原始字节后部署成功。这些问题没有改动原资产。

本地审计结果保存在交接包外的 `mesh_scene18/extract_handoff_audit_*.json`、`build_handoff_audit*.json` 及 cloud-instance-ops 工具审计目录。共享包不带 SSH 地址、凭据、私钥或凭据管理器配置。

验证范围：输入和目标文件一致性、静态坐标/几何契约与已完成的旧部署运行验证。不是整台主机审计，也不是更早合并 mesh 制作过程、真实物理参数或任意渲染环境的认证。
