# Gaussian / Motion BVH：实现层补充分析

日期：2026-09-17。对象仍为 Isaac Sim 6.0.1-rc.7 / Kit 110.1.2 的同一安装。
本轮对远端只读检查，没有启动仿真实验，没有修改远端场景、脚本或库。只新增本地分析文件。
本文件补充前一轮证据，不修改旧报告。

## 结论边界

此前已定位到原生实现主动拒绝模式 1，而非仅观察 Python 接口报错。
但是，“为什么开发者没有支持这个模式”的算法、GPU 查询和设计原因，尚未证明。

本轮新增的实现证据：
1. Gaussian 的实例缓冲区使用每条 64 字节的记录。
2. Gaussian 初始化自己的 TLAS 时，传给共用创建辅助函数的模式字段为 0。
3. 共用辅助函数能区分模式 0 / 1，模式 1 被其日志表示为 motion raytracing ENABLED。
4. 上层构建任务仍将模式 1 传给 Gaussian buildTlas；该函数拒绝模式 1。此点来自前轮运行时跟踪。
5. Gaussian 的创建前置检查明确要求 Ray Query 能力。这是待追踪的机制线索，不是已证实的冲突根因。

因此，现在的工作假设更具体：
Gaussian 子系统观察到的资源准备路径按普通模式组织，而上层任务会要求运动模式；本安装没有在这个调用点提供已验证的兼容路径。
仍不能据此断言：静态 Gaussian TLAS 无法与运动场景 TLAS 共存、必须扩大每个 Gaussian 记录、Ray Query 一定不支持相关用法，或只移除 guard 就可以正确运行。

## 证据 A：实例记录布局

函数入口 0x183030，内嵌完整签名：
rtx::scenedb::PreprocessedGaussians::createInstanceBuffer(omni::span<carb::graphics::RaytracingInstanceDesc>)

关键代码：
- 0x1832b5 从对象 +0x960 读取计数。
- 0x1832ca 左移 6 位，即乘 64，用于 InstanceList 缓冲区尺寸。
- 0x1834ce 输入 span 长度乘 64。
- 0x183500 写记录 +0x33 为 0xff，0x183504 指针递增 0x40。
- 0x183590 写记录 +0x38 的 8 字节值，0x183594 指针递增 0x40。

这些字段和步长与普通 Vulkan 实例记录布局相符，但不能只凭相符就把 Carbonite 的所有内部类型、字段或后端调用视为已经恢复。
记录中没有在此布局内给出两个独立的 3x4 变换矩阵；不排除对象运动存放于外层实例或其他资源。

## 证据 B：初始化 TLAS 的模式为 0

调用处：
- 0x183de4：rsi = rbp - 0x140，指向创建描述数据。
- 0x183e26：将 rbp - 0xf8 处的 8 字节置零。
- 因为 -0xf8 - (-0x140) = 0x48，描述数据 +0x48 的字段为零。
- 0x183e68：调用辅助函数 0x185110。
- 传入的 TLAS 资源数组起点为 Gaussian 对象 +0xa00，scratch 数组起点为 +0xc00。

辅助函数：
- 0x18512b：读取输入描述 +0x48 至 r12d。
- 0x1853c7–0x1853d3：用此值选择每模式资源槽组，偏移是 mode * 128。
- 0x1853de–0x1853f5：比较该值是否为 1，选择 ENABLED / DISABLED 日志文字。
- 对应日志为 [MBVH]: Creating acceleration structure ... with motion raytracing ...，位置在前轮及本轮保存的 helper 反汇编和字符串证据中。

因此可追踪确认：此 Gaussian 初始化调用选择了模式 0 的资源槽组。
这里是静态代码分析；本轮没有增加该初始化函数的 GDB 实参采样。

## 证据 C：Ray Query 是创建前置条件

观察到的创建入口位于 0x184810。
它遍历设备，读取返回的设备能力结构 +0x280，检查位 0x40。
失败路径引用明确错误：
Failed to create PreprocessedGaussians: Ray query is not supported on device %d

所有设备通过该检查后，才进入内部初始化（0x182450）和 GPU 资源初始化（0x183bb0）。
这是能力检查和相关初始化调用的代码证据，尚未取得 Gaussian GPU 着色器中的具体查询指令与时间参数。
不能从错误文本直接推出“标准 Ray Query 的限制就是本问题根因”。

## 源码可见性

远端 omni.hydra.rtx 扩展目录本次统计到 48 个 .so 文件，未发现 .cpp / .h / .hlsl / .glsl / .slang / .ptx / .cu / .cuh 文件。
在检查的安装目录中找到 ParticleField3DGaussianSplat 的 schema C++ 文件；它们定义场景属性，不是 PreprocessedGaussians 的 RTX 加速结构实现。
未取得 PreprocessedGaussians.cpp、BvhHelpers.h 的原始文本。
二进制中出现源码路径不代表这些源文件在安装包中存在。
公开检索也未取得上述实现的原始源码；这不等于证明任何渠道都不提供源码。

NVIDIA 对开源边界的说明：
https://developer.nvidia.com/blog/?p=101431
文章明确区分 Isaac Sim 专用开源扩展与仍然闭源的部分 Omniverse Kit 组件。

## 下一步应验证的命题

优先区分下面两类机制：
- Gaussian 自己保持普通 TLAS 就能被运动场景正确查询，但上层统一传模式 / 构建分派缺少适配。
- 即使为 Gaussian 成功构建普通 TLAS，运动路径仍因资源绑定、射线时间、变换或查询着色器不匹配而失效。

有区分力的实验应保持引擎与场景 Motion BVH 为 1，仅在新诊断进程中让 Gaussian 的局部构建请求为 0，同时保留 Mesh 控制、相机 / LiDAR 输出、资源与原生参数记录。
这将是诊断干预，不应包装成生产修复；静态场景恢复也不能证明运动精度正确。
如果能恢复，再分开测试传感器运动、Gaussian 刚体运动和 Gaussian 内部形变，追踪时间依赖究竟位于哪层。

另一条证据路线是取得原始实现 / 调试符号 / 厂商说明，并定位：
- Gaussian 局部 TLAS 与整个场景 TLAS 的连接与绑定。
- Gaussian 查询着色器使用的遍历指令与时间。
- Mesh 运动实例路径与 Gaussian 实例路径的具体差异。
- 是否存在适用于静态 Gaussian 的回退，而当前调用没有选择它。

本轮未进行上述干预实验，也未验证其他版本。

## 原始证据

native_implementation_evidence.json：本轮目标库哈希与关键反汇编段。
static_inventory_and_normal_build.txt：扩展目录类型统计、普通构建段和相关字符串。
helper_disassembly.txt：共用创建辅助函数的静态代码片段。
xrefs.txt：相关内嵌标识的引用位置，保留 objdump 输出；最近导出符号标签不是可靠的实际函数名。

目标库 SHA256：
3fc6bb790d164decaf40aa52c5c76a6401e67e210f395e40cea9ea20ac6c57f0

## 公共 API 对照资料

普通 Vulkan 实例：
https://docs.vulkan.org/refpages/latest/refpages/source/VkAccelerationStructureInstanceKHR.html

矩阵运动实例：
https://docs.vulkan.org/refpages/latest/refpages/source/VkAccelerationStructureMatrixMotionInstanceNV.html

运动追踪扩展：
https://docs.vulkan.org/refpages/latest/refpages/source/VK_NV_ray_tracing_motion_blur.html

这些公开结构说明普通实例与运动实例的区别，不能代替对当前 RTX 内部实现的验证。

