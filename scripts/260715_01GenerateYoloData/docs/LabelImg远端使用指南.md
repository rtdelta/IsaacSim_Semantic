# LabelImg 远端使用指南

本文记录当前远端计算机上的 LabelImg 部署状态、启动命令、进程管理和常见问题处理方式。

## 1. 当前部署状态

远端主机通过 SSH 别名连接：

```text
isaacsim-gpufree
```

项目目录：

```text
/root/gpufree-data/repositories/260715_01GenerateYoloData
```

LabelImg 虚拟环境：

```text
/root/gpufree-data/repositories/260715_01GenerateYoloData/.venv-labelimg
```

已安装版本：

```text
LabelImg 1.8.6
PyQt5 5.15.10
```

当前远端图形显示器：

```text
DISPLAY=:20
```

当前使用的 YOLO 输出目录：

```text
/root/gpufree-data/repositories/260714_01semantic_worldModule/output/Sim_Fangshan_08_angle260720_02_60hz_10fps_1136f_pathtracing64spp_20260720_01/yolo_tooth_1_to_5_20260721_01
```

该目录包含 1,136 张 RGB 图片、1,136 个同名 YOLO TXT 和一个 `classes.txt`。类别为：

```text
tooth_1
tooth_2
tooth_3
tooth_4
tooth_5
```

## 2. 连接远端计算机

在本地 PowerShell 中执行：

```powershell
ssh -tt -o BatchMode=yes isaacsim-gpufree
```

后续命令都在远端 shell 中执行。

## 3. 最常用的前台启动方式

先定义本次使用的路径：

```bash
LABELIMG_PROJECT='/root/gpufree-data/repositories/260715_01GenerateYoloData'
YOLO_OUTPUT='/root/gpufree-data/repositories/260714_01semantic_worldModule/output/Sim_Fangshan_08_angle260720_02_60hz_10fps_1136f_pathtracing64spp_20260720_01/yolo_tooth_1_to_5_20260721_01'
```

激活虚拟环境并启动：

```bash
cd "$LABELIMG_PROJECT"
source .venv-labelimg/bin/activate
export DISPLAY=:20
labelImg "$YOLO_OUTPUT" "$YOLO_OUTPUT/classes.txt"
```

LabelImg 会在远端显示器打开，并自动载入第一张图片及其同名 TXT 标注。

前台启动时不要关闭当前终端。关闭 LabelImg 窗口后，命令会返回 shell。

## 4. 不激活虚拟环境的单行启动方式

```bash
DISPLAY=:20 \
  /root/gpufree-data/repositories/260715_01GenerateYoloData/.venv-labelimg/bin/labelImg \
  '/root/gpufree-data/repositories/260714_01semantic_worldModule/output/Sim_Fangshan_08_angle260720_02_60hz_10fps_1136f_pathtracing64spp_20260720_01/yolo_tooth_1_to_5_20260721_01' \
  '/root/gpufree-data/repositories/260714_01semantic_worldModule/output/Sim_Fangshan_08_angle260720_02_60hz_10fps_1136f_pathtracing64spp_20260720_01/yolo_tooth_1_to_5_20260721_01/classes.txt'
```

## 5. 后台启动

需要关闭 SSH 终端后继续保留 LabelImg 窗口时执行：

```bash
LABELIMG_PROJECT='/root/gpufree-data/repositories/260715_01GenerateYoloData'
YOLO_OUTPUT='/root/gpufree-data/repositories/260714_01semantic_worldModule/output/Sim_Fangshan_08_angle260720_02_60hz_10fps_1136f_pathtracing64spp_20260720_01/yolo_tooth_1_to_5_20260721_01'

nohup env DISPLAY=:20 \
  "$LABELIMG_PROJECT/.venv-labelimg/bin/labelImg" \
  "$YOLO_OUTPUT" \
  "$YOLO_OUTPUT/classes.txt" \
  > "$LABELIMG_PROJECT/labelimg.log" 2>&1 < /dev/null &
```

后台日志位置：

```text
/root/gpufree-data/repositories/260715_01GenerateYoloData/labelimg.log
```

## 6. 检查进程、窗口和日志

检查 LabelImg 进程：

```bash
ps -eo pid,ppid,stat,args | grep -E '[.]venv-labelimg/bin/labelImg'
```

也可以只列出 PID 和完整命令行：

```bash
pgrep -af '[.]venv-labelimg/bin/labelImg'
```

检查远端显示器上是否存在 LabelImg 窗口：

```bash
DISPLAY=:20 xwininfo -root -tree | grep -i 'labelImg'
```

查看最新日志：

```bash
tail -n 50 /root/gpufree-data/repositories/260715_01GenerateYoloData/labelimg.log
```

持续跟踪日志：

```bash
tail -f /root/gpufree-data/repositories/260715_01GenerateYoloData/labelimg.log
```

## 7. 停止后台 LabelImg

先查出 PID：

```bash
pgrep -af '[.]venv-labelimg/bin/labelImg'
```

确认命令行确实属于当前项目后，使用实际 PID 停止：

```bash
kill <PID>
```

再次检查：

```bash
pgrep -af '[.]venv-labelimg/bin/labelImg'
```

没有输出表示进程已结束。正常情况下不要直接使用 `kill -9`。

## 8. LabelImg 界面使用要点

1. 确认工具栏中的格式为 `YOLO`，不要保存成 Pascal VOC。
2. 启动参数已经指定图片目录和 `classes.txt`，无需再次选择目录。
3. 在文件列表中选择图片，即可查看对应的同名 TXT 框。
4. 在 `View` 菜单中启用 `Display Labels` 可以显示类别名称。
5. `A` 切换到上一张，`D` 切换到下一张。
6. `Ctrl+S` 保存当前标注。

当前是直接打开正式输出目录。执行保存会直接修改对应的 `rgb_XXXX.txt`，LabelImg 也可能更新 `classes.txt`。只查看时不要保存或拖动方框。

## 9. 打开其他 YOLO 数据目录

目标目录需要满足：

```text
目标目录/
├── image_0000.png
├── image_0000.txt
├── image_0001.png
├── image_0001.txt
└── classes.txt
```

通用命令：

```bash
source /root/gpufree-data/repositories/260715_01GenerateYoloData/.venv-labelimg/bin/activate
export DISPLAY=:20
labelImg '<YOLO目录>' '<YOLO目录>/classes.txt'
```

图片和 TXT 的基本文件名必须相同，例如 `image_0000.png` 对应 `image_0000.txt`。

## 10. 检查安装

查看 LabelImg 版本和安装位置：

```bash
/root/gpufree-data/repositories/260715_01GenerateYoloData/.venv-labelimg/bin/python \
  -m pip show labelImg
```

检查可执行入口：

```bash
test -x /root/gpufree-data/repositories/260715_01GenerateYoloData/.venv-labelimg/bin/labelImg \
  && echo 'labelImg command OK'
```

检查 Qt 是否可以连接远端显示器：

```bash
DISPLAY=:20 \
  /root/gpufree-data/repositories/260715_01GenerateYoloData/.venv-labelimg/bin/python \
  -c 'from PyQt5.QtWidgets import QApplication; app=QApplication([]); screen=app.primaryScreen(); print(screen.name(), screen.size().width(), screen.size().height())'
```

当前验证结果应包含：

```text
DP-0 1920 958
```

## 11. 首次安装或重建虚拟环境

当前环境已经安装完成，日常使用不需要重复执行本节。

```bash
cd /root/gpufree-data/repositories/260715_01GenerateYoloData

python3 -m venv --system-site-packages .venv-labelimg
source .venv-labelimg/bin/activate
python -m pip install --upgrade pip
python -m pip install 'labelImg==1.8.6'
```

`--system-site-packages` 用于复用远端系统中已经安装的 PyQt5 和 lxml。

重新安装 LabelImg 会覆盖下一节记录的兼容修补，因此重装后必须重新检查。

## 12. 当前 PyQt5 兼容修补

LabelImg 1.8.6 原始代码会把浮点数传给 Qt 的 `setValue()`，在当前 PyQt5 环境中可能报错：

```text
TypeError: setValue(self, a0: int): argument 1 has unexpected type 'float'
```

当前远端虚拟环境已经修补四处调用，将参数转换为 `int`。修补文件：

```text
/root/gpufree-data/repositories/260715_01GenerateYoloData/.venv-labelimg/lib/python3.12/site-packages/labelImg/labelImg.py
```

原始文件备份：

```text
/root/gpufree-data/repositories/260715_01GenerateYoloData/.venv-labelimg/lib/python3.12/site-packages/labelImg/labelImg.py.orig-1.8.6
```

检查修补是否仍然存在：

```bash
LABELIMG_PY='/root/gpufree-data/repositories/260715_01GenerateYoloData/.venv-labelimg/lib/python3.12/site-packages/labelImg/labelImg.py'
grep -n 'setValue(int' "$LABELIMG_PY"
```

正常应至少看到以下四类调用：

```text
bar.setValue(int(...))
self.zoom_widget.setValue(int(...))
h_bar.setValue(int(...))
v_bar.setValue(int(...))
```

如果重新安装后补丁消失，可重新执行：

```bash
LABELIMG_PY='/root/gpufree-data/repositories/260715_01GenerateYoloData/.venv-labelimg/lib/python3.12/site-packages/labelImg/labelImg.py'

sed -i \
  -e 's/bar.setValue(bar.value() + bar.singleStep() \* units)/bar.setValue(int(bar.value() + bar.singleStep() * units))/' \
  -e 's/self.zoom_widget.setValue(value)/self.zoom_widget.setValue(int(value))/' \
  -e 's/h_bar.setValue(new_h_bar_value)/h_bar.setValue(int(new_h_bar_value))/' \
  -e 's/v_bar.setValue(new_v_bar_value)/v_bar.setValue(int(new_v_bar_value))/' \
  "$LABELIMG_PY"
```

## 13. 常见问题

### 13.1 没有弹出窗口

检查显示变量：

```bash
echo "$DISPLAY"
```

本机当前应使用：

```bash
export DISPLAY=:20
```

然后检查窗口：

```bash
DISPLAY=:20 xwininfo -root -tree | grep -i 'labelImg'
```

### 13.2 日志出现 XDG_RUNTIME_DIR 提示

```text
QStandardPaths: XDG_RUNTIME_DIR not set, defaulting to '/tmp/runtime-root'
```

这是当前环境中的无害提示，不影响 LabelImg 启动和查看标注。

### 13.3 重复启动多个窗口

启动前检查：

```bash
pgrep -af '[.]venv-labelimg/bin/labelImg'
```

如果已经存在进程，优先使用现有窗口，不要重复启动。

### 13.4 图片显示但没有框

依次检查：

```bash
YOLO_OUTPUT='/root/gpufree-data/repositories/260714_01semantic_worldModule/output/Sim_Fangshan_08_angle260720_02_60hz_10fps_1136f_pathtracing64spp_20260720_01/yolo_tooth_1_to_5_20260721_01'

test -f "$YOLO_OUTPUT/rgb_0000.png" && echo 'image OK'
test -f "$YOLO_OUTPUT/rgb_0000.txt" && echo 'label OK'
cat "$YOLO_OUTPUT/classes.txt"
head "$YOLO_OUTPUT/rgb_0000.txt"
```

同时确认 LabelImg 工具栏格式为 `YOLO`。

## 14. 当前验证记录

当前部署已经验证：

- LabelImg 1.8.6 安装成功；
- Qt 成功连接远端 `DISPLAY=:20`；
- 远端显示器识别为 `DP-0 1920×958`；
- LabelImg 窗口成功打开；
- 首帧 `rgb_0000.png` 成功读取 5 个框；
- 窗口标题显示 `[1 / 1136]`；
- 兼容补丁应用后进程可以稳定运行；
- 日志中没有未处理异常。
