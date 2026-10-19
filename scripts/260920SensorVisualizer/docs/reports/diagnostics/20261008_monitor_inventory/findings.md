# 当前云实例资源监控工具清单

只读观察时间：2026-10-08 18:25:13 北京时间。目标别名：isaac-new。
操作 ID：20261008T102516Z_51ba5fee8ef1。未安装软件、修改配置、启动项目或停止进程。

## 已找到的工具

- 整体终端面板：btop、top。
- 桌面进程面板：xfce4-taskmanager。
- GPU：nvidia-smi；支持的具体监控指标以本机输出为准。
- CPU/内存/交换/部分I/O：vmstat、free。
- 磁盘容量：df；网络：ip、ss；周期刷新：watch。
- CUDA 内核分析：ncu，位于 /usr/local/cuda/bin/ncu。未测试性能计数器权限，不等于可分析全部 RTX/Vulkan 渲染。

PATH 未找到 htop、nvtop、atop、glances、pidstat、iostat、mpstat、sar、iotop、perf、dcgmi、nsys。
nsys 也未在本次检查的 /opt/nvidia/nsight-systems 与 /usr/local/cuda/bin 常见位置找到；未全盘搜索。

## 配额与统计范围

- os.cpu_count 和 CPU affinity 均显示128，cpuset为0-127。
- cpu.max为1400000 100000，实际CPU时间配额约14核；128个可见逻辑CPU不代表分配了128核算力。
- memory.max为128849018880字节，即120 GiB；观察时memory.current约13.79 GiB。
- /proc/meminfo显示约1 TiB宿主可见内存，不能作为实例120 GiB配额的使用率分母。
- 可见GPU：NVIDIA L40，驱动580.126.09，nvidia-smi报告总显存46068 MiB。
- 本次cgroup CPU、memory、IO pressure文件均可读取。
- cpu.stat、io.stat为累计计数，应求时间差计算速率；多层块设备I/O不可直接全部相加。
- 本次没有采样当前各进程负载，不能据此判断Isaac采集状态。

## 使用建议

三个终端分别运行：

```bash
btop
```

```bash
nvidia-smi dmon -s pucm -d 1
```

```bash
nvidia-smi pmon -s um -d 1
```

GPU监控可用Ctrl+C结束。主线程及其他线程使用top -H -p PID查看，将PID替换为目标Isaac进程号。
在云桌面终端运行xfce4-taskmanager可打开现有图形任务管理器；本次未实际启动它。

查看配额与限流：

```bash
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpu.stat
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/cpu.pressure
cat /sys/fs/cgroup/memory.pressure
cat /sys/fs/cgroup/io.pressure
```

v03已有进程CPU/RSS、主线程CPU、整卡GPU及部分cgroup采样，不能替代完整系统监控或原生性能分析。
确认渲染瓶颈需要Nsight Systems/Kit性能跟踪，关联Vulkan/CUDA、线程调度与组阶段；本次未安装或启动性能分析器。

## 来源及操作覆盖

- 本地项目resources.py及远端只读工具/配额清单。
- NVIDIA nvidia-smi官方说明：https://docs.nvidia.com/deploy/nvidia-smi/index.html
- Linux cgroup v2说明：https://cdn.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html
- btop官方项目：https://github.com/aristocratos/btop
- Nsight Compute官方支持范围：https://docs.nvidia.com/nsight-compute/ReleaseNotes/topics/library-support.html

公开文档访问记录为自报，不是网络抓包。SSH审计只覆盖本次包装器调用，不代表整个实例的系统审计。
