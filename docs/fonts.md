# 中文字体

状态日期：2026-11-12。

手机此前安装了 `noto-fonts` 和 `noto-fonts-emoji`，但 `fc-list :lang=zh` 没有结果，普通字体不含中文。已通过 USB SSH 安装官方仓库的 [`noto-fonts-cjk`](https://archlinuxarm.org/packages/aarch64/noto-fonts-cjk)（`20240730-1`），补齐简繁中文等 CJK 字形，并刷新字体缓存。

## 已有系统补装

在手机上执行：

```sh
sudo pacman -S --needed noto-fonts-cjk
fc-cache -f
fc-list :lang=zh-cn family
fc-match 'sans-serif:lang=zh-cn'
```

已打开的应用如果仍显示方框，关闭后重新打开，使其重新加载字体。系统语言仍为 `en_US.UTF-8`；安装中文字形不需要切换界面语言，也不需要重启手机。

## 构建集成

字体包已加入 [config/packages/common-tools.txt](../config/packages/common-tools.txt)。全新构建会安装；已有镜像续建时清单变化会触发 [install-common-tools-image.sh](../scripts/install-common-tools-image.sh)，安装后重新封装，见 [构建集成说明](build-integration.md)。本次未构建新的完整镜像。

## 实机验证

2026-11-12，OnePlus 10 Pro NE2210、内核 `7.3.0-sm8450+`：

- `pacman -Qkk noto-fonts-cjk`：21 个文件，0 个被修改。
- `fc-list` 已列出 Noto Sans/Serif/Mono CJK 字族，默认 sans-serif、serif、monospace 均可匹配中文字体。
- 在手机上以 Pango 渲染简体、繁体、标点与中英文混排，序列化结果 `unknown-glyphs = 0`。
- 在手机上用 Qt Quick 的 offscreen/software 后端渲染三类通用字体，样图经目视检查，中文完整可读。

整理后的结果见 [verification.json](../artifacts/fonts-20261112/verification.json)，样图为 [Qt](../artifacts/fonts-20261112/qt-fonts.png) 和 [Pango](../artifacts/fonts-20261112/pango.png)。原始日志在本地 `logs/fonts-20261112/`，不纳入 Git。

以上是实机生成样图的验证；已有桌面应用逐个重新打开后的显示、物理屏幕显示、新完整镜像安装均未测。系统 fontconfig 当前会选择包含中文字形的 CJK KR 变体，本次未调整地区字形偏好。
