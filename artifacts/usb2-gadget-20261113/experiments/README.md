# 已否证的 USB2 LPM 实验

2026-11-13 曾在运行中的 `vendor_boot_b` 加入 `snps,usb2-gadget-lpm-disable`。重启后属性存在、DCFG LPMCap 清零，USB3 正常，但换到 USB2 口依旧失败。因此该属性并未解决本机 USB2 问题；后续 datapath override 释放和同为 device 时的 PHY 恢复才取得拔插、换口和传输结果，见 [USB 调试](../../../docs/usb-debug.md)。

本目录保存当时的内核补丁及只操作本地文件的 `inject-lpm-dtb.py`，从原来的 `logs/usb-debug-20261112/` 提炼。它们不接入镜像构建或手机自动执行。

脚本保留当日接口：复制到独立的本地日志目录，把自己备份的 `vendor_boot_b-original-20261113.img` 放在旁边后执行，输出 `vendor_boot_b-lpm.img` 和 JSON 报告。仅支持 vendor_boot v4、4096 字节页、空 vendor ramdisk 的布局，校验原 DT 属性逐字节不变、只多一个布尔属性、镜像头只改 dtb_size；不适合直接套用到其他镜像格式。原始镜像和输出均不入 Git。

脚本不会刷机。任何实机刷写另行备份、核对 SHA-256、槽位和授权；回滚使用对应刷前分区备份。LPM 属性移除之后的表现、完全断电、OTG/PD Hub 与真正深度睡眠仍需另测，不应因这份实验归档而改变当前默认镜像。
