# 01｜问题、数据与数学定义

## 1. Semantic ID 图到底是什么

普通 RGB 图像的一个像素通常包含红、绿、蓝三个颜色分量。semantic ID 图不是为了给人看，而是让程序知道每个像素属于哪个语义类别。

例如：

```text
0 = background
1 = tooth_1_front_3DGS
2 = tooth_2_front_3DGS
...
```

一个简化的 `3 × 4` semantic ID 图可能是：

```text
0 0 1 1
0 2 2 1
0 0 5 5
```

ID 为 `1` 的像素有 3 个，ID 为 `2` 的像素有 2 个，ID 为 `5` 的像素有 2 个。

项目输入不是彩色图片，而是 NumPy `.npy` 文件。每个文件保存一个二维整数数组：

```text
shape = [height, width]
dtype = uint16（正式数据预期）
```

`uint16` 表示每个元素占 2 字节，可表示 `0～65535`。像素 ID 是类别编号，不是颜色强度，也不是连续物理量。

## 2. 为什么要有两套图

同一个 frame ID 对应两套语义图：

```text
whole_scene / semantic_id_<frame_id>.npy
excavator_only / semantic_id_<frame_id>.npy
```

直观理解：

- `whole_scene` 是目标处于完整场景时真正看见的像素；
- `excavator_only` 是移除其他场景遮挡物后的参考像素；
- 两者必须来自逻辑上可比较的同一帧；
- 项目用像素数比值描述目标在完整场景中的相对可见程度。

如果帧 `0042` 的第一齿正面在完整场景中有 600 个像素，在参考场景中有 1000 个像素，那么：

```text
pixel_ratio = 600 / 1000 = 0.6
```

可解释为完整场景保留了参考像素量的 60%。

## 3. 严格数学定义

设：

- `f` 表示帧；
- `t` 表示五个目标标签之一；
- `W(f,t)` 表示 whole scene 中 semantic ID 为 `t` 的像素数；
- `R(f,t)` 表示 excavator-only reference 中 semantic ID 为 `t` 的像素数。

单帧、单标签比值：

```text
r(f,t) = W(f,t) / R(f,t)
```

当 `R(f,t)=0` 时，比值没有定义。项目不会写 `0`、无穷大或 `NaN`，而是：

```text
ratio = null（CSV 中为空字符串）
status = reference_missing
```

当比值大于 1：

```text
status = ratio_over_one
```

项目保留真实比值，不做截断。大于 1 不必然是程序错误，但值得调查，可能来自：

- 两次渲染或相机没有严格对齐；
- 目标姿态不同；
- mapping 或输入目录选错；
- 完整场景中的光栅化边界变化；
- 参考场景反而产生了不同遮挡；
- 上游采集不满足“reference 是最大可见基准”的假设。

## 4. 五齿集合的正确算法

设五个目标为 `t1...t5`。

一帧集合像素数：

```text
W_group(f) = Σ W(f,ti)
R_group(f) = Σ R(f,ti)
```

集合比值：

```text
r_group(f) = W_group(f) / R_group(f)
           = ΣW(f,ti) / ΣR(f,ti)
```

它**不是**：

```text
(r(f,t1) + ... + r(f,t5)) / 5
```

原因是每个齿的参考像素数不同。正确集合比值让每个齿按其参考像素数自然加权。

例子：

```text
齿 1：whole=10, reference=100, ratio=0.1
齿 2：whole=1,  reference=1,   ratio=1.0
```

两个比值的简单平均：

```text
(0.1 + 1.0) / 2 = 0.55
```

正确集合比值：

```text
(10 + 1) / (100 + 1) = 11/101 ≈ 0.10891
```

两者相差很大。像素量为 100 的齿显然不应与像素量为 1 的齿拥有相同权重。

## 5. 为什么五个计数可以直接相加

项目要求五个标签解析为五个不同 semantic ID。一个 semantic ID 图中的单个像素只有一个整数 ID，因此一个像素不可能同时属于两个目标 ID。

所以五个集合是互斥的：

```text
count(ID=1 or ID=2 or ... or ID=5)
= count(ID=1) + ... + count(ID=5)
```

源码还检查集合计数不能超过一帧总像素数。若超过，说明至少有一项前提遭到破坏，例如后端输出错误或目标 ID 不再互异。

## 6. 数据集级指标

对某个 target，数据集主汇总比值为：

```text
aggregate_ratio
= Σ_f W(f,t) / Σ_f R(f,t)
```

项目还计算：

```text
mean_frame_ratio   = 所有有定义的单帧 ratio 的算术平均
median_frame_ratio = 单帧 ratio 中位数
min/max            = 单帧 ratio 极值
```

`aggregate_ratio` 与 `mean_frame_ratio` 表达不同问题：

- `aggregate_ratio`：把所有帧的像素池合并后，整体比例是多少；
- `mean_frame_ratio`：把每帧视为同等重要，典型帧比例是多少。

如果没有 `reference=0` 且 `whole>0` 的帧，aggregate ratio 可以看作按 reference 像素数加权的单帧平均。若存在 `reference=0, whole>0`，这些帧没有单帧 ratio，却仍会增加数据集 numerator，因此不能再简单解释成“有效帧 ratio 的加权平均”。

## 7. 手算完整示例

假设一帧有 `2 × 4 = 8` 个像素，五个目标 ID 为 `1～5`：

```text
whole:
1 1 2 0
3 4 5 0

reference:
1 2 2 0
3 5 5 0
```

计数：

| ID | whole | reference | ratio | status |
|---:|---:|---:|---:|---|
| 1 | 2 | 1 | 2.0 | `ratio_over_one` |
| 2 | 1 | 2 | 0.5 | `valid` |
| 3 | 1 | 1 | 1.0 | `valid` |
| 4 | 1 | 0 | null | `reference_missing` |
| 5 | 1 | 2 | 0.5 | `valid` |
| group | 6 | 6 | 1.0 | `valid` |

注意：ID 4 的分母为零不会阻止 group ratio 有定义，因为 group denominator 是五个 reference count 的总和。

## 8. 项目的输入正确性契约

要让上面的数学有意义，代码必须保护这些前提：

1. 两个目录的 frame ID 集合完全相同；
2. 每对图像 shape 和 dtype 相同；
3. 所有帧都与第一帧确定的全局 shape/dtype 一致；
4. 数组是二维整数数组；
5. mapping 中存在全部五个标签；
6. 五个标签映射到互不相同的非负 ID；
7. 后端只返回整数计数；
8. 单目标计数和五目标之和不超过一帧像素数；
9. 账本中的 ordinal 连续、frame ID 无重复；
10. 报告只从同一份整数账本生成。

这些不只是“防御式编程”。缺少其中任何一项，都可能得到格式正常但语义错误的 CSV。

## 9. 本章自检

不看上文回答：

1. 为什么 group ratio 不能取五个 ratio 的平均？
2. `reference=0` 时为什么不能写 0？
3. `ratio>1` 为什么保留而不截断？
4. aggregate ratio 和 mean frame ratio 各自回答什么问题？
5. 为什么五个 ID 的计数总和理论上不超过总像素数？

答不清时，先回到手算示例，不要急着读 GPU kernel。

