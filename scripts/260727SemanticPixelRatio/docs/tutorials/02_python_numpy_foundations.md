# 02｜读代码前必须会的 Python 与 NumPy

这一章只补项目实际用到的概念。目标不是学完整门语言，而是看到源码时知道数据在哪里、谁拥有它、什么时候释放。

## 1. 模块、包和入口

项目根目录包含：

```text
run_compare.py
semantic_pixel_ratio/
    __init__.py
    pipeline.py
    ...
```

目录中存在 `__init__.py` 后，Python 会把它当作包。下面的导入：

```python
from semantic_pixel_ratio.config import load_config
```

表示从 `semantic_pixel_ratio/config.py` 中导入 `load_config`。

`run_compare.py` 末尾：

```python
if __name__ == "__main__":
    raise SystemExit(main())
```

表示只有当该文件作为程序入口执行时才调用 `main()`；当它被别的测试文件导入时，不会自动运行。

## 2. 类型提示不等于运行时检查

例如：

```python
def resolve_target_ids(
    mapping: SemanticMapping,
    labels: Tuple[str, ...],
) -> Tuple[int, ...]:
```

类型提示帮助人和静态检查器理解接口，但 Python 通常不会自动阻止调用者传入错误类型。项目仍需在 `load_config`、dataclass 的 `__post_init__` 和业务函数中显式检查。

## 3. dataclass 是什么

[models.py](../../semantic_pixel_ratio/models.py) 使用多个 `@dataclass(frozen=True)`：

```python
@dataclass(frozen=True)
class FramePair:
    ordinal: int
    frame_id: str
    whole_path: Path
    reference_path: Path
```

可以把它理解为有明确字段的数据记录。`frozen=True` 禁止正常赋值修改：

```python
pair.frame_id = "new"  # 会报错
```

这样做的价值是让跨线程、跨阶段传递的数据更不容易被意外改变。

项目中的主要数据对象：

| 类型 | 表示什么 |
|---|---|
| `FramePair` | 同一 frame ID 的两个文件路径 |
| `DatasetContract` | 全数据集统一的二维 shape 和 dtype |
| `LoadedBatch` | 一批帧对及 `[B,2,H,W]` 数组 |
| `BatchCounts` | 一批帧的 `[B,2,5]` 整数计数 |
| `CountLedgerData` | 全部已提交计数 |
| `TargetRow` | 报告中的一行逻辑记录 |

`LoadedBatch.__post_init__` 会在构造后检查形状。这是一种“让非法状态尽早失败”的设计。

## 4. tuple、list 和不可变性

代码经常把序列转换为 tuple：

```python
self._pairs = tuple(pairs)
```

list 可增删，tuple 不可增删。对于帧顺序、标签顺序这类运行期间不应变化的数据，tuple 更能表达契约。

注意：tuple 只保证容器本身不可变。如果里面放的是可变 NumPy 数组，数组内容仍然可以改变。

## 5. Path 与路径解析

`pathlib.Path` 用对象表示路径：

```python
path = Path("configs/example.json")
path.parent
path.is_file()
path.resolve()
```

项目把配置中的相对路径解析为**相对于配置文件所在目录**，不是相对于终端当前目录。例如配置文件：

```text
project/configs/example.json
```

其中：

```json
"root": "../output/example"
```

最终得到：

```text
project/output/example
```

这是理解“输出为什么不在我以为的位置”的关键。

## 6. context manager 与资源释放

源码中的：

```python
with create_backend(...) as backend:
    ...
```

会调用后端的 `__enter__`，离开 `with` 时调用 `__exit__`，最终执行 `close()`。NumPy 后端在 `close()` 中关闭线程池。

同理：

```python
with OutputLock(config.output.root):
```

保证正常结束或 Python 异常退出该代码块时删除锁文件。

`with np.load(path) as archive` 保证 `.npz` 压缩包的文件句柄及时关闭。

## 7. generator 与流式处理

函数中出现 `yield` 后，它返回的是迭代器：

```python
def _chunks(pairs, size):
    for start in range(0, len(pairs), size):
        yield tuple(pairs[start:start + size])
```

它不会一次创建全部 batch，而是在消费者请求下一项时生成。项目的 reader 也是迭代器：

```python
for loaded_batch in reader:
    result = backend.count_batch(loaded_batch)
```

这让总数据量可以很大，因为程序只保留有界数量的 batch。

## 8. NumPy ndarray 的四个核心属性

```python
array.shape   # 每个维度的长度
array.ndim    # 维度数
array.dtype   # 每个元素的数据类型
array.nbytes  # payload 字节数
```

项目规定单帧：

```text
ndim = 2
shape = [H, W]
dtype = 某种整数类型
```

读入 batch 后：

```text
shape = [B, 2, H, W]
```

维度 1 的含义：

```text
data[:, 0, :, :] = whole_scene
data[:, 1, :, :] = excavator_only
```

计数结果：

```text
counts[:, 0, :] = whole 的五个计数
counts[:, 1, :] = reference 的五个计数
```

## 9. dtype、溢出和转换

`uint16` 适合保存 semantic ID，但不适合保存任意大小的累计像素数。

项目采用：

```text
输入 semantic ID  : 通常 uint16
单帧后端计数      : uint32 / int32 中间值
跨帧求和          : uint64 或 Python int
比值              : Python float
```

为什么单帧 `uint32` 足够：

```text
720 × 1280 = 921,600 < 2^32
```

为什么汇总前要转 `uint64`：帧数增大后，所有帧像素总数可能超过 `uint32`。

NumPy 整数是固定宽度的，溢出后可能绕回。Python `int` 则可以自动扩展。源码在报告层通过 `astype(np.uint64)` 或 `int(value)` 避免小整数累计溢出。

## 10. view、copy 与连续内存

```python
flat = array.reshape(-1)
```

若数组内存连续，`reshape(-1)` 通常只是创建一个新的“视图”，不会复制 payload。

reader 中：

```python
data = np.empty([B, 2, H, W], dtype=...)
np.copyto(data[index, 0], whole)
```

则明确把每个单独加载的数组复制进连续 batch。优点：

- 后端看到统一的连续布局；
- GPU 可以一次传输整个 batch；
- Triton 可用简单线性地址公式。

代价：

- 读取期间同时存在单帧数组和 batch 数组；
- 增加一次 CPU 内存复制；
- 当前 GPU 后端还会把 pageable batch 再复制到 pinned memory。

性能优化经常是在减少这些复制，但不能以破坏布局和生命周期为代价。

## 11. `.npy` 与 `.npz`

`.npy`：

- 通常保存单个 NumPy 数组；
- 包含 header，记录 shape、dtype、存储顺序；
- 项目输入每帧一个 `.npy`。

`.npz`：

- 是多个命名 `.npy` 的容器；
- 项目每个账本 part 保存 `ordinals`、`frame_ids`、`whole_counts`、`reference_counts`；
- `np.savez` 默认不是压缩版 `np.savez_compressed`，避免额外 CPU 压缩开销。

`allow_pickle=False` 是安全和数据契约措施：只接受普通数组，不执行 pickle 对象反序列化。

## 12. mmap 只用于轻量预检

第一对文件使用：

```python
np.load(path, mmap_mode="r", allow_pickle=False)
```

memory mapping 让程序可以读取 header、shape 和 dtype，而不必立刻把整个 payload 复制进普通 ndarray。

但正式批处理没有 mmap，而是普通 `np.load`。这避免长期同时 mmap 数万个小文件，也让 batch 数据拥有明确、连续的内存布局。

## 13. JSON、CSV 与 `None`

Python：

```python
None
```

写入 JSON 是：

```json
null
```

写入 CSV 时项目使用空字符串。`allow_nan=False` 禁止生成不符合严格 JSON 的 `NaN` 或 `Infinity`。

CSV 不带强类型，读取后数字最初也是字符串；JSON 能保留数值、布尔值和 null 类型。

## 14. 异常传播

项目的总体策略是 `fail_fast`。reader 后台线程若失败，会把异常包装成 `_ReaderFailure` 放入队列，主线程取到后重新抛出。

主入口只把：

```text
OSError, RuntimeError, ValueError
```

转换为退出码 1 和简洁错误信息。pipeline 内部还用 `except BaseException` 更新失败 manifest 后重新抛出，目的是让 `KeyboardInterrupt` 等中断也尽量留下失败状态。

## 15. 复杂度记号

后文会使用：

```text
O(N)  随输入数量线性增长
O(1)  不随总帧数增长
```

项目总计算量是 `O(N×H×W)`，因为每个像素至少必须检查一次。

所谓内存 `O(batch_size)` 是说：

```text
总帧数 N 从 1 万增加到 10 万
只要 B 和队列容量不变
在途数组内存不会跟 N 一起增大
```

它不代表内存很小。`B=128` 的单 batch 已是 450 MiB，多个队列项和临时副本仍可能占数 GiB。

## 16. 本章自检

1. 为什么 `uint16` 适合 semantic ID，却不适合全数据集累计计数？
2. `reshape(-1)` 与 `copy()` 有什么潜在差别？
3. 为什么 reader 要把单帧数组复制进 `[B,2,H,W]`？
4. `with backend:` 解决了什么资源问题？
5. “内存为 O(batch_size)”为什么不等于“只占一个 batch”？

