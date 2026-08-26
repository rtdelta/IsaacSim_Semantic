# 示例项目

`scripts/create_remote_smoke_jobs.py` 使用 v04 自身模型、Repository 和 JobCompiler 生成两个完整 `.swproject`：

- Realtime：Full Scene 输出 RGB + 两种语义；隔离场景只输出两种语义。
- Path Tracing：相同模态矩阵，使用最小 SPP 做冒烟。

在云电脑执行：

```bash
cd /root/gpufree-data/semantic/scripts/260820semantic_worldModule_v04
export PYTHONPATH="$PWD/src"
/root/isaacsim/python.sh scripts/create_remote_smoke_jobs.py \
  --workspace "$PWD/examples/generated" \
  --output-root /root/gpufree-data/semantic/output/v04_smoke
```

默认 Stage 和 Camera 是已验证公共测试资产，可通过 `--stage` 和 `--camera` 覆盖。脚本不读取旧项目配置或代码。

生成后可运行：

```bash
/root/isaacsim/python.sh -m semantic_world_v04.cli.supervisor_cli run \
  examples/generated/v04_smoke_realtime.swproject/jobs/job-v04-realtime-smoke/job_spec.json
```

`examples/generated/` 是可再生成内容；真实业务项目建议放在独立数据目录并纳入自己的版本/备份策略。

仓库中已提交的 `examples/generated` 仍是 Schema v1，用于持续验证向后兼容；重新运行生成脚本会产生 Schema v2 revision。

v04.3 的针孔 + 原生鱼眼 + RTX LiDAR 示例由以下脚本生成：

```bash
./scripts/launch_isaac_python.sh scripts/create_v043_sensor_smoke_stage.py \
  --output /data/v043_sensor_smoke.usda
./scripts/launch_isaac_python.sh scripts/create_v043_sensor_smoke_job.py \
  --workspace /data/projects --stage /data/v043_sensor_smoke.usda \
  --output-root /data/output --job-id job-v043-mixed \
  --renderer RayTracedLighting --frame-count 3 --segment-frames 2
```
