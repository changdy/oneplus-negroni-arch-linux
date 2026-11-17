# RTC 硬件时钟

## NE2210 实机结论（2026-11-17）

PMK8350 的 `rtc-pm8xxx` 可读，原始秒数在关机和重启之间持续递增。当前驱动把原始秒数解释为 Unix 时间，因此开机先显示 1970 年；NTP 后来将系统时间校准到 2026 年，RTC 原始读数仍在 1970 年。设备没有 EFI 变量目录。`CONFIG_RTC_HCTOSYS=y` 与 `CONFIG_RTC_SYSTOHC=y` 均已启用，但驱动没有可写的时间偏移量存储时，`set_time` 返回 `-ENODEV`。[原始诊断](../artifacts/rtc-20261117/README.md)。

曾按主线 `rtc-pm8xxx` 的 NVMEM offset 机制，在 PMK8350 SDAM1 `0x7c–0x7f` 声明 offset。经用户同意写入 `vendor_boot_b` 并重启后，RTC 能读取该位置，但系统尝试写入时 PMIC 返回 `-EPERM`，约 3 分钟出现数百条错误。对同一 SDAM 的 `0x70` 及另一块未占用 SDAM 的 `0x7c` 做同值写入测试也都返回 `-EPERM`，说明这不是单个地址的越界或权限位问题。先在运行中解绑实验驱动，随后经用户同意写回原 `vendor_boot_b` 并重启；RTC 驱动恢复，启动日志没有新的 SDAM 写入错误。失败的设备树改动保存在[实验记录](../artifacts/rtc-20261117/README.md)，默认构建不使用它。原始 PMIC 计数器没有被修改。

## 文件持久化偏移方案

`negroni-rtc-clock` 将 PMIC 原始秒数与 NTP 校准后的 UTC 相减，把偏移量原子写入 `/var/lib/negroni-rtc/state.json`。下次开机时，`negroni-rtc-restore.service` 在 `systemd-timesyncd` 之前读取原始秒数和偏移量；只有推算时间晚于当前系统时间时才向前设置系统时钟。若 PMIC 计数器回退，服务拒绝旧偏移量。这样断网开机也能利用硬件计数器经过的时间；PMIC 无需写入，系统时间不会被旧文件倒拨。

`negroni-rtc-sync.path` 等待 `systemd-timesyncd` 首次成功校时产生 `/run/systemd/timesync/synchronized`，再触发一次保存。没有网络时，path 单元不会阻塞启动。全新 rootfs 由 `finalize-rootfs.sh` 安装，已有镜像由 `build.sh` 按源文件指纹补装；封装前检查脚本、systemd 单元、启用链接和 DTB 中不存在受保护的 SDAM offset 写入路径。用户可运行 `negroni-rtc-clock show` 查看按偏移量换算的 UTC。`hwclock --show` 仍显示原始 PMIC 计数值，不能把它当成换算后的墙上时间。

文件系统偏移量必须在至少一次可靠 NTP 校时后生成。若电池完全断开导致 PMIC 计数器归零，旧偏移量会被拒绝，需重新联网校时。原分区已回滚，当前 rootfs 已安装并在 NTP 同步后成功保存偏移量。一次经用户同意的重启显示：恢复服务在启动第 10 秒把系统 UTC 设为 2026 年，早于 NTP 服务启动，且检查时没有 NTP 同步标记；详见[实验记录](../artifacts/rtc-20261117/README.md)。新完整镜像尚未构建和刷入；完整断网启动、完全断电启动、闹钟唤醒仍需分别验收。任何再次刷写分区或重启手机，均按 [AGENTS.md](../AGENTS.md) 先征得用户同意。
