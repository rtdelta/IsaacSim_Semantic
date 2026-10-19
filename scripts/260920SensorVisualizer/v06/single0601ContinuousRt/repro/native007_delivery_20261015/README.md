# 2026-10-15 交付源码快照

`implementation/` 从原 `reports/native007_delivery_20261015/implementation/` 迁移，完整保留 81 份文件及其原始内容。这是历史交付源码快照，保留了当时的路径假设，不能据此认为所有脚本可以直接从新目录启动。

现行入口和工具仍位于项目的 `tools/native_rotation_localization/`；快照中 80 份文件与整理时的现行副本一致，`finalize_record_local.py` 不同。原始实验锁定记录未改动。

逐文件原路径和哈希见仓库 `docs/repository_layout/20261019_migration.json`。原始实验数据继续保留在原运行目录，由 `.gitignore` 排除；本次迁移没有重新运行实验。
