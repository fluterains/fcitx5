# Patch3：零高度光标的预览避让

包含 Core Patch2 的全部功能，修复屏幕底部上翻时仍可能遮住预览输入的问题。

## 原因与处理

XIM 的 spot location 可以是文字基线；本项目 XIM frontend 将它转换为
`height=0` 的光标位置。部分客户端也会用无高度的点表示文字底部。
基线语义参见 [Xlib 规范的 Spot Location](https://www.x.org/releases/X11R7.6/doc/libX11/specs/libX11/libX11.pdf)。
Patch2 只在这个点的下方估计高度，上翻时却把这个点当作文字顶部，
候选框因而可能占据实际文字所在的区域。

有完整高度的光标矩形继续按实际矩形避让。对于没有高度的点，
现在还在它上方保护一段文字区域，取 40 个逻辑像素与当前候选字体行高的较大值，
并沿用 Patch2 的上下间距和 DPI 换算。下方原有的估算范围保留。
未提供高度时无法得知应用的真实字体大小，这仍是保守估计；特别大的应用字体
可能超出估计范围，需结合实际客户端的光标上报数据进一步处理。

增加 `classicui` debug 日志，输出前端、光标与锚点矩形、面板高度及最终位置，
不输出预览字符串或候选文字。默认日志级别下不启用。

## 验证

`tests/verify-x11-candidate.py` 在原有隔离测试后增加真实 GTK 输入框，
通过 XIM 输入，使用 GTK/Pango 返回的实际预览文字边界验证避让，
而不是仅根据候选框自身的估算规则断言位置。GTK 测试只在隔离 Xvfb 会话内
启用 XIM 的 On The Spot，不修改用户配置。

旧 Patch2 在该测试中，候选框底部为 889，实际预览行上边缘为 868，
两者重叠 21 个屏幕像素（96 DPI）。测试矩阵覆盖 96/144/192 DPI，
以及普通窗口与透明画布两条路径。

测试额外需要 `python3-gi`、GTK 3 / GdkX11 introspection、GTK XIM 模块及
`libXtst6`。运行方式与 `PATCH2.md` 相同，将输出目录替换为 `out/patch3`。
编译仍使用 `Dockerfile.patch1`，打包与包验证使用 `--patch-version 3`。

发布包版本统一为 `5.1.7-1build3+patched.3`。Rime 和 Configtool 版本独立。
本次依旧只修改 X11 Classic UI；原生 Wayland 及外部候选 UI 不受影响。
