# KRDP 下拉开关实机验证

2026-11-18，NE2210，内核 `7.3.0-sm8450+`、Plasma Mobile `6.8.2-1`、KRDP `6.8.3-1`。通过 USB SSH 安装 `bbe31ed` 的下拉项、会话配置和启动程序，并重新载入 Plasma 面板。

- 旧的用户级 USB 监听覆盖已移出 systemd 配置目录。用户服务和 KDE 自启设置分别为 `disabled` 与 `Autostart=false`。
- Plasma Mobile 的 `QuickSettingsModel` 从安装目录发现「远程桌面」项。调用该项的切换方法完成 `active → inactive → active`，显示状态对应「已开启 → 已关闭 → 已开启」。
- 最终 KRDP 为 `active`，监听 `*:3389`。Windows 对 USB 地址 `10.55.0.1:3389` 和当时的 Wi-Fi 地址 `192.168.5.18:3389` 均完成 TCP 连接。
- 本轮未重启手机或刷写分区。下拉栏实际触控、Windows RDP 身份认证及下一次登录后的状态未测。
