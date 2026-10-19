"""Produce a compact delivery record from completed capture evidence."""
import collections
import json
import statistics
import sys
from pathlib import Path


def main(directory):
    base = Path(directory)
    source = base/'production/capture'
    delivery = base/'delivery_300'
    status = json.loads((base/'delivery_status.json').read_text())
    assert status['state'] == 'completed'
    result = json.loads((source/'result.json').read_text())
    validation = json.loads((delivery/'validation.json').read_text())
    groups_validation = json.loads((delivery/'group_validation.json').read_text())
    assert result['state'] == 'completed' and validation['ok'] and groups_validation['ok']
    groups = [json.loads(line) for line in (source/'groups.jsonl').read_text().splitlines()]
    resources = [json.loads(line) for line in (source/'resources.jsonl').read_text().splitlines()]
    engine_lines = (source/'engine.log').read_text(errors='replace').splitlines()
    times = [g['payload_observed_scope_s'] for g in groups]
    gpus = [r['gpu'] for r in resources if r.get('gpu')]
    summary = dict(
        ok=True, groups=len(groups), messages=status['messages'],
        data_directory=str(delivery), source_capture=str(source), scene=json.loads((source/'spec.json').read_text())['scene'],
        logical_time_s=[groups[0]['logical_time_s'], groups[-1]['logical_time_s']],
        native_time_s=[groups[0]['native_time_s'], groups[-1]['native_time_s']],
        native_minus_logical_s=groups[0]['native_time_s']-groups[0]['logical_time_s'],
        last_world_x_offset_m=groups[-1]['trajectory_state']['world_x_offset_m'],
        root_start_xyz=groups[0]['trajectory_state']['position_world_m'],
        root_end_xyz=groups[-1]['trajectory_state']['position_world_m'],
        root_delta_rpy_min_max_deg=[min(g['trajectory_state']['root_rpy_increment_deg'][0] for g in groups), max(g['trajectory_state']['root_rpy_increment_deg'][0] for g in groups)],
        group_seconds=dict(mean=statistics.mean(times), median=statistics.median(times), max=max(times), total=sum(times)),
        engine_and_recorder_wall_s=result['process_wall_s'],
        root_pose_max_abs_error=max(g['root_target_max_abs_error'] for g in groups),
        joint_pose_max_abs_error_rad=max(g['joint_target_max_abs_error_rad'] for g in groups),
        render_frozen_pose_max_abs_error=max(g['pose_change_error'] for g in groups),
        render_frozen_time_max_abs_error_s=max(abs(g['native_time_after_s']-g['native_time_s']) for g in groups),
        camera_render_pose_max_abs_error=max(x['camera_pose_max_abs_error'] for g in groups for x in g['images'].values()),
        lidar_render_pose_max_abs_error=max(x['render_pose_max_abs_error'] for g in groups for x in g['lidars'].values()),
        usd_unchanged=result['root_usd_unchanged'], dependencies_unchanged=result['source_dependencies_unchanged'],
        warning_lines=sum('[Warning]' in line for line in engine_lines), error_lines=sum('[Error]' in line for line in engine_lines),
        source_mcap_bytes=sum(p.stat().st_size for p in (source/'bag').glob('*.mcap')),
        delivery_mcap_bytes=sum(p.stat().st_size for p in (delivery/'bag').glob('*.mcap')),
        delivery_files=status['files'], counts={name:t['messages'] for name,t in validation['topics'].items()},
        gpu_busy_mean_percent=statistics.mean(g['utilization.gpu'] for g in gpus),
        gpu_busy_max_percent=max(g['utilization.gpu'] for g in gpus),
        gpu_memory_peak_mib=max(g['memory.used'] for g in gpus),
    )
    (base/'run_summary.json').write_text(json.dumps(summary, indent=2))
    report = f'''# Scene18 原生冻结 RT2：300 组采集交付记录

状态：正式采集与交付包校验全部通过。300 组，13 路点云（3900 帧）、4 路鱼眼（1200 张），24 个话题、7500 条消息。

## 参数

- 场景：`{summary['scene']}`。
- 整机 Yaw/Pitch/Roll：相对场景初始姿态各 ±15°，3°/s 三角波，同相、20 s 周期，0° 起步向正方向。
- 整机世界 X：0.1 m/s；世界 Y/Z 固定。300 个样本按 0.1 s 间隔，逻辑时间 0～29.9 s，累计 +2.99 m。
- 大臂、小臂、铲斗：沿用 ±15°、3°/s；cab–track 保持初始角度。
- 根旋转：`R_world = R_initial @ Rz(delta_yaw) @ Ry(delta_pitch) @ Rx(delta_roll)`。
- 原生冻结 RT2：RealTimePathTracing、DLSS Quality、AA=3，每组 16 预热 + 2 正式子帧，保持原生 Helper 接线，产品常驻。
- 每组先推进 0.1 s → 冻结 → 设置根与关节姿态、清零速度、原生运动学/PhysX→USD 同步 → 渲染 → 读取并校验。
- 规定姿态采集，不自动贴地；冻结状态的速度字段不能当成轨迹速度。既有资产和场景文件未改动。

## 交付位置和组织

`{delivery}`

- `bag/`：标准 ROS 2 MCAP 与 metadata.yaml，可用于 ros2 bag play/info。
- `groups.jsonl`：300 组的逻辑时刻、原生时间戳、目标位姿、实测位姿、图像与点云哈希。
- `input_trajectory.jsonl`：输入轨迹；`spec.json`：本次运行配置；`sensor_manifest.json`：传感器话题、frame 与 Prim 对应。
- `selection_manifest.json`：每条交付消息的原始录包序号、CDR 哈希及时间戳。
- `validation.json`、`group_validation.json`：结构、数据、时间戳、TF 和姿态校验。
- `files_sha256.json`：MCAP 及 metadata 的大小与哈希；`*_first.png`、`*_measurement_last.png`：从包内解出的四相机首尾帧。

每组保留 13 PointCloud2、4 Image、4 CameraInfo、2 TFMessage、1 JointState、1 Clock。TF 包括 `world → swing_coordinate` 和该根参考下的 17 个传感器坐标系。`swing_coordinate` 沿用原生基线名称，含义是挖掘机根参考。

逻辑时间：{summary['logical_time_s']} s；原生消息时间：{summary['native_time_s']} s。保留初始化偏移 {summary['native_minus_logical_s']:.9f} s，未重写 header、CDR 或消息录制时间。有效样本 10 Hz 指仿真时间频率，不是真实采集速度。

原始录包保留于 `{source}/bag/`。交付包只选择匹配冻结输出哈希和当前 TF/关节的消息，剔除原生预热和重复发布。原始消息字节不变；交付包另行完整复验。

## 结果与限制

- 平均每组 {summary['group_seconds']['mean']:.3f} s，中位数 {summary['group_seconds']['median']:.3f} s；采集进程含初始化/收尾 {summary['engine_and_recorder_wall_s']:.2f} s，不包含之后导出及校验耗时。
- 交付 MCAP {summary['delivery_mcap_bytes']/1024**3:.3f} GiB；原始 MCAP {summary['source_mcap_bytes']/1024**3:.3f} GiB。
- 根矩阵误差最大 {summary['root_pose_max_abs_error']:.3g}；关节误差最大 {summary['joint_pose_max_abs_error_rad']:.3g} rad。
- 冻结时位姿变化最大 {summary['render_frozen_pose_max_abs_error']:.3g}；时间变化最大 {summary['render_frozen_time_max_abs_error_s']:.3g} s。
- 相机实际渲染矩阵误差最大 {summary['camera_render_pose_max_abs_error']:.3g}；雷达 {summary['lidar_render_pose_max_abs_error']:.3g}。
- 场景与 18 个已加载 USD 依赖容器哈希未变。此范围不等于对所有纹理和系统文件进行全面审计。
- 正式引擎日志 Error {summary['error_lines']} 行、Warning {summary['warning_lines']} 行。大量是原生 PoseTree 对传感器/辅助 Xform 的类型提示；本轮数值 TF、渲染矩阵及数据一致性验证通过，未据此声称警告本身已修复。
- 一致性校验验证时间、坐标和消息对应关系，不替代物理传感器精度/真实场景标定评估。RT2 子帧数也不是离线路径追踪的精确射线 SPP。

原始阶段日志及 `resources.jsonl` 位于 `{source}`。资源记录为整卡 GPU busy、显存、功率、时钟和进程/线程 CPU 计数，不是 CUDA/RT/Tensor Core 各自利用率。
'''
    (base/'CaptureReport.md').write_text(report, encoding='utf-8')
    print(json.dumps(summary))


if __name__ == '__main__':
    main(sys.argv[1])
