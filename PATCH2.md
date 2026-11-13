# Patch2：候选框上下避让与预览间距

基于 Fcitx5 5.1.7，包含 Core Patch1 的全部功能。

- 候选框优先放在预览输入下方；当前显示器下方空间不足时，完整翻到上方。
- 候选框（包括主题阴影）与预览输入之间保留 8 个逻辑像素；使用候选窗
  同一 DPI 换算，96/144/192 DPI 时分别为 8/12/16 个屏幕像素。
- 避让区域包括组合起点及当前光标行，防止预览换行或光标高度延迟上报后
  与候选框重叠。横向起点固定、右侧越界后的最大左移量仍按 Patch1 处理。
- 定位使用实际绘制面板高度，不使用保留透明画布的高度。
- 两侧空间都不足以容纳候选框时，选择空间较大的一侧并限制在屏幕内；
  此时无法保证完全避开输入行。

本次只修改 X11 Classic UI。原生 Wayland 的候选窗口由合成器定位，
Kimpanel 及应用自绘候选框不受影响。应用必须提供有效光标坐标；
未提供高度时仍使用随 DPI 缩放的 10 像素估算高度。

## 构建与验证

继续使用现有 Docker 构建和打包脚本，通过参数指定新的补丁版本：

```sh
docker buildx build --progress=plain -f Dockerfile.patch1 \
  --output type=local,dest=out/patch2 .
apt download fcitx5-modules=5.1.7-1build3 fcitx5-modules-dev=5.1.7-1build3 \
  fcitx5=5.1.7-1build3
python3 tools/package-patch1.py --patch-version 2 \
  fcitx5-modules_5.1.7-1build3_amd64.deb \
  fcitx5-modules-dev_5.1.7-1build3_amd64.deb \
  fcitx5_5.1.7-1build3_amd64.deb \
  out/patch2/libclassicui.so out/patch2
python3 tests/verify-patch1-packages.py --patch-version 2 \
  out/patch2/libclassicui.so out/patch2
mkdir -p out/patch2/addons
cp out/patch2/libclassicui.so out/patch2/addons/
FCITX_ADDON_DIRS="$PWD/out/patch2/addons:/usr/lib/x86_64-linux-gnu/fcitx5" \
  /usr/bin/python3 tests/verify-x11-candidate.py
TEST_COMPOSITE=1 TEST_DPI=144 \
  FCITX_ADDON_DIRS="$PWD/out/patch2/addons:/usr/lib/x86_64-linux-gnu/fcitx5" \
  /usr/bin/python3 tests/verify-x11-candidate.py
```

隔离测试覆盖原 Patch1 的位置与画布回归，以及下方间距、底部上翻、
零高度光标、预览换行、光标高度延迟更新。使用临时主题的非零阴影检测
阴影越界，并通过 X Shape 获取实际面板高度，避免把保留画布当成面板。
`TEST_DPI` 可设为 96、144 或 192；透明画布路径采用模拟合成器选择所有者，
不等同于真实 GNOME 合成器的逐帧视觉验证。

三个核心包内部版本统一为 `5.1.7-1build3+patched.2`，互相依赖同步更新。
安装正式 Release 中的三个包后，使用桌面会话的中文环境重启 Fcitx5。
Rime 与 Configtool 的补丁版本独立，不因本次改动重新编号。
