# tooth_group_yolo

消费上游 `SemanticBoxSet` 中间产物，根据两个端部斗齿框生成一个集合框。

集合框规则：

- `left`：画面左侧端部框的左边；
- `right`：画面右侧端部框的右边；
- `top`：两个端部框较高的上边；
- `bottom`：两个端部框较低的下边。

`endpoint_selector.type` 支持：

- `semantic_labels`：配置两个物理端部 semantic label；
- `image_extrema`：在配置候选标签中动态选择画面最左和最右框。

`missing_policy` 支持 `exclude_frame`、`empty_label`、`error` 和 `visible_extrema`。默认推荐 `exclude_frame`，避免无法构造集合框的图片被错误地作为负样本。
