# semantic_yolo_boxes

根据二维 semantic ID 数组，为配置中的每个 semantic label 计算独立像素框并输出 YOLO 标注。

模块同时发布 `<module_id>.semantic_boxes` 中间产物。该产物保留 semantic label、semantic ID、像素数量和半开像素框，供下游模块复用。

配置文件 `semantic_yolo_boxes.json` 只包含本模块的类别、标签、阈值和输出子目录。模块不负责帧发现、多进程调度、图片加载复用或错误汇总。
