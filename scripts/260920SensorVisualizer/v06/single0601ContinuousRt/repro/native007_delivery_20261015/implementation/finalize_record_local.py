"""Finalize the execution record from the verified local evidence bundle."""
import collections,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BASE=ROOT/'reports/native007_delivery_20261015';E=BASE/'evidence'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
d=read(BASE/'summary.json');f=d['first_matrix'];inv=d['final_inventory'];meta=read(E/'final_metadata_crosscheck.json')
report=ROOT/'docs/Experiments/008_原生旋转偏差分层定位_实现与执行记录_20261015.md';text=report.read_text(encoding='utf-8')
old='状态：执行中，以下记录不代表实验已完成。'
new=f"状态：本轮已执行并归档；首批强制矩阵为部分覆盖（{f['captured_runs']}/{f['planned_runs']} 轮实际采集，{f['captured_targets']}/{f['planned_targets']} 个计划目标）。全部结果 `formal_continuous_acceptance=false`。"
text=text.replace(old,new)
intro='''\n\n核心结果：MyAiry 的官方 API 与原生入口短轮一致；三次长轮确认距离的历史姿态候选与输出参考系差异。关闭累积改变原生输出节奏；关闭 Motion BVH 改变姿态和距离候选，但没有恢复当前姿态正确性。结论收紧到原生运动姿态与距离生成相关路径，尚未取得实际历史消费追踪，不能定位具体 SDK 函数，也不能把官方示例资产的动态问题记为已复现。'''
index=text.index('\n\n## 1.');text=text[:index]+intro+text[index:]
text=text.replace('## 6. 当前观察与结论边界','## 6. 实现资格阶段观察（历史记录）')
text=text.replace('这只是当前 E1/E2 层证据；','这部分短轮只是 E1/E2 层证据；最终长轮和单因素结果见第 10 节。')
start=text.index('## 7. 尚待完成');end=text.index('## 8.',start)
text=text[:start]+'''## 7. 未覆盖与未解决事项

官方 A2/A3 未取得静态名义射线资格，其动态分支保留阻断；C1 关闭累积后未满足原定 10 Hz 节奏；C2 的完整有效返回集合配对在部分目标不一致，不作为工程修复验收。实际历史端点消费、射线查询时刻、插值权重和发射射线状态仍不可取得。C3、C4、运动对象互换和构建版本交叉未执行，属于本轮未扩展范围。

''' +text[end:]
text=text.replace('## 9. 阶段性新增事实（后续长轮尚在执行）','## 9. 扩展触发与异常保留记录')
text=text.replace('后续预登记采用完整输出重复观测及每轮独立名义模型','后续三次长轮采用完整输出重复观测及每轮独立名义模型')
lines=['\n## 10. 最终矩阵与分层指标\n',
 f"首批固定分母为 **{f['planned_runs']} 轮、{f['planned_targets']} 个目标**：实际采集 {f['captured_runs']} 轮、{f['captured_targets']} 个目标；阻断 {f['blocked_runs']} 轮、{f['blocked_targets']} 个目标。实际采集中的 4 个官方资产静态轮未取得模型资格，不算合格动态证据。q01 实现迭代和各扩展不混入这个分母。\n",
 '| 阶段 | 条件 | 工况 | 轮数/目标 | 距离失败 | 输出方向失败 | 平面失败 | yaw 失败 | 原生姿态失败 | 相邻增量失败 | 可区分候选 |',
 '|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|']
for g in d['groups']:
 if g['phase'] not in ('main','speed','confirm','coded'):continue
 candidates=', '.join(f'{k}:{v}' for k,v in g['distinguishable_candidates'].items()) or '无可区分候选'
 unknown=sum(v for k,v in g['candidate_status'].items() if k!='distinguishable')
 if unknown:candidates+=f'; 不可区分/歧义:{unknown}'
 lines.append(f"| {g['phase']} | {g['condition']} | {g['profile']} | {g['runs']}/{g['targets']} | {g['distance_fail']} | {g['direction_fail']} | {g['plane_fail']} | {g['yaw_fail']} | {g['native_pose_fail']} | {g['increment_fail']} | {candidates} |")
lines += ['\n门槛：距离 P95 10 微米；输出方向 P95 1e-4 rad；平面 P95 5 mm；几何 yaw 1e-4 rad；相邻几何增量 1e-4 rad。输入旋转和逐物理步/扫描增量另按 1e-6 / 2e-6 rad 检查。表中平面、yaw、距离分列；原 `geometry_absolute_ok` 是包含距离的联合条件，不能把联合失败解读为每个几何分量都失败。相邻增量分母是每轮 99 对。\n',
 'SENSOR 与 WORLD 的方向指标都依据已声明坐标规范化后计算；WORLD 不重复施加传感器姿态。方向由输出推导，不是独立实际射线观测。不同有效返回集合的 C2 比较保留所有目标和返回，未筛交集。\n',
 '### 10.1 报告姿态端点预测\n',
 '| 阶段 | 条件/工况/重复 | 报告端点中点距离通过数 | frameEnd 接近当前步 | frameEnd 接近前一步 |',
 '|---|---|---:|---:|---:|']
for stage,summary in d['stage_analyses'].items():
 for r in summary['header_predictions']:
  label='/'.join(Path(r['run']).parts[-4:]);lines.append(f"| {stage} | {label} | {r['header_midpoint_passed']} | {r['header_end_current']} | {r['header_end_previous1']} |")
lines += ['\n该中点模型在分析前固定，不拟合延迟、旋转或时间偏置。它使用 GMO **对外报告**的 frameStart/frameEnd 姿态；这些姿态的时间字段属于原生输出时间域，未擅自当作物理源时间。模型预测成立是 E2 证据，不能据此证明实际 GPU 插值权重为 0.5 或内部使用 SLERP。\n',
 '### 10.2 固定共同朝向与非匀速输入\n']
common=d['stage_analyses']['speed']['common_orientation_summaries']
lines.append(f"R3P 与 R6P 每一条件/重复使用事前固定的 50 个共同朝向，共 {len(common)} 组。全部实际朝向匹配；每组 {common[0]['candidate_differences']} 个目标的候选不同。由此排除‘仅由绝对朝向决定’这一解释，但不能单独区分步长、速度、历史端点更新规则或精度阈值。\n")
coded=read(E/'stage_analysis/coded/coded_input_review.json')
lines.append(f"C0 编码输入完成 {len(coded)} 次独立初始化，每次 100 个目标、完整 {coded[0]['expected_steps']} 个物理步（含固定排空）。本地预登记完整角度表 SHA `{coded[0]['preregistered_input_sha256']}`；所有运行的全表、运行时哈希和实际输入检查一致。每次扫描期望增量使用六步实际角增量之和。候选歧义不强制选解，也不称为随机测试。\n")
lines.append('**中点模型存在稳定反例，不能作为完整根因。** 每次编码实验只有 98/100 个目标通过报告端点中点预测，三次合计 294/300。第 17、70 个目标（零起始索引 16、69；局部物理步 102、420）在三轮中均为反例：实际增量 0.02°，报告 frameEnd 已是当前步，但距离符合前一步/frameStart；中点距离 P95 约 1.57 mm，前一步预测约 2 微米。说明对外报告端点不能完整替代实际射线消费状态。\n')
small=read(E/'stage_analysis/coded/exploratory_small_rotation.json')
lines.append('编码每轮按当前物理步增量分层：0.02° 的 34 个目标全部为 previous1；0.05° 的 34 个目标中 half 21、previous1 13；0.10° 的 32 个目标全部为 half。三轮分层计数一致。此表为全样本描述，没有剔除反例。\n')
lines.append('另保存了事后探索性的 float32 四元数分量乘积求和及 float64 归一化内积。该数值描述不等于 GPU 使用的运算顺序、归一化方式或分支条件，不能据此宣布某个浮点阈值已被证明；尤其上述两个反例仍要求区分元数据更新和实际距离路径。\n')
lines += ['## 11. 机制结论及证据边界\n',
 '1. **应用业务链与 API 封装不是当前主要解释。** A0/A1 同资产短轮在完整身份集合配对下没有质量类别或候选差异，径向输出相同；A1 只有短轮证据，不能外推长期稳定性。官方 API 产品/annotator 拓扑差异已记录，因未触发差异，没有增加桥接组。\n',
 '2. **输出参考系与距离形成必须分开。** WORLD 输出方向可与前一步/frameStart 对应，距离却对应报告端点中点；SENSOR/SPHERICAL 的径向分量保留同一距离候选。因此仅修改世界坐标转换不能解释或消除全部距离异常。\n',
 '3. **Motion BVH 对原生姿态和距离候选有可重复影响。** C2 的独立完整输出重复确认候选变化，且仍未达到当前姿态距离门槛。有效返回集合差异同时存在；严格逐点配对未通过，E3 结论限于单因素对整组输出行为的约束，不是等价扫描下的质量修复证明。\n',
 '4. **报告端点更新是更具体的候选边界。** 匀速与非匀速数据检验端点预测；是否存在小旋转更新阈值、精度影响、历史状态构造或查询时间规则，仍需直接追踪。不能把几何候选名称当作实际历史槽位号。\n',
 '5. **官方资产对照仍有缺口。** A2/A3 静态原始采集、解析和时钟检查成功，但原参数下的名义射线模型不合格。保留噪声和 emitter fire time，未降低门槛；因此不能宣称‘官方示例资产与官方 API 的动态组合也已复现’。\n',
 'G4 已审阅 68 份安装版接口/契约文件。`Transformation.interpolationFactor` 是调用方构造后传给 `ILidarPCConverter.setTransformation` 的输入，并非读取实时传感器内部权重的接口；SimulationManager 的 31 样本时钟映射也不是 64 槽变换历史。未发现可读取实际消费端点、查询时间及逐射线 origin/direction 的公开入口。没有把新建对象的默认字段冒充内部证据。\n',
 '下一层应在厂商调试构建或明确的原生诊断接口中关联同一原生事件的：输入 Xform 提交、渲染实例更新、历史端点写入、实际查询时刻/权重、射线 origin/direction 与 GMO 打包时刻；再做构建版本交叉。当前结果支持优先排查 SDK/渲染原生运动状态路径，但不足以裁定具体代码缺陷。\n',
 '## 12. 回读、文件保护和交付\n']
raw=inv['all_preserved_raw_events'];targets=inv['all_preserved_targets'];allruns=len(inv['runs']);partial=len(inv['partial_runs'])
lines.append(f"共保留 {allruns} 个有目标结果的运行（包含 q01 迭代）、{partial} 个暖机中止前缀，合计 {targets} 个目标、{raw} 个原生事件。原始文件清单回读完整状态为 `{inv['all_raw_readback_complete']}`；全部事件均做独立完整 GMO 解码，API 自有载荷另行交叉核验。最终新增官方 parser 端点/枚举/时间/扫描字段核对：{meta['decoded_files']} 个载荷，结果 `{meta['passed']}`。原 XYZ/GMO 大文件保留远端，紧凑证据包已回传并逐文件核验。\n")
lines.append(f"旧 005/006 锁定文件 {inv['locks']['native_instant_baseline']['files']} 个、007 主轮锁定文件 {inv['locks']['native_rotation_localization/v1']['files']} 个均无差异；原场景 SHA `{inv['original_scene_sha256']}` 未变。结束时未发现残留采集 Kit/worker；没有发布正式 READY。失败前缀、旧分析和重新分析分别保留，不覆盖原结果。\n")
lines.append('最终额外离线解析进程在成功保存 3,730 项核验结果后，普通可取消退出请求未使窗口退出；经 PID、入口和进程组核验后只对该任务进程发送 SIGTERM，正常退出码为 0，原实验采集早已结束。清理记录单独保存在 `final_metadata_parser_cleanup.json`。入口后续修正为与采集器一致的不可取消退出，实际执行过的旧入口快照保留；未为此重复采集。\n')
lines += ['本地机器汇总：[summary.json](../../reports/native007_delivery_20261015/summary.json)；归档清单：[delivery_manifest.json](../../reports/native007_delivery_20261015/delivery_manifest.json)；最终文件检查：[final_inventory.json](../../reports/native007_delivery_20261015/evidence/final_inventory.json)。\n',
 '远端原始根目录：`/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt/reports/native_rotation_localization/native007_20261015_v1/`。各次执行和传输操作由本地 cloud-instance-ops 审计保存，外部文件只有用户批准的官方单资产批次。\n',
 '## 13. 图表\n']
for name,title in [('absolute_yaw_residuals','绝对 yaw 残差，未减去首帧偏差'),('distance_history_candidates','完整目标的距离候选'),('common_orientation_speed_comparison','固定共同朝向的速度对照'),('adjacent_increment_errors','相邻扫描增量'),('motion_bvh_full_output_confirmation','Motion BVH 完整输出重复'),('coded_header_prediction','非匀速输入与固定报告端点模型')]:
 if (BASE/'figures'/(name+'.png')).is_file():lines.append(f'![{title}](../../reports/native007_delivery_20261015/figures/{name}.png)\n')
report.write_text(text+'\n'+'\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps({'report':str(report),'first_matrix':f,'preserved_targets':targets,'raw_events':raw,'metadata_crosscheck':meta['passed']}))
