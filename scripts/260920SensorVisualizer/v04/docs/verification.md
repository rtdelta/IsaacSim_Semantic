# v04 验证说明

本轮以实际文件为证据，不沿用旧版本验证结论。完整结果见 deployment_and_native_test.md。

- docs/evidence/portable_tests.txt：29项可移植测试，包括丢失/晚回调、独立数组所有权、全传感器屏障、取消与原生排空、错误源时间/矩阵、失败资源关闭、缓冲ACK和跨线程CPU计时。
- docs/evidence/final_gated_comparison.json 与 final_throughput_comparison.json：完整MCAP解码及同等灯光/姿态/时间对照。
- docs/evidence/controls.json：实际Kit/Omni.UI功能验收及资产前后哈希，不等同网页桌面视觉验收。
- docs/evidence/native_final_analysis.json 与 native_direct_analysis.json：原生栈、调度、Vulkan/CUDA/OSRT证据及采集限制。
- reports/isolation_check.json：生产入口不依赖旧代码；旧版哈希核对。experiments明确可以读取基线，仅用于诊断。

尚未完成的长100组统计与闭源内核精确归因不宣称已验证。图像与点云不宣称位级一致。失败实验完整保留，不计作成功收益。
