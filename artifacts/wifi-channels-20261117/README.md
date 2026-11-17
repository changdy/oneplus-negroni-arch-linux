# Negroni Wi-Fi 信道 12/13 修复（2026-11-17）

## 根因

通过 USB SSH 读取当前 `7.3.0-sm8450+`、WCN6855 hw2.1，global 与 self-managed PHY 均为 CN，但 PHY 的 2.4 GHz 规则为 `2402–2472 MHz`，2467 MHz（12）和 2472 MHz（13）均为 disabled。

22:47 临时打开 ath11k 的监管调试，执行 `US → CN` 后恢复调试开关。固件接受两次请求，返回：

| 国家码 | 固件返回的 2.4 GHz 规则 | 最终 PHY 规则 |
| --- | --- | --- |
| US | 2402–2472 MHz，40 MHz，20 dBm | 2402–2472 MHz |
| CN | 2402–2482 MHz，40 MHz，20 dBm | 2402–2472 MHz |

因此信道 12/13 是在主机与初始化默认规则取交集时被裁掉；不是 CN 配置未应用，也不是固件拒绝 CN。`00` 提示曾被固件拒绝，随后已恢复 global CN。

修复只对设备树 `oplus,negroni` 加 WCN6855 hw2.0/2.1 使用固件成功接受国家码后返回的规则。保留国家码请求的固件成功检查、功率/DFS/信道标志、其他机型的交集和默认回退。没有扩写频段边界、替换固件/监管数据库或修改设备校准。

依据：[OpenWrt 2023 年对应修复](https://lists.infradead.org/pipermail/lede-commits/2023-April/017910.html)。该记录及 Qualcomm 补丁说明固件会执行 BDF 限制；本项目将行为变化限定在本机，未全局移除 ath11k 的交集代码。

## 检查与首次热更新

- ARM64 ath11k / ath11k_pci 模块编译通过，vermagic 与手机一致。
- `tests/test-wifi-regulatory.py` 提取真实驱动函数，并从真实 Negroni DTS 获取 compatible；102 组机型、芯片和国家码组合通过。覆盖普通机型保持交集、Negroni 两版 WCN6855 使用固件规则、其他芯片保持交集、空默认规则和 `00` / `na`。
- `bash scripts/check.sh` 通过；补丁 `checkpatch.pl --strict` 与 `git diff --check` 通过。
- 首次候选误用了 `oneplus,negroni`，未命中设备树；回归已发现并改成 `oplus,negroni`。
- 22:49 首次热更新脚本在驱动重载后仍查询 `phy0`，实际新设备为 `phy1`，查询失败触发回退。回退中的第二次模块卸载未完成；串口看到 `modprobe` 和新的 sshd 子进程为 D 状态，`ath11k_pci` 引用计数为 -1。USB ping 与已有串口 shell 仍可用，但该 shell 退出后无法再登录。未取得内核栈，卸载阻塞的具体锁尚未定位。
- 用户同意重启恢复。正常重启未完成，USB 未重新枚举且原 TCP 连接仍在；用户随后强制关机再开机，23:00 重新连上，B 槽 Active / Successful / Bootable 均为 1。没有刷写分区。后续检查从 `/sys/class/net/wlp1s0/phy80211` 获取 PHY，不能假定编号为 0，也不能在检查失败时立即重复卸载模块。

原始输出仅保存在本地 `logs/wifi-channels-20261117/`，不入库。

## 修复版部署与实测（23:02–23:04）

内核提交 `ad0c3dbdbde4996f1bd382e6b4c63c7aeab30e9c`；重新执行正常 Kbuild 的模块构建，安装两份 stripped 模块，随后 `depmod`，单次卸载/加载通过。调试掩码最终恢复为 0。模块 SHA-256：

| 文件 | SHA-256 |
| --- | --- |
| `ath11k.ko` | `ae109095884694114396e622aaaf3edd4f2ff19300b49be2856b8ea7f767e64b` |
| `ath11k_pci.ko` | `4730d4689a99a26d687302c91bf0e14ff5ce5464bdf60f718271fd8bb863260f` |

| 实测 | 结果 |
| --- | --- |
| 固件初始化 | 明确返回 US 的 2402–2472 MHz；随后 CN 返回 2402–2482 MHz，修复后 PHY 保留 CN 的完整范围 |
| CN 信道 | 12/13 均启用，20 dBm，允许 20 MHz / HT40-；14 disabled |
| 定向扫描 | `iw dev wlp1s0 scan freq 2467 2472` 返回 0，附近没有这两个频率的 BSS；不能据此宣称已连接 12/13 热点 |
| 切到 US | 12/13/14 均 disabled，保留固件国家限制 |
| 恢复 CN | 12/13 重新启用，14 disabled，最终保留 CN |
| 已有网络 | 信道 8 自动重连；经 `wlp1s0` 向网关 ping 4/4 成功，无丢包 |
| 系统状态 | `systemctl is-system-running` 为 running，修复部署后日志没有新的 firmware crash、硬件重启、Oops 或 timeout |

原始模块备份位于手机 `/var/lib/negroni-wifi-backups/20261117-224859/`，初始两份模块哈希分别为 `ac93dd69db7ad0047f389180c5f79009425e9d3de2983004aa3e73eb0c8463d6`、`a3adc6705b7df3d2bddf3bb4d4d59c073bccba1e799551f5eb35e3adb38e8d13`。需要恢复时先将这两份文件复制回 `/usr/lib/modules/7.3.0-sm8450+/kernel/drivers/net/wireless/ath/ath11k/` 并运行 `depmod -a`；然后在获得用户同意后重启。避免立即重复卸载正在初始化的驱动。23:02 的第二份备份是未命中 compatible 的首次候选，不能当作原始模块。

用户空间 CN 提示及 PHY-add udev 规则继续使用既有 `configure-wifi.sh`；全部 Kbuild 模块由现有镜像安装/检查路径交付。父仓库 gitlink 与 `local-7.3.bundle` 已同步，bundle 保留历史 rc2 引用与两个原有前置提交，并通过验证。

**未测**：12/13 上的实际热点关联与传输、修复版整机重启、完全断电启动、睡眠恢复、长期稳定性与功耗。完整新镜像未构建、未刷入。
