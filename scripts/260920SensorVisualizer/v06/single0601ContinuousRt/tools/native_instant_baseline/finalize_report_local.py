# -*- coding: utf-8 -*-
"""Write the final execution report from verified delivery and preservation evidence."""
import collections,json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def run():
    result=read(ROOT/'reports/native005_summary_20261015/results.json');records=result['records'];comparisons=result['comparisons']
    if len(records)!=39 or not all(r['measurement_qualified'] and r['cleanup_ok'] for r in records):raise RuntimeError('Cannot finalize full completion')
    if not all(c['all_measurement_and_pair_qualified'] for c in comparisons.values()):raise RuntimeError('Incomplete pair gates')
    inventory=read(ROOT/'reports/native005_delivery_20261015/native005_20261015_v1/final_inventory.json')
    preservation=read(ROOT/'reports/native005_final_preservation_20261015.json')
    if inventory['source_lock_mismatches'] or not inventory['all_raw_GMO_readback_complete']:raise RuntimeError('Lock or readback failed')
    doc=ROOT/'docs/Experiments/006_原生InstantLiDAR独立基线_实现与执行记录_20261015.md';body=doc.read_text(encoding='utf-8').split('\n## 5.')[0]
    body=body.replace('六组最终资格和架构配对已通过，代码已锁定，24 轮必做矩阵正在执行。旋转资格中两条链路均复现绝对几何异常，不能把测量资格通过写作连续采集通过。',
        '实现及本轮矩阵执行完成：6 轮 E 资格＋24 轮必做主对照＋9 轮 D 对照，共 39 轮、3,108 个计划目标。独立最小链路与现有链路稳定复现相同旋转异常，历史长度 64→8 未消除异常；正式连续采集仍未通过。')
    body=body.replace('完整终态及逐轮表将在收尾后写入下节。','全部预登记运行现已结束，完整终态及逐轮表见下节。')
    lines=['','## 5. 完整主轮结果','',
        '四类条件均完成两组各三次独立初始化，每轮固定 100 目标、99 对相邻扫描。下表数字按 r01/r02/r03 依次列出，失败目标与 unknown 均未从分母删除。',
        '', '| 组别 | 条件 | 原生 pose 失败（各 /100） | 绝对几何失败（各 /100） | 增量失败（各 /99） | 每轮历史候选 |',
        '|---|---|---:|---:|---:|---|']
    main=[r for r in records if r['phase'] in ('main','D_main')]
    for group in ('M_E','P_E','M_D'):
        for profile in ('S0','R3P','R3N','R6P'):
            rr=sorted([r for r in main if r['group']==group and r['profile']==profile],key=lambda r:r['repeat'])
            if not rr:continue
            candidates=rr[0]['candidate_counts'];same=all(r['candidate_counts']==candidates for r in rr)
            label='静态等价、不可辨识' if profile=='S0' else '；'.join(f'{k}={v}' for k,v in candidates.items())
            if not same:label=str([r['candidate_counts'] for r in rr])
            nums=lambda k:'/'.join(str(r[k]) for r in rr)
            lines.append(f"| {group} | {profile} | {nums('native_pose_failed')} | {nums('geometry_absolute_failed')} | {nums('geometry_increment_failed')} | {label} |")
    lines+=['','全部 39 轮测量资格、数据完整性和退出清理通过；缺失、重复、时间未分配及几何 unknown 均为零。静态几何通过只用于本模型资格；运动载荷重算新鲜度保持 unknown。',
        '', '完整 39 轮逐轮分母与候选统计见 [逐轮表](../../reports/native005_summary_20261015/run_table.md)，逐目标指标、交叉表和完整分位数见 [结果索引](../../reports/native005_summary_20261015/results.json) 及 [元数据目录](../../reports/native005_delivery_20261015/)。',
        '', '6°/s 每轮原生 pose 和相邻增量均通过，但绝对几何 100/100 失败。不能把正确增量或元数据一致替代当前源姿态下的点云一致性。',
        '', '## 6. 配对、配置与绝对误差','',
        'E 主轮 12/12 对、资格 3/3 对配对成立；环境、资产、schema、输出拓扑、初始化和源 tick 相位一致。所有配对的逐目标三轴判定及历史候选差异数均为零。M/P 实际输入位置差为零，最大旋转差约 2.22e-16 rad；这是数值等价，不声称所有矩阵字节相同。',
        '', 'D 已完成 3 个短轮资格和 S0/R3P 各 100×3，全部逐轮读回 history=8，其余有效配置、输入及拓扑与 E 匹配。D/E 的 3 个资格对及 6 个主轮对配置归因条件成立。恢复本构建默认历史长度没有改变本轮逐目标失败和候选分布，不能据此排除历史查询或插值机制本身。',
        '', '射线/表面列为每个目标内点残差的 P95，再取全部目标及三轮的最大值；yaw/增量列为每轮目标序列绝对误差的 P95，再取三轮最大值。未扣除首帧偏差，完整 P50/P95/P99/max 与带符号序列仍保留。',
        '', '| 组别 | 条件 | 当前射线残差 P95 最大（mm） | 表面残差 P95 最大（mm） | 绝对 yaw 误差 P95 最大（°） | 相邻增量误差 P95 最大（°） |',
        '|---|---|---:|---:|---:|---:|']
    for group in ('M_E','P_E','M_D'):
        for profile in ('S0','R3P','R3N','R6P'):
            rr=[r for r in main if r['group']==group and r['profile']==profile]
            if not rr:continue
            lines.append('| %s | %s | %.7g | %.7g | %.7g | %.7g |'%(group,profile,max(r['current_ray_p95_max_m'] for r in rr)*1000,max(r['plane_p95_max_m'] for r in rr)*1000,
                math.degrees(max(r['absolute_yaw_error_rad']['0.95'] for r in rr)),math.degrees(max(r['absolute_increment_error_rad']['0.95'] for r in rr))))
    common=result['common_orientation_comparison']
    lines+=['','共同朝向控制使用预登记的 0.6°、1.2°、…、30.0°，每个重复 50 个目标，实际输入矩阵按门槛核验。R3P/R6P 候选不同的目标数为：'+ '；'.join(c['group']+' '+c['repeat']+' '+str(c['candidate_different'])+'/50' for c in common)+'。完整 100 目标分母未被此子集替代。',
        '', '## 7. 图表','',
        '![源时间与物理步](assets/native005_20261015/source_physics_time.png)',
        '', '![绝对yaw与带符号误差](assets/native005_20261015/absolute_yaw_and_error.png)',
        '', '![相邻扫描增量误差](assets/native005_20261015/adjacent_increment_error.png)',
        '', '![历史候选](assets/native005_20261015/history_candidates.png)',
        '', '![共同朝向速度对照](assets/native005_20261015/common_orientation_speed_control.png)',
        '', '## 8. 机制解释与仍未证实部分','',
        '已证实：异常复现不需要旧 Owner、Backend 或生产状态账本；独立最小入口与现有链路在合格配对下得到相同失败模式。完整 GMO 与 Extractor 一致，独立几何与旧实现交叉一致；两组旋转短轮完整数据在 Windows Python 3.9 重新回读、解码、计算，也与远端 Python 3.12 结果一致。',
        '', '源事件按 source/ref 时间唯一关联实际物理步，所有目标输入和实际推进合格，因此不能只用 Writer 晚到或命令未施加来解释这些几何偏差。静态通过、正反转均失败、双倍转速呈稳定半步，以及相同朝向下不同每步角增量的区别，把后续重点收敛到两条链路共同使用的原生旋转状态消费、变换历史、射线生成和输出坐标表达路径。',
        '', '受支持的解释是“点云有效朝向符合历史姿态候选”，并非已经观测到 SDK 内部选择了某个历史槽位或确切插值权重。D 的结果只说明历史容量 8/64 的单项切换不足以修复；不能据此认定整个配置或原生 SDK 某函数无误/有误。',
        '', '本轮没有取得 GPU 射线实际姿态、历史变换样本、查询时间、插值权重和原生重算标识，无法把根因锁到具体 SLERP、float32 阈值或函数。004 中既有数值阈值模型解释力不足，本轮不将其升级为结论。下一步应以独立基线为复现入口，优先取得这些实际消费状态；当前 Fabric 世界矩阵和时间映射不能替代它们。',
        '', '## 9. 保存、验证及保护范围','',
        (f"原始保留共 {inventory['all_preserved_runs']} 轮、{inventory['all_preserved_targets']} 个计划目标、{inventory['all_raw_events']} 个原始事件；"
         "其中 q01/q02/q03 仅作修订历史，不混入最终 39 轮主结果。"
         f"共 {inventory['all_evidence_files']} 个采集证据文件，约 {inventory['all_evidence_bytes']/2**30:.3f} GiB。"
         f"全部 {inventory['full_GMO_decoded_including_corrected_q01']} 个 GMO 已完整回读解码；"
         "q01 另存 corrected_decoder_readback，原失败报告没有改写。"),
        '', f"250 个主轮锁定文件最终 SHA 无变化；峰值自有队列 {inventory['max_queue_peak_bytes']/2**20:.2f} MiB，单轮原始预算占用最大 {inventory['max_reserved_disk_bytes']/2**30:.3f} GiB；收尾空闲 {inventory['free_bytes']/2**30:.2f} GiB。每轮独立 Kit 串行，未安装或下载新依赖。",
        '', '全部完整 XYZ/GMO 留存在远端原路径。已回传所有紧凑 JSON/JSONL、逐目标分析、原始事件元数据、原始文件 SHA 清单和冻结配置，并校验归档及逐文件 SHA；大型传感器数组和全量载荷未全部复制到本地。另回传 M_E/P_E 各一轮 R3P q04 的完整数据并完成本地数值复算。',
        '', '[本地归档校验](../../reports/native005_delivery_20261015/local_transfer_verification.json)；[最终清单](../../reports/native005_delivery_20261015/native005_20261015_v1/final_inventory.json)；[主轮源码锁](../../config/native_instant_baseline/main_code_lock.json)；[保留范围复核](../../reports/native005_final_preservation_20261015.json)。',
        '', f"旧 v06 源文件保持不变：{preservation['source_unchanged']}；原始 USD 保持不变：{preservation['scene_unchanged']}；已有 {preservation['ready_count']} 份 READY/manifest 保持不变：{preservation['ready_unchanged']}。收尾本任务 Kit/worker 数为 {len(preservation['processes'])}。",
        '', '重要部署均经既有凭据引用、主机指纹与 GPU 身份核验并留审计。被覆盖的项目文件保存在远端 `.deploy_backups/<audit-id>/`；最终采集部署记录见 [部署清单](../../reports/native005_final_code_deployment_20261015.json)。如需恢复共享诊断入口或保存器，应按对应初始部署备份逐文件恢复；不要整树覆盖既有用户修改，不删除本轮证据。',
        '', '## 10. 未完成与适用边界','',
        '- 正式连续采集故障尚未修复；`formal_continuous_acceptance=false`，没有生成新的 READY。',
        '- 原生 GPU 状态历史和射线实际消费状态的直接证据、载荷重算新鲜度仍未取得。',
        '- 可选 O_D/LidarSensor 路径、本轮新的 120 Hz 扩展、混合运动、机器人/接触、多传感器及长期运行未执行；不能把当前纯旋转房间诊断推广为生产验收。',
        '- 保持窗口属于先前工程规避实验，本轮没有用保持、额外渲染、吸附时间或姿态修正使数据通过。',
        '', '复现入口与命令见 [README](../../tools/native_instant_baseline/README.md)。本轮完成的是 005 所要求的独立实现、必做矩阵、推荐 D 对照及证据交付；内部机制定位和生产修复继续保持未完成。','']
    doc.write_text(body+'\n'+'\n'.join(lines),encoding='utf-8');print(str(doc))
if __name__=='__main__':run()
