# PMK8350 RTC 直接写入权限实验（2026-11-17）

## 目的与边界

SDAM offset 写入返回 `EPERM`，不能直接证明 RTC 外设的寄存器也不可写。内核 `rtc-pm8xxx` 在设备树设置 `allow-set-time` 后，会先改闹钟和 RTC 控制寄存器，再把新秒数写入 `0x6140–0x6143`。NE2210 原厂 DTBO 候选 0/11 和当前设备树均没有 `allow-set-time`。本实验只对 RTC 控制寄存器 `0x6146` 发起一次**写回原值**的权限探测，不设置日期、闹钟或计数器，不刷分区、不重启。

实验源码是 [negroni_rtc_write_probe.c](negroni_rtc_write_probe.c) 和 [Makefile](Makefile)，不接入默认构建或镜像。模块硬编码设备名、`qcom,pmk8350-rtc` compatible、地址 `0x6146` 和预期控制值 `0x80`；任何前置条件不满足时不会写。加载时还必须显式传入 `confirm_same_value_write=1`。源码本身未提供更改计数器的路径。

## 构建与防误触验证

在 WSL 内核树 `b3a55871a46d9148c77a7dbfbefec24138216a5d`，以 `O=output ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- M=<实验目录> modules` 构建。`modinfo` 显示 `7.3.0-sm8450+ SMP preempt mod_unload aarch64`，与手机现用 `rtc_pm8xxx` 模块的 vermagic 相同。实测模块 SHA-256：`0a40e716a887fb3abbbdffc43b197c74e6db854c396dcca092fa5f107f577fc0`，手机上的文件哈希已核对。未传确认参数时，`insmod` 返回 `EPERM`，内核记录 `confirmation absent; no PMIC write attempted`。

经用户单独同意后，在 USB SSH 上以 root 运行已校验脚本：先确认模块哈希、`/sys/kernel/debug/regmap/0-00/registers` 中 `6146: 80` 和 `/sys/class/rtc/rtc0/since_epoch`；然后只执行一次 `insmod ... confirm_same_value_write=1`，最后核对控制值、秒数和模块卸载状态。该脚本与原始输出保存在忽略目录 `logs/rtc-direct-probe-20261117/`，不纳入 Git。

## 实机结果

15:43:33 CST，写入前 `RTC_CTRL=0x80`、原始秒数 `75019`，系统 UTC 为 `2026-11-17T07:43:33Z`。加载实验模块返回 `Operation not permitted`，内核日志明确记录：

```text
spmi spmi-0: disallowed SPMI write to sid=0, addr=0x6146
same-value RTC_CTRL write returned -1
```

写入后 `RTC_CTRL` 仍为 `0x80`，秒数仍持续递增（复核时从 `75074` 到 `75076`），`negroni-rtc-clock show` 与系统 UTC 相同；实验模块没有留在内核中，`systemctl --failed` 为空。未改动 PMIC 计数器、闹钟、设备树、分区或启动状态，无需回滚。若重复实验后模块意外仍在，先用 `rmmod negroni_rtc_write_probe` 卸载并检查 RTC 读数；任何异常都停止写入，刷写或重启前按 [AGENTS.md](../../../AGENTS.md) 征得同意。

内核 `spmi-pmic-arb.c` 在当前执行环境不是该 SPMI 外设的写拥有者时返回 `EPERM`。这次错误来自该仲裁层，位于 RTC 驱动的寄存器写入之前。**在当前固件的 SPMI 权限配置下，给设备树加 `allow-set-time` 不会让 Linux 获得 RTC 外设写权限。** 若要让 PMIC 的原始 RTC 本身显示真实日期，需要找到受支持的固件设时接口或由固件改变外设写拥有权；本机目前均未证实。现有 rootfs 文件偏移方案仍是已验证的开机时间恢复路径。
