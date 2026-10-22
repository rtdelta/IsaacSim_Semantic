# GPU 状态记录工具调查

只读观察时间：2026-10-09 10:02:21 北京时间。目标：isaac-new。
SSH 操作：20261009T020222Z_841537c679b3。
本次只检查可执行文件、已知工具进程、帮助、常见记录位置，并做一次GPU CSV查询。
没有安装软件、启动GPU录制、启动后台服务、修改项目源码或系统配置。

## 远端已有能力

- /usr/bin/nvidia-smi：--query-gpu、--filename、--loop、dmon、pmon、daemon、replay均出现在帮助中。
- 一次CSV查询成功，字段包括timestamp、index、utilization.gpu、utilization.memory、memory.used、memory.total、power.draw、temperature.gpu、clocks.current.graphics、clocks.current.memory。
- nvidia-smi原生支持周期查询与文件输出，不需要另写GPU采样器。本次没有测试持续写文件。
- daemon帮助说明可后台采样并压缩保存；replay可回放或导出。二者标为experimental，帮助声明裸机Linux支持；本云容器的实际运行兼容性尚未验证，不应因存在帮助就宣称可用。
- nvitop位于/usr/local/bin/nvitop，btop位于/usr/local/bin/btop。只确认入口存在，未启动它们。
- nvitop-exporter、gpustat、Glances、DCGM工具、Prometheus、Grafana、Telegraf、collectd、Netdata、atop、nmon在PATH及本次检查的常见额外入口目录中未找到。未做全盘搜索。
- 可见进程中没有匹配上述工具名称的持续监控进程；/var/log/nvstats及/var/run/nvsmi.pid不存在。
- 这不能排除平台或宿主机存在其他监控，也不能排除其他路径存有GPU日志。

## 时间对齐

同一次观察中，Python UTC为02:02:21，nvidia-smi时间为10:02:21，相差8小时。
该CSV时间字段不带显式时区，应在记录元信息中注明时区，并与项目日志统一转换。
只读单次GPU值不能用于判断一轮采集瓶颈。

## 常用候选及适配

- nvidia-smi CSV：当前优先，已安装，直接产出时间序列文件；后续只需确定字段、输出目录和进程启停。
- nvidia-smi daemon/replay：原生后台压缩历史，但为实验性且当前容器未运行验证。
- Glances：官方支持CSV/JSON等导出，GPU需要对应插件依赖；适合同时记录CPU、GPU、内存、磁盘、网络。远端未找到入口。
- nvitop：已存在的GPU/进程交互查看器；其Prometheus exporter是另一个组件，本机未找到入口。不能把打开终端面板当作已保存历史日志。
- gpustat：支持监控及JSON输出，主要是轻量查看，持久历史仍需文件或采集后端。本机未找到入口。
- DCGM Exporter + Prometheus + Grafana：成熟的长期GPU指标收集、存储、查看组合；Exporter本身不负责完整历史存储。当前没有发现对应入口，部署复杂度高于单轮CSV。

2026-10-09所见GitHub社区规模：Glances约33.7k stars，nvitop约7.2k，gpustat约4.4k，DCGM Exporter约1.9k。
Stars仅作为社区关注度参考，不等于实际安装量或用户量；没有找到可信的跨项目实际使用量统计。

## 官方及项目来源

- NVIDIA CLI：https://docs.nvidia.com/deploy/nvidia-smi/index.html
- Glances：https://github.com/nicolargo/glances
- Glances CSV示例：https://github.com/nicolargo/glances/blob/develop/docs/glances.rst
- nvitop：https://github.com/XuehaiPan/nvitop
- gpustat：https://github.com/wookayin/gpustat
- DCGM Exporter：https://github.com/NVIDIA/dcgm-exporter

外部访问为浏览公开资料，无远端下载；访问登记属于自报，不是网络抓包。
SSH证据仅覆盖本次检查，不是全实例监控或完整审计。
