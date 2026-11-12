# USB 调试通道（USB 网络 SSH + USB 串口）

状态日期：2026-11-12。这条通道**不依赖 Wi-Fi**。手机用 USB 线接电脑后，可以同时得到：

| 通道 | 电脑侧 | 手机侧 | 用途 |
| --- | --- | --- | --- |
| **USB 网络 SSH（首选）** | `ssh oneplus@10.55.0.1` | NCM 网卡 `usb0`，`10.55.0.1/24` | 日常调试、传文件、刷分区 |
| USB 串口 | Windows `COM3`，115200 8N1 | ACM `ttyGS0` + `serial-getty@ttyGS0` | 网络全挂时的救援 shell |

> **必须接电脑的 USB3 口。** 接 USB2 口时 gadget 只枚举约 3 秒就掉线（UDC 在 `default` / `not attached` 之间反复，速率只有 `full-speed`）。详见文末“已知问题”。

## 电脑侧使用

### 1. 设置一次静态 IP（Windows）

手机用 NetworkManager 的 shared 模式提供 DHCP，但实测 DHCP 包到不了 Windows，所以 **NCM 网卡必须手动设成静态 IP**。在管理员终端执行一次（网卡名以“网络连接”中新出现的 NCM 网卡为准，本机为“以太网 3”）：

```bat
netsh interface ipv4 set address name="以太网 3" static 10.55.0.2 255.255.255.0
```

不要设网关，避免抢走默认路由。Linux 主机同理：`ip addr add 10.55.0.2/24 dev <网卡>`。

### 2. 登录

```sh
ssh oneplus@10.55.0.1
```

电脑的公钥已经在手机的 `~/.ssh/authorized_keys` 里，可以用 `ssh -o BatchMode=yes` 做非交互调用。`sudo` 的密码和登录密码相同（来自构建时的 `image-credentials.json`）。root 不能远程登录。实测 ping 约 1 ms，传 20 MB 文件正常。

常用的非交互调用：

```sh
ssh -o BatchMode=yes -o ConnectTimeout=6 oneplus@10.55.0.1 'uname -r; uptime'
ssh oneplus@10.55.0.1 'journalctl -k -b --no-pager | tail -100'
scp images/7.3/boot.img oneplus@10.55.0.1:~/
```

### 3. 串口救援

网络起不来时（例如 NetworkManager 或 Wi-Fi 驱动坏了），用 PuTTY 或 `plink -serial COM3 -sercfg 115200,8,n,1,N` 打开 `COM3`，以 `oneplus` 登录。串口只依赖 gadget 本身，不经过任何网络栈。

### 连不上时按顺序检查

1. 线是否插在 **USB3 口**；设备管理器里是否同时出现 NCM 网卡和 `COM3`。
2. Windows 网卡是否还是 `10.55.0.2/24`（重装驱动或换口后可能被重置成 DHCP）。
3. 用串口登录，检查手机侧：`systemctl status usb-gadget`、`cat /sys/kernel/config/usb_gadget/negroni/UDC`（应为 `a600000.usb`）、`nmcli con show --active`（应有 `usb-debug` / `usb0`）。
4. 以上都不行，再走 Wi-Fi SSH（IP 由 DHCP 分配，会变；最近一次为 `192.168.137.143`）。

## 手机侧组成

文件存档在 [config/usb-debug/](../config/usb-debug/)。2026-11-12 在手机上**手动安装**，**尚未接入镜像构建**：全新刷入的镜像没有这条通道，需要按下面步骤补装（可以先通过 Wi-Fi SSH 操作）。

| 手机路径 | 仓库文件 | 作用 |
| --- | --- | --- |
| `/usr/local/bin/usb-gadget.sh` | [usb-gadget.sh](../config/usb-debug/usb-gadget.sh) | 通过 configfs 建立 `negroni` gadget：NCM `usb0` + ACM `GS0`，绑定第一个 UDC |
| `/etc/systemd/system/usb-gadget.service` | [usb-gadget.service](../config/usb-debug/usb-gadget.service) | 开机运行上述脚本，排在 NetworkManager 之前 |
| `/etc/udev/rules.d/86-usb-debug-managed.rules` | [86-usb-debug-managed.rules](../config/usb-debug/86-usb-debug-managed.rules) | NetworkManager 默认不管 gadget 网卡（`85-nm-unmanaged.rules`），这条规则把 `usb0` 设为受管 |
| NM 连接 `usb-debug` | — | `usb0` 上 `10.55.0.1/24`，`ipv4.method shared`，自动连接 |
| `serial-getty@ttyGS0.service` | — | 串口登录 |

补装步骤（在手机上执行）：

```sh
sudo pacman -S --needed dnsmasq   # NM shared 模式依赖
sudo install -m 755 usb-gadget.sh /usr/local/bin/usb-gadget.sh
sudo install -m 644 usb-gadget.service /etc/systemd/system/usb-gadget.service
sudo install -m 644 86-usb-debug-managed.rules /etc/udev/rules.d/86-usb-debug-managed.rules
sudo udevadm control --reload
sudo nmcli con add type ethernet ifname usb0 con-name usb-debug \
    ipv4.method shared ipv4.addresses 10.55.0.1/24 ipv6.method disabled connection.autoconnect yes
sudo systemctl enable --now usb-gadget.service serial-getty@ttyGS0.service
```

从 Windows 复制脚本到手机前要确认是 LF 换行，CRLF 会让 `/bin/sh` 报错。

## 为什么不用 adb

Arch 的 `android-tools` 不带 `adbd`，AUR 也没有可用的包（只有无人维护的 `xdbd-git`）；postmarketOS 用的也是 USB 网络加 SSH。所以本项目统一用 SSH。

## 已知问题与注意事项

- **USB2 口不可用。** gadget 枚举后约 3 秒断开，链路进入 Suspend；把 `max_speed` 限为 high-speed 也没有改善。推测是 HS PHY / USB2 通路问题，与 [USB2 Hub 诊断](../artifacts/usb2-diagnosis-20260916-030952/README.md) 同类。一加原厂 `waipio-usb.dtsi` 有 `snps,usb2-gadget-lpm-disable`、`has-lpm-erratum`、`hird-threshold`、`is-utmi-l1-suspend`、`disable-clk-gating` 等属性，我们的 DT 没有（实测 DCFG `0x00e00804`，LPMCap 打开）。本地准备了 `logs/usb-debug-20261112/0001-usb-negroni-disable-gadget-lpm.patch`，DTB 能编译通过，但**还没应用、也没刷入**。USB3 口能用，所以优先级不高；刷入需要重建 vendor_boot 并重启。
- 其他会话在用手机时（音频、相机、基带调试），**不要写 `usb_role`，也不要重新绑定 UDC**，否则所有人的 USB 连接都会断。
- 修改 Windows 网卡设置需要管理员终端，AI 代理通常没有这个权限，要请用户来执行。
