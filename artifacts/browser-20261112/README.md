# Angelfish 安装与验证记录

日期：2026-11-12；设备：OnePlus 10 Pro NE2210；内核：`7.3.0-sm8450+`。

本记录整理自实机 USB SSH 输出；原始日志保存在本地 `logs/browser-20261112/`，不纳入 Git。

## 安装成功与启动验证

手机恢复并重新连接 USB3 后，实机确认原 pacman 进程已不存在，旧锁文件时间早于本次启动。重新检查没有包管理器占用后，移除旧锁并以本地包事务完成安装。

| 软件包 | 版本 | 架构 | `pacman -Qi` 验证方式 |
| --- | --- | --- | --- |
| angelfish | 26.08.3-1 | aarch64 | Signature |
| qt6-webengine | 6.11.3-2 | aarch64 | Signature |
| minizip | 1:1.4-1 | aarch64 | Signature |

共新增 18 个包，占用 300.18 MiB。包和签名先在电脑端下载，通过 USB SSH 传输后核对 SHA-256，再交由 pacman 验证并安装。软件包和原始日志仅保存在 `logs/`，不纳入 Git。

- `minizip 1:1.4-1` 的包元数据只要求 `glibc` 和 `zlib`，安装时现有依赖满足要求。
- Qt WebEngine 的 `.BUILDINFO` 记录 Qt Base `6.12.0-3`、Qt Declarative `6.12.0-2`、Qt WebChannel `6.12.0-1`；本机 Qt Base 为 `6.12.0-3`、Qt Declarative 为 `6.12.0-4`。
- 在 Plasma Mobile / Wayland 会话启动 Angelfish，日志显示 `isMobile` 为 `true`。
- Qt WebEngine 的页面接口报告 `url=https://example.org/`、`title=Example Domain`、`type=page`，随后普通启动的日志也记录该页面完成加载。
- 桌面入口 `org.kde.angelfish.desktop` 已安装，当前默认浏览器查询返回同一入口。
- 临时调试实例停止后，以普通模式启动的浏览器为 `active/running`，退出状态为 0；本机回环地址的临时 9223 调试监听已关闭。

未测：人手触摸、软键盘输入、GPU 加速、视频和长时间稳定性。启动日志存在 QtFeedback 模块缺失及 Kirigami/ContextDrawer 警告，交互影响尚未验证。

## 首次中断时的包管理器状态

- `pacman -S --needed --noconfirm angelfish` 解析出 18 个新增包，下载 86.22 MiB，安装占用 300.18 MiB。
- 下载过程中连接中断，重新连接后 `angelfish` 和 `qt6-webengine` 均未安装。
- 原安装进程处于 `D` 状态。未删除锁文件，也没有并行启动另一个安装事务。
- 镜像目录已将 `minizip 1:1.3.2-4` 替换为 `1:1.4-1`，恢复后还需要处理同步数据库与依赖的一致性。

## 同期内核异常

按当前启动的单调时间整理：

| 时间（秒） | 观察 |
| --- | --- |
| 8616.983 | 音频进程报告 `audio_process` crash；此前有 `negroni_lpi_try3` 音频时钟实验输出 |
| 8627.004 | ADSP 首次崩溃并进入恢复 |
| 8627.480 | `clk_nodrv_disable_unprepare` 警告，调用链经过 `rx_macro_runtime_suspend` |
| 8633.002 | 内核空指针异常，地址 `0x350`；PC 为 `clk_q6dsp_prepare`，调用链经过 `clk_core_prepare`、`rx_macro_runtime_resume`、`q6dsp_clock_dev_probe` 与 `pdr_indack_work` |
| 8646.927 | ADSP 再次崩溃并进入恢复 |
| 8830.482 | systemd-journald 停止超时 |
| 8845.980 | systemd-timesyncd watchdog 超时 |

后续进程列表中，`ufs_clk_gating_0` 工作线程、`jbd2/sda14-8`、KWin、pacman 及多个写回工作线程均处于 `D` 状态。该现象与全局时钟锁或存储路径被阻塞相符，但本次没有获取这些进程的内核栈，尚不能确定完整锁等待关系。

本次浏览器安装操作没有加载音频实验模块、修改音频时钟、重新绑定 DSP 或切换 USB 角色。这里记录同时发生的异常，不将其视为浏览器自身故障。

以上内核异常属于首次安装中断时的记录；恢复后的安装和网页加载已完成，人手交互验证仍未进行。
