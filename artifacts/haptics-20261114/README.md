# NE2210 振动反馈调试（2026-11-14）

本轮通过 USB SSH 操作，使用当前主线 7.3 内核的模块，没有加载原厂 5.10 模块，没有刷写分区。原始日志在忽略的 `logs/haptics-20261114/`。

## 初始状态与可复现故障

- `CONFIG_INPUT_QCOM_HV_HAPTICS=m`，模块已安装，但没有加载；设备树的 `qcom,hv-haptics` 节点未绑定 driver。
- `modinfo -F alias qcom-hv-haptics` 为空，源码未导出 OF 匹配表。
- 手动加载后生成 `qcom-hv-haptics` 输入设备，PMIC 硬件类型为 2，读取到 5882 µs 标称周期和 5864 µs 闭环周期。
- 内核通用 FF 层虽然因 `FF_PERIODIC` 自动显示 rumble 能力，驱动只接受 `FF_CUSTOM` 周期效果；标准 rumble 上传实际返回 `EINVAL`。
- 原代码在上传常量效果时启动停止计时器，重播同一个效果不会重置计时；`playback(..., 0)` 未实际停止播放。手机尚未安装 Plasma 所调用的 `feedbackd`。

原安装模块已备份到手机 `~/haptics-backup-20261114/qcom-hv-haptics.ko`，SHA-256 为 `47556a9945d3c8871e6a4dd4bf242c8e9173d9beafc858d31fc5d14560216b3a`。

## 首次实验与修正

首次热安装版本成功通过 OF 设备事件自动加载，但播放工作任务在持有 `play.lock` 时调用 `haptics_wait_hboost_ready()`；该函数自己也会获取同一把锁，导致振动 worker 阻塞，关闭 evdev 的测试进程随之等待。其他子系统和 USB SSH 当时仍可用。

已通过 worker 的内核栈确认调用位置。修正版将升压等待移到锁外，获取播放锁后再次读取停止请求；新增回归保留升压等待函数的真实锁行为，首次版本触发断言、修正版通过。

同时修正原驱动卸载时遗留测试 proc 节点的问题，避免重新加载出现重复注册及遗留回调。阻塞的旧模块不能安全卸载，修正版先安装到磁盘；用户明确同意重启一次后才发出重启请求。重启前只读核对当前 B 槽 Active / Successful / Bootable 均为 1，未切槽或改成功标记。

当前修正版模块 SHA-256：`bf501cc39b99510e2b77c8d86992eab620d1c2f3e24d6dc419427a468684353a`。

用户随后按键重新开机，USB SSH 恢复；上一次日志已进入 `System Shutdown`，pstore 为空，没有取得 kernel panic 证据。该现象与旧阻塞 worker 拖住关机过程相符，不能把屏幕上的红色状态行直接判为启动崩溃。

内核修复为 `f2fc0916795112d8e10f350bf1b27b053bef069e`，由 `patches/linux/local-7.3.bundle` 保存，只涉及振动驱动。

## 验证边界

- ARM64 独立模块编译通过，使用现有完整内核构建的导出符号表；新模块包含三个 compatible 的 OF 自动加载别名。
- 真实 FF 回调的主机回归及 `bash scripts/check.sh` 通过。
- 按键开机后自动加载通过，运行模块 build-id note 的 SHA-256 与构建产物一致：`a5fb3d4c81430a50ea2e36c820b5d4fb39b299ee097e2938c458a82e09114fb7`。
- 用户确认 150 ms、50% 强度的三次短振清楚。
- 上传后等待 300 ms 再播放、80 ms 自动停止、同一效果 20 次重复播放均通过。内核寄存器操作日志间隔：20 ms 请求为 23.463–27.747 ms，80 ms 请求为 83.828–85.335 ms；这是日志时序，未测电气波形。
- 600 ms 效果在 70 ms 时主动停止，日志间隔为 71.399 ms，没有等待原定时长。
- udev 的 `FEEDBACKD_TYPE=vibra` / `uaccess` 生效；普通用户调用 Plasma 同一 `org.sigxcpu.Feedback.Haptic.Vibrate` 接口及连续 10 次请求均返回 true；`fbcli` 的 `button-pressed` 事件通过。
- 修正版模块卸载、三个厂商 proc 节点移除、设备事件自动重载及重载后的桌面 D-Bus 调用通过；未出现新的驱动 WARNING / Oops，系统失败服务为 0。
- 用户同意最后一次正常重启后，`systemctl reboot` 顺利完成，无需按键恢复；开机后模块自动加载、普通用户 D-Bus 短振、B 槽 Active / Successful / Bootable 均为 1，系统失败服务为 0。
- 全新完整镜像、深度睡眠、厂商 RichTap、SoundWire 同步及长时间多客户端压力未测。

整理后的哈希、能力及启停日志时序见 [evidence.json](evidence.json)，不包含设备标识或原始日志。

使用方式、构建接入和诊断命令见[振动反馈说明](../../docs/haptics.md)。
