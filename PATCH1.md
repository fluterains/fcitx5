# Patch1：X11 候选框稳定绘制与定位

基于 Fcitx5 5.1.7。本补丁独立于 fcitx5-rime 的托盘 Patch1；需要原始拼音
预编辑时，应另行使用对应 Rime 分支，不把 Rime 插件或用户词库打入本包。

- Rime 组合期间保存输入起点，避免预编辑光标移动拖动候选框。
- 双 pixmap 准备完整帧后再提交；支持透明合成及 Shape 1.1 时，使用稳定画布，
  可见背景和鼠标区域继续实时伸缩。
- 无合成器或缺少 Shape Input 支持时，回退为内容大小窗口，避免黑条和鼠标拦截。
- 画布宽度使用最长显示器宽度，不使用多显示器拼接后的根窗口总宽度。
- 右侧越界后保留本次组合中的最大左移量；缩窄时不回弹。
- 跟踪原生焦点窗口的屏幕坐标，移动宿主窗口时平移候选锚点。

位置跟踪依赖应用上报光标矩形；同一原生窗口内部的视口滚动和预编辑光标移动
尚未单独区分，因此窗口内部滚动仍是已知限制。该补丁不改变 Wayland 合成器的
popup 定位，也不覆盖 Kimpanel 或应用自绘候选框。

## Docker 构建和 Ubuntu 打包

```sh
docker buildx build -f Dockerfile.patch1 --output type=local,dest=out/patch1 .
apt download fcitx5-modules=5.1.7-1build3 fcitx5-modules-dev=5.1.7-1build3 \
  fcitx5=5.1.7-1build3
python3 tools/package-patch1.py \
  fcitx5-modules_5.1.7-1build3_amd64.deb \
  fcitx5-modules-dev_5.1.7-1build3_amd64.deb \
  fcitx5_5.1.7-1build3_amd64.deb \
  out/patch1/libclassicui.so \
  out/patch1
python3 tests/verify-patch1-packages.py out/patch1/libclassicui.so out/patch1
```

基础包为 Ubuntu 24.04 `fcitx5`、`fcitx5-modules` 和 `fcitx5-modules-dev`
5.1.7-1build3。三个重打包文件内部版本均为 `5.1.7-1build3+patched.1`，并标记
`X-Local-Variant=patch1`。核心元包及开发包对模块的精确依赖都同步指向补丁模块，
只替换模块包中的 `libclassicui.so`。三个包版本都高于 Ubuntu 仓库包，因此正常
升级不会用同版本原版模块覆盖补丁，也不会导致开发包被移除；不再需要 apt-mark
hold。请勿安装到其他 Fcitx ABI 的发行版。

安装时必须将三个 deb 放在同一次 apt 事务中：

```sh
sudo apt install \
  ./out/fcitx5-modules_5.1.7-1build3+patched.1_amd64.deb \
  ./out/fcitx5-modules-dev_5.1.7-1build3+patched.1_amd64.deb \
  ./out/fcitx5_5.1.7-1build3+patched.1_amd64.deb
```

若从旧 Patch1 升级，先执行 `sudo apt-mark unhold fcitx5-modules`。
重启：`systemctl --user restart app-org.fcitx.Fcitx5@autostart.service`。

## 隔离测试

```sh
mkdir -p out/patch1/addons
cp out/patch1/libclassicui.so out/patch1/addons/
FCITX_ADDON_DIRS="$PWD/out/patch1/addons:/usr/lib/x86_64-linux-gnu/fcitx5" xvfb-run -a -s '-screen 0 1600x900x24' dbus-run-session -- /usr/bin/python3 tests/verify-x11-candidate.py
TEST_COMPOSITE=1 FCITX_ADDON_DIRS="$PWD/out/patch1/addons:/usr/lib/x86_64-linux-gnu/fcitx5" xvfb-run -a -s '-screen 0 1600x900x24' dbus-run-session -- /usr/bin/python3 tests/verify-x11-candidate.py
```

测试创建临时配置、最小 Rime 方案、独立 X11 和 D-Bus，不使用个人词库。
模拟合成器选择所有者以验证 32 位画布路径及透明像素，不等同于真实合成器逐帧验证。
无合成器测试验证 24 位内容窗口；两条路径均验证宿主窗口移动、预编辑光标移动不拖动候选框，以及右边缘左移后缩窄不回弹。
依赖系统 fcitx5、fcitx5-rime、python3-dbus、Xvfb、xauth、x11-utils。

## 提交组织

发布分支将两次候选窗实现及本轮边界修复整理为一个功能提交；
Docker 构建、打包、回归测试和本文档作为独立提交。保留原调试分支。
