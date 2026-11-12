# 蓝牙（WCN6855）

状态日期：2026-11-12。

| 项目 | 状态 |
| --- | --- |
| 固件加载、HCI 控制器 | 正常 |
| 自动设置地址并开启适配器 | 实机已验证（手动安装后重新加载 `hci_uart`） |
| 扫描 | 实机已验证：扫到 10 个设备，期间 Wi-Fi 稳定，没有出现共存掉线 |
| 完整重启、镜像构建路径、配对、A2DP 音频 | 未测 |

## 问题与修复

固件加载正常，唯一的阻碍是 `hci0` 被内核注册成 “Unconfigured controller, missing options: public-address”：WCN6855 的 UART 控制器没有 Linux 能读到的出厂 BD 地址，bluetoothd 因此忽略它。

修复见 [config/bluetooth/](../config/bluetooth/)：

| 文件 | 安装位置 | 作用 |
| --- | --- | --- |
| [90-negroni-bt-address.rules](../config/bluetooth/90-negroni-bt-address.rules) | `/etc/udev/rules.d/` | HCI 设备出现时拉起对应的服务 |
| [negroni-bt-address@.service](../config/bluetooth/negroni-bt-address@.service) | `/etc/systemd/system/` | 在 `bluetooth.service` 之前运行 |
| [negroni-bt-address](../config/bluetooth/negroni-bt-address) | `/usr/local/libexec/` | 由 SoC 序列号（`/sys/devices/soc0/serial_number`）生成固定的本地管理地址 `02:4E:xx:xx:xx:xx`，读不到序列号时改用 machine-id；等待 QCA 初始化完成后用 `btmgmt public-addr` 写入 |

这三个文件登记在 `scripts/runtime_fixes.py` 中，随 `configure-runtime-fixes.sh` 进入全新 rootfs，已有镜像由 `update-runtime-fixes-image.sh` 补装。`bluez-utils` 已加入软件清单（提供 `btmgmt`）。

## 检查

在手机上执行：

```sh
systemctl status 'negroni-bt-address@hci0'
btmgmt --index 0 info        # 应有 addr 02:4E:...，current settings 含 powered
bluetoothctl show
```

此前一次“断连”经查是用户在 Plasma 中主动重启，与蓝牙无关。
