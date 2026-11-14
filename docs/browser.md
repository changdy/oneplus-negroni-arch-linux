# 手机浏览器

状态日期：2026-11-12。

## 选型与安装范围

当前手机使用 Arch Linux ARM（`aarch64`）与 Plasma Mobile。已补装 KDE 为手机触屏设计的 [Angelfish](https://apps.kde.org/angelfish/) `26.08.3-1`，网页引擎为 `qt6-webengine 6.11.3-2`。

2026-11-12 先给现有手机补装；2026-11-15 已加入默认软件清单，并由桌面打包检查确认包和程序存在。新完整镜像未构建、未刷入。Firefox、Chromium、Falkon 和 Epiphany 也有 ARM64 包，但本次没有安装或验证。

## 安装与启动：通过（2026-11-12 实机）

手机恢复并接回 USB3 后，通过 USB SSH 传入 18 个软件包及其配套签名文件，核对 SHA-256，再用 `pacman -U --needed --noconfirm` 完成安装。安装占用合计 300.18 MiB。`pacman -Qi` 确认 Angelfish、Qt WebEngine 和 minizip 的验证方式均为 `Signature`。

本次使用镜像中可下载的 `minizip 1:1.4-1`，其依赖由现有 `glibc`、`zlib` 满足。Qt WebEngine 的构建信息记录使用 Qt Base `6.12.0-3` 和 Qt Declarative `6.12.0-2`，与本机 Qt 6.12 运行环境对应；其自身 `6.11.3` 版本号没有阻止启动。

已验证：

- Angelfish 在现有 Plasma Mobile / Wayland 会话中启动，日志识别为移动界面。
- 网页引擎实际加载 `https://example.org/`，页面标题为 `Example Domain`。
- 桌面入口为 `/usr/share/applications/org.kde.angelfish.desktop`，启动命令为 `angelfish %u`；`xdg-settings get default-web-browser` 返回该入口。
- 验证结束后已关闭仅监听回环地址的临时调试实例，以普通模式重新打开浏览器，进程保持运行，调试端口已关闭。

启动日志仍有 QtFeedback 模块缺失、Kirigami binding loop 和 ContextDrawer 警告；本次网页加载成功，尚未确认这些警告对交互的影响。

**未测**：人手触摸操作、软键盘输入、GPU 加速、视频播放及长时间稳定性。记录与核查依据见[安装记录](../artifacts/browser-20261112/README.md)。

## 首次安装中断及恢复

通过 USB3 网络 SSH 执行 `sudo pacman -S --needed --noconfirm angelfish`。事务计划新增 18 个包，下载 86.22 MiB，安装后占用 300.18 MiB；下载期间 USB SSH 断开。

重新连接后，`pacman -Q angelfish qt6-webengine` 均报告未安装，原安装进程处于 `D` 状态。内核同时记录了音频 DSP 崩溃与恢复时的 `clk_q6dsp_prepare` 空指针异常，UFS 时钟门控、根分区日志线程、KWin 和包管理器等进程随后处于不可中断等待。现有记录不能将这个内核故障归因于浏览器安装，见[整理后的依据](../artifacts/browser-20261112/README.md)。

此外，同步数据库引用的 `minizip 1:1.3.2-4` 已无法从配置镜像下载；2026-11-12 查询镜像目录时已提供 `1:1.4-1`，后续安装采用该版本。

用户重新连接恢复后的手机时，已无 pacman 进程；旧锁文件的时间早于本次启动。安装脚本再次核对包管理器进程和锁的占用情况后，才移除上次启动遗留的锁并开始新事务。不要删除仍被安装进程持有的包管理器锁。

本次代理没有重启、刷写分区、重新绑定 USB 或音频驱动。
