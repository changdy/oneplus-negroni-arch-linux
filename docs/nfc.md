# NFC

本机是 NXP SN100，挂在 I²C 地址 `0x28`（运行时节点 `1-0028`）。原厂项目 20846 的配置是 PLL 时钟、19.2 MHz，参考时钟来自 PMK8350 的 `LN_BB_CLK2`。主线驱动是 `nxp-nci` / `nxp-nci_i2c`，用户空间走 NFC generic netlink，不是原厂的 `/dev/nq-nci`。

## 2026-11-14 实机

控制器可以完成 NCI 2.0 复位和初始化。制造商 ID 为 `0x04`，NCI 版本 `0x20`。专有时钟参数 `0xA011` 读回的首字节已经是 `0x01`（PLL、19.2 MHz），没有改写其余字节。

改驱动之前，第一次上电可以打开，关闭后再打开会超时。原因是掉电时的 IRQ 毛刺被记成永久 I²C 故障，下一次打开不再清掉这个标记，VEN 高电平也只保持约 10 ms，SN100 来不及启动。

当前模块已在手机上替换并加载，未刷写启动分区，也未重启：

- 连续两次打开都成功，中间有一次关闭。
- 打开期间 `ln_bb_clk2` 的 enable 计数从 0 变为 1，关闭后回到 0。
- RF 发现命令返回成功，12 秒内没有 PLL 未锁定或发射器错误。旁边没有标签，没有读到 UID。

21:49 再测一次，仍未刷写、未重启。打开成功，`ln_bb_clk2` 在打开期间为 1、关闭后为 0。发现命令返回成功，原始 NCI 里只有配置和 `RF_DISCOVER`，12 秒内没有 `RF_DISCOVER_NTF` 或接口激活，随后正常去激活。UID / NDEF 仍未读到。

随后又做了 30 秒实时轮询。发现配置是 NFC-A / B / F / V，命令成功，期间没有发现通知，没有 UID。控制器在轮询未停时直接关闭会返回忙，进程退出后已单独关闭，电源状态回到关闭。

22:22 连续两次都在打开后约 20 ms 激活到同一张卡。UID 是 `CD 27 FC DB`，ATQA `00 04`，SAK `08`，NCI 协议是 T2T。SAK `08` 表示 MIFARE Classic 1K。主机发 Type 2 的 `READ 30 00` 后，控制器回 `04 14`：`04` 是卡的 NAK，后面的 `14` 被主线协议栈当成失败状态。没有读到块数据或 NDEF。两次结束后控制器都已关闭。

因此基本读标签所需的控制器打开、时钟和发现命令已经通了，Classic 卡的 UID 也已读到。NDEF 还要先做 Classic 认证，尚未测试。

## 手机模拟 UID

22:40 给 `nci` 加了 NFC-A 被动监听。目标协议只带 MIFARE、不再同时轮询时，驱动写入：

- `LA_BIT_FRAME_SDD = 0x04`，`LA_PLATFORM_CONFIG = 0x00`（ATQA `00 04`）
- `LA_SEL_INFO = 0x08`
- `LA_NFCID1 = CD 27 FC DB`

控制器对这四项和监听发现命令 `21 03` / 模式 `0x80` 都返回成功，并保持监听 20 秒。旁边没有读卡器，所以还没有证明门禁或 vivo 能看见这个 UID。监听期间没有接口激活通知。结束后控制器已关闭。

模块参数在 `/etc/modprobe.d/nci.conf`：`options nci emulate_uid=cd27fcdb`。当前已经加载的是这份模块，重启后由该参数带上 UID。开始模拟需要 root：

```
nfc-emulate 25
```

程序源码在 `artifacts/nfc-20261114/nfc-emulate.c`，手机上装在 `/usr/local/bin/nfc-emulate`。这只让手机在读卡器场里报出这个 UID 和 SEL_INFO `0x08`，不会回答 Classic 加密扇区。旁边没有读卡器，不能证明门禁或别的手机看得见。监听改动是内核 `b7385d286e`，gitlink 和 `local-7.3.bundle` 已更新。`configure-nfc.sh` 不写入 `emulate_uid`，确认读卡器认卡之前镜像不带这张 UID。新镜像未构建、未刷入。

内核 `fff7de955691` 包含已经验证的打开、`LN_BB_CLK2` 和电平触发中断。`configure-nfc.sh` 把时钟模块参数装进镜像，作为设备树还没生效时的回退；新设备树里的 `clocks` 和 `nxp,pll-19m2` 生效后，驱动不再靠 `bbclk2`。`defconfig` 和 `sm8450.config` 已经把 `nxp-nci` 编成模块。打包路径已接入，新镜像未构建、未刷入。

下一次启动要带上这次的模块参数，否则参考时钟不会打开。手机上已写入 `/etc/modprobe.d/nxp-nci.conf`：

```
options nxp_nci pll19=1
options nxp_nci_i2c bbclk2=1
```

设备树里的 `clocks = <&rpmhcc RPMH_LN_BB_CLK2>`、`nxp,pll-19m2` 和电平触发中断要等内核与 DT 一起刷入后才生效。刷入后不必再靠这两个模块参数。这次没有刷写，也没有重启。

打开时内核仍会打印一行 `unknown rsp opcode 0x3`。那是读取 `0xA011` 的响应，驱动已经收下，不是失败。
