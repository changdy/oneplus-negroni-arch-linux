# USB2 gadget：充电检测 datapath override 残留

日期：2026-11-13，21:27–22:03（UTC+8）。实机 OnePlus 10 Pro NE2210，内核 `7.3.0-sm8450+`，保留此前的 LPM 实验属性。用户配合在同一台电脑的 USB3 / USB2 口换线。

## 当前结果（22 时驱动部署后）

**驱动修复已刷入 b 槽并重启，USB2 可自动连接和拔插恢复。** 内核提交 `f8350cc1e221ce4cb22beec8a9eeae7a5ad77a2d`，运行 `7.3.0-sm8450+ #4`。USB2 随启动自动 high-speed，连续 3 次同口拔插均自动恢复；换到 USB3 自动 super-speed，换回 USB2 自动 high-speed。USB2 双向各 64 MiB SHA-256 一致，整个驱动验收没有运行恢复脚本。详见 [驱动验证数据](driver-evidence.json) 和 [构建报告](driver-build.json)。

下面的 21 时对照记录解释了修复依据。

## 修复前的运行时对照（21 时）

**USB2 可以工作。** 在失败的 USB2 连接中，只清除 HS PHY `PHY_CFG0`（`0x088e3094`）bit 0 `UTMI_PHY_DATAPATH_CTRL_OVERRIDE_EN`，即可从 `not attached` 恢复到 `configured / high-speed`，NCM USB SSH 恢复。上下行各 32 MiB 文件的 SHA-256 一致。未重启、未刷写、未写 USB role、未重绑 UDC。

**重新插线会复发。** 拔插同一个 USB2 口后，`PHY_CFG0` 低字节又变成 `0x01`；运行本轮恢复脚本再次清位，枚举及传输再次通过。这是驱动部署前的运行时规避；22 时已由新内核自动处理。

## 对照与证据

| 对照 | 实测结果 |
| --- | --- |
| USB3 → USB2，只采集状态 | USB role / DWC3 均保持 device，configfs `UDC=a600000.usb`、`usb0` 仍存在，但未枚举、链路 Suspend；本轮无 `enable otg` / xHCI 注册 |
| 只启用 `GCC_EUSB3_0_CLKREF_EN` bit 0 | 硬件读回开启，仍未枚举 |
| 随后清除 PHY datapath override | 约 0.25 秒内枚举为 high-speed |
| 已配置后把参考时钟还原为关闭 | USB2 SSH 保持可用 |
| 同口拔插，参考时钟保持关闭，只清除 datapath override | 约 0.23 秒内配置完成；其后才进行的参考时钟写入并非本次成功的原因 |
| 再次同口拔插，使用仓库恢复脚本，仅清除 datapath override | 21:45:33 实测成功，参考时钟始终为原值 `0x80000000`；上下行各 32 MiB 哈希一致 |

失败时 PHY 低字节：`UTMI_CTRL0=0x09`（OPMODE_NONDRIVING）、`HS_PHY_CTRL2=0x0e`、`PHY_CFG0=0x01`；OTG boost / OVP 的 GPIO64 / GPIO57 都为 low。成功后只需 `PHY_CFG0=0`，其他 PHY 配置无需更改。32 位 PHY 寄存器读数会重复低字节，例如 `0x01010101`，清 bit 0 后硬件读回 `0x00000000`。

原厂 [phy-msm-snps-hs.c](https://github.com/OnePlusOSS/android_kernel_oneplus_sm8450/blob/oneplus/sm8450_v_15.0.0_oneplus_10_pro/drivers/usb/phy/phy-msm-snps-hs.c) 的 `msm_hsphy_put_phy_in_non_driving_mode()` 用同一组位使 DP/DM 进入充电检测高阻态，并在退出时清除 datapath override。**本轮寄存器状态与该模式一致；究竟由 boot firmware、ADSP/充电固件还是其他路径重新写入，尚未直接追踪，不能据此认定写入者。**

早前 16:44 确实记录过 OTG host 的短暂切换，但 21 时的失败与恢复均不需要发生 host 切换，故它不能解释全部 USB2 故障；“gadget 未重绑所以 USB2 失效”也不是本轮原因。实际接收 OTG/CID 通知的是 `oplus_battmgr.c`，`qcom_battmgr` 提供公共协议层。

整理后的数值与传输结果见 [runtime-evidence.json](runtime-evidence.json)。原始 kernel / uevent / 20 ms 状态采样及寄存器快照在忽略的 `logs/usb2-role-20261113/`。顺序采样不是原子快照，无法排除短于 20 ms 的状态变化；kernel/uevent 日志用于交叉核对。

## 临时恢复

手机脚本：[negroni-usb2-recover.py](../../scripts/negroni-usb2-recover.py)。本轮已复制到手机 `/tmp/negroni-usb2-recover.py`；没有安装服务或设置自动启动。USB2 故障时，通过 Wi-Fi 备援登录手机运行：

```sh
sudo python3 /tmp/negroni-usb2-recover.py       # 只查看状态
sudo python3 /tmp/negroni-usb2-recover.py --apply
```

脚本要求 `oplus,negroni`、Type-C data role 为 device、有连接伙伴、DWC3 为 device、UDC 已绑定且 `not attached`；已配置时不写寄存器，host、未绑定或状态变化时拒绝写入。它只清除 PHY_CFG0 bit 0，并等待最多 15 秒确认配置完成。保持物理连接不变后执行；用户空间的检查不能与内核角色切换形成原子操作。

只读采集脚本：[negroni-usb-observe.py](../../scripts/negroni-usb-observe.py)，可通过临时 systemd unit 运行以跨越 USB SSH 中断，不会修改角色、绑定或寄存器。

## 驱动修复与验证边界

[usb2-datapath-candidate.patch](usb2-datapath-candidate.patch) 已提交到内核、纳入父仓库源码恢复 bundle，并构建/刷入 `boot_b`（沿用早期文件名）：

- PHY 初始化完成时同时清除 common / datapath override；已初始化 PHY 在重新设置 USB host/device 模式时释放 datapath override。
- Qualcomm DWC3 在控制器已经处于 device 模式时，也为新的 DEVICE 请求重新设置 USB2 PHY 模式，并用 DWC3 mutex 串行化异步角色切换。原来的同角色早退会跳过 PHY 恢复。

已通过 ARM64 的两个驱动对象及完整 Image.gz 构建、boot v4 封装回读核对、`checkpatch.pl --strict`（0 errors / warnings / checks）。真实驱动函数的主机回归覆盖 datapath 位掩码、重复 DEVICE 恢复、PHY/PM 错误清理及 HOST 路径保留。恢复脚本的 5 项测试覆盖机型、host / 缺伙伴 / 未绑定拒绝、写前状态变化拒绝、已配置跳过及只改目标位。

完整 `bash scripts/check.sh --with-kernel` 在 WSL 的 LF 临时副本通过（Windows 配置片段为 CRLF，原始副本会令 grep 把行尾 CR 当作配置值一部分）。bundle 校验通过，pack 确认包含新提交，恢复出的两个驱动文件与实测源码一致；`git diff --check` 通过。

**已测**：新内核在 USB2 连接状态下重启、3 次同口拔插、USB3→USB2 换口，以及 USB2 双向各 64 MiB 文件传输，均无需恢复脚本。b 槽成功标记保留，无 failed units。完整分区备份只在忽略的 logs 中保存；只更新 boot_b，vendor_boot/设备树和 ramdisk 保留。

**未测**：完全断电后的启动、长时间/更多线缆与电脑、OTG / 带 PD Hub 和挂起恢复。此前 LPM 实验属性仍在本机 DT 中，是否可以移除也未做对照。不能把本轮通过扩展为所有 USB 场景已修复。
