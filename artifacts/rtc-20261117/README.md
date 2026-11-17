# NE2210 RTC 实验与回退记录（2026-11-17）

## 起点

USB `10.55.0.1` SSH 只读检查：`rtc-pm8xxx c400000.spmi:pmic@0:rtc@6100` 注册为 `rtc0`，`hctosys=1`，原始秒数持续递增。开机第 9.77 秒内核用 67,209 秒设置系统时间为 `1970-01-01T18:40:09Z`；当 NTP 已同步到 `2026-11-17T06:29:13Z` 时，RTC 仍显示 `1970-01-01 19:35:58`、`since_epoch=70558`。设备没有 `/sys/firmware/efi/efivars`。原厂 DTBO 候选 0/11 的 RTC 节点不含 offset；SDAM1 `sdam@7000` 没有设备树消费者。

主线 `rtc-pm8xxx` 驱动在没有 `allow-set-time` 时仅通过 NVMEM 或 UEFI offset 修改所报告的时间；两者都没有时，`set_time` 返回 `-ENODEV`。实验采用[此设备树改动](failed-sdam-offset.md)，声明 SDAM1 `0x7c–0x7f` 为 offset；PMIC 原始计数器保持不变。改动已从默认内核树移除，保留在此以便复现，不进入下一次镜像。

## 备份、刷入和结果

刷写前 `qbootctl` 显示当前槽 `_b`，B 槽 Active / Successful / Bootable 均为 1。完整 `vendor_boot_b`（201,326,592 字节）备份在手机 `/home/oneplus/rtc-vendor-boot-b-backup-20261117.img` 和本机忽略目录 `logs/rtc-vendor-boot-b-backup-20261117.img`；两份 SHA-256 都是 `2714b634cc0fadbc96378c9c71f92851c41357a92ed4635476389e3b65473703`。候选 `vendor_boot-rtc.img` 的 SHA-256 为 `70c5cf15f635875dfec103ba41eadedc97ceaa009778a83e56901dc19672098f`，解包 DTB 与实验内核编译产物逐字节相同，镜像头除 DTB 大小外与原镜像相同。

用户明确同意后，于 14:57 写入 `vendor_boot_b`；写入后前 184,320 字节回读 SHA-256 与候选一致，分区整体 SHA-256 为 `c0ffdd438f7cccc7742e8e12826c753736b41b8e32244e54bd9a1cfd68ea3f17`，随后重启。新 boot ID 为 `9d0bd512-d809-45c2-a3aa-5a9c7afea8de`，内核 `7.3.0-sm8450+`，USB SSH 恢复，系统无失败单元。NTP 同步后 RTC 仍是 1970 年，内核报 `qcom,spmi-sdam ... nvram@7000: Failed to write SDAM offset 0x7c len=4, rc=-1`；约第 3 分钟累计 745 条同类错误。

试卸载 `rtc_pm8xxx` 因模块使用中失败，随后只解绑该 RTC 设备，`/sys/class/rtc/rtc0` 消失，重复写入停止；系统 UTC 仍由 NTP 保持。以 root 对相同 SDAM1 的 `0x7c`（`00000000`）和 `0x70`（`00000100`），及原厂 DT 没有消费者的 SDAM23 `0x7c`（`00000000`），分别尝试写回完全相同的 4 字节，三次均直接返回 `EPERM`，读数未变。没有改写 PMIC RTC 计数器、SDAM 数据或其他分区。原始镜像、运行 FDT 与日志留在忽略目录，不纳入 Git。

## 回退与后续

用户再次同意后，于 15:18 核对当前 B 槽仍为 Active / Successful / Bootable，核对候选分区整体哈希和完整原分区备份哈希，再把 201,326,592 字节原备份写回 `vendor_boot_b`。全分区回读 SHA-256 与备份一致：`2714b634cc0fadbc96378c9c71f92851c41357a92ed4635476389e3b65473703`。获同意重启后，boot ID 为 `cc6293f6-a24f-4203-b475-86a0ed406b29`，`rtc0` 重新注册，原始读数继续递增，本次启动日志无 `Failed to write SDAM offset`。内核源码已退回已验证提交 `b3a55871a46d9148c77a7dbfbefec24138216a5d`，恢复 bundle 同步退回。

15:20 通过 USB SSH 将[文件持久化偏移方案](../../docs/rtc.md)的脚本和三个 systemd 单元安装到当前 rootfs；`systemd-analyze verify` 通过，恢复服务与同步 path 均为 enabled。NTP 标记出现后，保存服务成功写入 `/var/lib/negroni-rtc/state.json`：`raw_at_sync=73609`、`unix_at_sync=1794900004`、`offset_seconds=1794826395`。`negroni-rtc-clock show` 为 `2026-11-17T07:20:11+00:00`，与当时系统 UTC 一致；原始 RTC 仍为 1970 年，未写入受保护的 PMIC SDAM。

15:21 获用户同意再次重启，boot ID 为 `7479d6fb-0f18-48da-8c94-22a05e9f57c9`。恢复服务于启动第 4.74 秒开始，在第 10.44 秒从 PMIC 计数器推算并设置 `2026-11-17T07:21:47+00:00`；`systemd-timesyncd` 于第 10.79 秒才启动。检查时 NTP 同步标记仍不存在，因而这次恢复不依赖网络校时。服务因启动事务重复运行一次，第二次检测到时钟已领先，没有回拨；随后加上 `RemainAfterExit=yes`，在手机重新安装并通过 `systemd-analyze verify`，防止后续重复执行。该单元调整尚未经过另一次重启。随后 NTP 同步正常，换算 UTC 与系统 UTC 一致，`systemctl --failed` 为空，启动日志没有 SDAM 写入错误；`qbootctl` 显示 B 槽仍为 Active / Successful / Bootable。完整断网启动、完全断电和闹钟唤醒未测；新完整镜像尚未构建或刷入。
