# USB 调试通道（USB 网络 SSH + USB 串口）

资料整理：2026-11-15；实机记录截至 2026-11-14。这条通道**不依赖 Wi-Fi**。手机用 USB 线接电脑后，可以同时得到：

| 通道 | 电脑侧 | 手机侧 | 用途 |
| --- | --- | --- | --- |
| **USB 网络 SSH（首选）** | `ssh oneplus@10.55.0.1` | NCM 网卡 `usb0`，`10.55.0.1/24` | 日常调试、传文件、刷分区 |
| USB 串口 | Windows `COM3`，115200 8N1 | ACM `ttyGS0` + `serial-getty@ttyGS0` | 网络全挂时的救援 shell |

> **2026-11-13 USB2 驱动修复已部署。** 当前手机在 USB2 口可随启动、拔插自动恢复 `high-speed` 和 USB SSH；USB3 口仍为 `super-speed`。gadget 服务已接进镜像打包，带它的新镜像未构建、未刷入。详见文末“USB2 驱动部署与验证”。

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

文件存档在 [config/usb-debug/](../config/usb-debug/)。2026-11-12 在手机上手动安装。2026-11-14 接进镜像打包：`configure-usb-debug.sh` 安装下表文件和 NM 连接 [usb-debug.nmconnection](../config/usb-debug/usb-debug.nmconnection)（从手机原样取回），并启用两个服务，`prepare-rootfs.sh` 安装 `dnsmasq`。仓库里三份 gadget 文件与手机上的 SHA-256 一致。带这条通道的新镜像未构建、未刷入；在那之前刷入的旧镜像仍要按下面步骤补装（可以先通过 Wi-Fi SSH 操作）。

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

- **USB2 原故障（运行时规避见下节）。** gadget 枚举后约 3 秒断开，链路进入 Suspend；把 `max_speed` 限为 high-speed 也没有改善。推测是 HS PHY / USB2 通路问题，与 [USB2 Hub 诊断](../artifacts/usb2-diagnosis-20260916-030952/README.md) 同类。一加原厂 `waipio-usb.dtsi` 有 `snps,usb2-gadget-lpm-disable`、`has-lpm-erratum`、`hird-threshold`、`is-utmi-l1-suspend`、`disable-clk-gating` 等属性，我们的 DT 原先没有（2026-11-12 实测 DCFG `0x00e00804`，LPMCap 置位）。
- **2026-11-13 已把 LPM 补丁刷入当前 b 槽（后续 USB2 实测无效）。** 补丁是 `logs/usb-debug-20261112/0001-usb-negroni-disable-gadget-lpm.patch` 的一行属性 `snps,usb2-gadget-lpm-disable`。本机 WSL 构建树被安全策略禁用，改用 `logs/usb-debug-20261112/inject-lpm-dtb.py` 从手机当前分区的 DTB 直接注入：原 5269 个属性逐字节不变，只多 1 个布尔属性，vendor_boot v4 头仅 `dtb_size` 从 178513 改为 178554。刷前备份 `vendor_boot_b-original-20261113.img`（sha256 `c46b3d9b…`），写入 `vendor_boot_b-lpm.img`（sha256 `be29366a…`）后回读一致；**只刷 `vendor_boot_b`，未动 boot/userdata/vbmeta，未切槽**（a 槽 `Bootable=0`，不能切槽回滚）。重启后 USB SSH 约 47 秒恢复，`/sys/firmware/devicetree/base/soc@0/usb@a600000/snps,usb2-gadget-lpm-disable` 存在，debugfs `regdump` 的 DCFG 为 `0x00a00814`：bit22（`DWC3_DCFG_LPM_CAP`，`0x00400000`）已从 1 清零；槽位 b 仍 `Active/Successful/Bootable=1`，无 failed units，USB3 口 NCM `usb0` 与串口正常。
- **2026-11-13 16:44 USB2 口实测：补丁无效，LPM 不是根因。** 把线换到电脑 USB2 口后，手机侧 `udc state = not attached`、`usb0` 消失、`link_state = Suspend`，Windows 报 `未知 USB 设备(设备描述符请求失败)`（`USB\VID_0000&PID_0002`，ProblemCode 43）。同一时刻 DCFG 仍为 `0x00a00804`（bit22 已清零），补丁生效但问题依旧。内核日志给出触发序列：`!!!!!enable otg` → `xhci-hcd ... io mem 0x0a600000` 注册 host 控制器 → `!!!!!disable otg` → xhci 移除；gadget 没有重新绑定，所以 `usb0` 不再出现。这与 [USB2 Hub 诊断](../artifacts/usb2-diagnosis-20260916-030952/README.md) 的 CID/OTG 方向一致：**当时确实出现 OTG host 使能及 DWC3 切换，但 21 时的后续实验表明它不是全部 USB2 失败的原因**。同一秒还有 `qcom-snps-hs-femto-v2-phy 88e3000.phy: restoring USB2 PHY after reference clock loss`（角色切换的伴随现象）和 `usb_adap_type: 17`（厂商 PD_SDP）；`cid detect || no detect`、`typec_state_change_work` 连续出现，说明充电 IC 的 CID/Type-C 状态机在 USB2 口（A-to-C）下反复判定。实际运行的 `oplus_battmgr` 收到 `BC_OTG_ENABLE` 后只拉 `otg_boost_en`/`otg_ovp_en` GPIO，不直接写 `usb_role`；host 切换发生在 PMIC/Type-C 一侧，具体触发点仍待确认。
- **后续方向与回滚。** 原厂 `waipio-usb.dtsi` 的其他 LPM 属性（`has-lpm-erratum`、`hird-threshold`、`is-utmi-l1-suspend`、`disable-clk-gating`）大概率也不是重点。2026-11-13 对照一加 10T（`anorak-usb.dtsi`）与 10 Pro（`oplus-chg-20845.dtsi`）原厂 DT 后发现：10T 根本没用 `snps,usb2-gadget-lpm-disable`，而是 `has-lpm-erratum` + `hird-threshold = 0` + `is-utmi-l1-suspend`；且 10T 的 USB2 走 eUSB2 + NXP repeater，与 10 Pro 的 HS PHY 不是一套硬件，DT 不能照搬。10 Pro 充电 DT 有 `qcom,otg_scheme = <0>` 和 boost/OVP GPIO，但我们的 `oplus_battmgr.c` 不解析 `qcom,otg_scheme`，补 DT 也不会生效。详见 [10T/10 Pro DT 对照](../artifacts/usb2-diagnosis-20260916-030952/oneplus-10t-dt-comparison.md)。这属于 16 时的排查方向；21 时已用 PHY datapath override 清位恢复 USB2，见下节。CID/OTG 日志本身不能证明它导致全部 USB2 故障。补丁对 USB3 口无影响，可保留为已否证的实验，也可回滚：把 `vendor_boot_b-original-20261113.img` 写回 `vendor_boot_b` 并重启。
- **2026-11-13 16:53 换回 USB3 口：自动恢复，且不触发 OTG。** 换回后 `udc state = configured`、`usb0` 10.55.0.1/24 回来、`mode = device`、`link_state = U0`，Windows 侧 NCM `10.55.0.2/24` 与 `COM3` 均正常，**无需重启服务或手机**。内核日志在 16:52:57 只有一条 `request ... was not queued to ep3in`，没有再次出现 `enable otg`/xhci 注册；与 16:44:36 USB2 口的 `enable otg`→xhci→`disable otg` 对比，说明 OTG host 切换只由 USB2 口路径触发。DCFG 回到 `0x00a00814`（bit22 仍为 0）。补丁、注入脚本与两份镜像都在 `logs/usb-debug-20261112/`，**未纳入 Git、未接入镜像构建**；全新刷入的镜像仍不含此属性。
- 其他会话在用手机时（音频、相机、基带调试），**不要写 `usb_role`，也不要重新绑定 UDC**，否则所有人的 USB 连接都会断。
- 修改 Windows 网卡设置需要管理员终端，AI 代理通常没有这个权限，要请用户来执行。

## USB2 运行时恢复（2026-11-13 21 时历史对照）

本节记录修复前的手工对照；22 时已刷入驱动修复，当前结果见下一节。

**已恢复 USB2 high-speed 枚举、NCM USB SSH 和双向各 32 MiB 文件传输，SHA-256 一致。** 重新插线会再次留下充电检测 override，仍需手动运行恢复脚本；没有安装自动恢复服务，也没有部署新的内核。

本轮 20 ms 状态采样中，失败时 DWC3 / Type-C 一直是 device，configfs `UDC=a600000.usb`、`usb0` 仍在，GPIO57/64 为 low，没有 `enable otg` / xHCI 注册。清除 HS PHY `PHY_CFG0`（`0x088e3094`）bit 0 `UTMI_PHY_DATAPATH_CTRL_OVERRIDE_EN` 后约 0.23 秒完成配置；参考时钟保持原值也能恢复并传输。因此此前“OTG 切走且 gadget 未重绑”不能解释本轮失败。

寄存器组合与原厂充电检测的 high-Z 模式一致，但重新置位的具体写入者尚未直接追踪。参考时钟实验已还原；未重启、未刷分区、未写 USB role、未重新绑定 UDC。本轮保留此前 LPM 实验属性，其移除后的表现未测。

USB2 故障时，通过 Wi-Fi 备援登录手机。将 [negroni-usb2-recover.py](../scripts/negroni-usb2-recover.py) 复制到手机后执行（本轮已放在 `/tmp`，重启后需重新复制）：

```sh
sudo python3 /tmp/negroni-usb2-recover.py           # 只查看
sudo python3 /tmp/negroni-usb2-recover.py --apply   # 核对状态后只清 PHY_CFG0 bit 0
```

脚本限定 Negroni、device 角色、有 Type-C 伙伴、UDC 已绑定且未枚举；已配置时跳过，host / 未绑定 / 写前状态变化时拒绝。执行时保持线缆不动，用户空间检查不能与内核切换角色形成原子操作。直接寄存器操作属于实验性规避，未接入镜像构建。

整理后的证据、精确时序及 [驱动候选补丁](../artifacts/usb2-gadget-20261113/usb2-datapath-candidate.patch) 见 [USB2 gadget 实验记录](../artifacts/usb2-gadget-20261113/README.md)。候选覆盖 PHY 初始化/模式设置的 datapath 释放，以及 DWC3 同为 device 时仍重新设置 PHY 模式的路径。这段是写验证记录时的状态。随后的 datapath 修复已经进入内核 `f8350cc1e221` 并刷入 b 槽，见下一节。USB2 LPM 属性实验没有进 Git，也没有进镜像构建；去掉该属性之后的表现仍未测。

## USB2 驱动部署与验证（2026-11-13 22 时）

**当前手机已能在 USB2 口自动启动、拔插恢复，无需运行恢复脚本。** 内核提交 `f8350cc1e221ce4cb22beec8a9eeae7a5ad77a2d` 已纳入源码恢复 bundle；手机运行 `7.3.0-sm8450+ #4`（2026-11-13 21:54:31 构建）。

修复在 PHY 初始化和 USB 模式设置时释放充电检测 datapath override；Qualcomm DWC3 收到 DEVICE 请求时，即使控制器本来就是 device，也重新设置 USB2 PHY 模式，避免同角色早退漏掉恢复，并用 DWC3 mutex 串行化角色工作。只在实际释放 override 时打印诊断；既有参考时钟丢失恢复日志仍保留。

经用户同意，已备份手机当前完整 `boot_b`、`vendor_boot_b`，在手机和电脑核对 SHA-256 后，仅写入 `boot_b` 并回读校验、重启。新镜像 header v4 除 kernel size 外逐字节不变，ramdisk 不变，`vendor_boot_b` 和设备树不变；原有音频/相机内核改动保留，没有部署新的相机模块。b 槽仍为 Active / Successful / Bootable = 1，系统无 failed units。

| 实机项目 | 结果 |
| --- | --- |
| USB2 口保持连接重启 | 新内核自动 `configured / high-speed`，USB SSH 正常 |
| 同一 USB2 口连续拔插 3 次 | 全部自动恢复 high-speed、NCM carrier=1 |
| USB2 → USB3 → USB2 | USB3 自动 super-speed，回 USB2 自动 high-speed |
| 换口后的 USB2 文件传输 | 上下行各 64 MiB，电脑、手机、回传 SHA-256 一致 |
| 启动槽与服务 | b 槽成功位保留，无 failed units |

本轮重启后没有复制或执行 `/tmp/negroni-usb2-recover.py`，也没有自动清寄存器的用户空间服务。恢复来自新内核；只读采集的状态转换与内核 PHY 恢复日志相互印证。

该轮未测完整镜像重建、完全断电后的启动、OTG host / PD Hub / 挂起恢复，设备树当时保留 `snps,usb2-gadget-lpm-disable` 实验属性。原始输出与完整分区备份在忽略的 `logs/usb2-driver-20261113/`，整理后的 [验证记录](../artifacts/usb2-gadget-20261113/driver-evidence.json) 与 [构建报告](../artifacts/usb2-gadget-20261113/driver-build.json) 可供复核。

2026-11-18 使用不含该 LPM 属性的正式 DTB 启动，USB3 NCM SSH 在一次重启及一次 38.4 秒深睡唤醒后均恢复，设备端为 `super-speed`。USB2 和 OTG 挂起恢复仍未测。[该次深睡记录](camera.md#正式-dtb-刷写与整机深睡2026-11-18)

## USB SSH 意外断连排查（2026-11-13 22:34–22:45）

用户未移动 USB 时，SCP 曾报 `reset by peer`，随后两次 USB SSH 超时，22:36:53 自动恢复。**根因尚未定位。** Wi-Fi 只读采集未发现手机重启、gadget/NM/sshd 重启、USB 重新枚举、host 角色切换或 PHY override 回归的证据；Windows 设备最近到达时间仍为 22:02:48，手机最后的内核与 carrier 日志也在 22:02。原 SCP 的 TCP 连接仍在手机上退避重传，因此不能仅凭客户端报错认定是手机 SSH 主动断开。

随后双通道每秒观测 3 分钟：均为 `configured / high-speed / device`，carrier 计数不变，netlink 无变化；USB 上下行各 512 MiB 哈希一致，原目录 158,666,752 字节文件的 SCP 复测也一致，未复现。Windows 同时有 Hyper-V/FSE 虚拟网络活动，但时序和本轮对照不足以证明因果；手机到电脑的 ICMP 无响应也不能作为断连依据，同期 TCP 双向传输正常。

本轮全程未重启、刷写或改动 USB/网络配置。尚缺故障当时的双端抓包或 USB 请求跟踪，主机 NCM/过滤/路由及手机数据路径的短暂异常均未排除，长时间稳定性未测。整理后的 [事件时序与证据](../artifacts/usb-disconnect-20261113/README.md) 区分了观测与推测，原始日志独立保存在 `logs/usb-disconnect-20261113/`。

## 历史实验与恢复操作边界（2026-11-15 整理）

LPM 已否证实验的[补丁和离线 DTB 注入脚本](../artifacts/usb2-gadget-20261113/experiments/README.md)已保存；默认构建不应用。只读对照 10T 设备树的结论仍有效：硬件通路不同，不能照搬。USB2 后续 datapath 修复与自动拔插成功采用较晚记录，不能继续概括为“USB2 一律不可用”；OTG/PD Hub、断电和深睡按上文保留验证边界。

旧手机 `usb-gadget.sh` 的 start 在 configfs 目录已存在时直接退出，`systemctl restart usb-gadget.service` 可能只解除绑定而不恢复。不要用它作为随手修复方法，也不要在多人会话中重绑 UDC；会同时断开 USB SSH/串口，Windows 还可能重建网卡实例而丢失静态地址。保留已知可用 USB3 通道，故障时先采证据，恢复和重启按操作规则安排。
