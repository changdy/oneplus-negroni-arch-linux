# 基带（MPSS）、SIM、移动数据与 VoLTE

状态日期：2026-11-12。设备 NE2210，内核 `7.3.0-sm8450+`，实测用中国电信卡。

| 功能 | 状态 |
| --- | --- |
| 基带启动 | **可用**。QRTR 握手竞争导致的约 40 秒看门狗循环崩溃已由内核 `984f1b07caa` 修复 |
| 无卡上线 | 可用：手动设为 online 后能测到 LTE 信号（RSSI -65 dBm，RSRP -94 dBm） |
| 开机带卡 | 可用：开机选卡成功，ModemManager 显示 `registered` |
| 开机后热插卡 | 已用 `negroni-uim-hotplug.service` 解决；模拟重插约 2 秒恢复，物理重插未测 |
| 移动数据 | 可用（电信 APN `ctnet`），IPv4 + IPv6 均通 |
| VoLTE 拨出 | 能到 `ringing-out` → `active`；**通话没有声音**（内核缺少语音通路） |
| 来电、短信 | 未测 |
| IMEI | 读出为 `unknown`（MEID 正常），原因未查 |

## 1. 看门狗循环崩溃（已修复）

现象：基带启动约 40 秒后出现 `DOG detects stalled initialization` 并重启，循环往复；QMI 的 uim 服务始终不出现。

定位过程：

- 基带本身没问题，固件来自手机自己的 `modem_b` 分区，换固件不能解决。
- 崩溃和基带启动时的一对内核日志一一对应：`failed to announce new service` / `failed while handling packet from 0:-2`（QRTR 名称服务）。出现这对日志的 14 次启动全部卡死，没出现的 6 次全部正常。快速重启 `rmtfs`（间隔 1.5 秒）每次都能复现。
- 根因在 `net/qrtr/af_qrtr.c`：上游 `544d85de4dc2`（"net: qrtr: Send HELLO message on endpoint register"）之后，本端 HELLO 发出前，`qrtr_node_enqueue()` 对 HELLO 以外的包一律返回 `-EAGAIN`。如果基带的 HELLO 先到，名称服务的 NEW_SERVER 通告就会被拒，而且不会重发，基带因此一直找不到 rmtfs。
- 修复 `984f1b07caa`：记录远端已经发过 HELLO，等本端 HELLO 发出后，再把它交给名称服务重新通告一次。实机上基带（节点 0）和 WCN6855（节点 7）都会触发这个竞争，重放后都能恢复。日志里的 `failed to announce new service ... -11` 属于预期输出。上游有同思路但未合入的补丁（2026-10），上游合入正式修复后应替换本补丁。详见[内核修复说明](../patches/linux/README.md)。

排查思路：先看 QRTR 通告是否失败，不要从固件或 pd-mapper 启动顺序入手。

## 2. SIM 选卡与热插拔

- 查卡前**先确认卡槽里有没有卡**。无卡时两个卡槽都报 `no-atr-received` / `absent`，属于正常。
- `msm-modem-uim-selection.service` 只在开机时运行一次，只等 4 秒。开机后再插的卡会停在 `detected`，基带不会自动建立 provisioning session，ModemManager 报 `sim-missing`，基带停在 `shutting-down` 模式。
- 手动恢复（用户 `oneplus` 调用 qmicli 时**不要加 `-p`**，qmi-proxy 属于 root）：

  ```sh
  qmicli -d qrtr://0 --uim-get-card-status          # 找 USIM 的 AID
  qmicli -d qrtr://0 --uim-change-provisioning-session=slot=1,activate=yes,session-type=primary-gw-provisioning,aid=<USIM AID>
  qmicli -d qrtr://0 --dms-set-operating-mode=online
  sudo systemctl restart ModemManager
  ```

- 自动处理：`negroni-uim-hotplug.service` 每 5 秒查询一次，发现有卡但没有 Primary GW session 时重新运行选卡脚本；如果 ModemManager 没有可用的 modem，就重启它。由 `configure-modem-uim.sh` 安装，见[构建集成说明](build-integration.md)。“MM 失败后重启”的分支和物理重插还没测。

## 3. 移动数据

NetworkManager 连接 `ct-lte`：APN `ctnet`，用户名 `ctnet@mycdma.cn`，数据接口为 `qmapmux0.0`。镜像里不预置这个连接，各运营商需要自己添加：

```sh
sudo nmcli con add type gsm ifname '*' con-name ct-lte gsm.apn ctnet gsm.username ctnet@mycdma.cn
```

## 4. VoLTE

电信在 LTE 上没有电路域语音（`CS: detached`）。基带注册 IMS 时会向主机请求一条 `IMS` APN 的数据连接（QMI IMS DCM，QRTR 服务 770）。没有程序应答时，拨号直接返回 QMI `InvalidArgument`。MCFG 已经是正确的 `OPLUS_hVoLTE_OPNMKT_CT`。

方案：用 postmarketOS 的 [81voltd](https://gitlab.com/flamingradian/81voltd) 应答，以 `negroni-81voltd.service` 跟随 ModemManager 启停。它必须在 ModemManager 有已注册的 modem 后才启动，因为基带只请求一次（单元里有 `ExecStartPre` 等待）。本地补丁 [81voltd-negroni.patch](../config/volte/81voltd-negroni.patch) 做两件事：

1. 基带会连续发两次 Start Connection，两个并发的 `Connect()` 打到同一个承载会让 ModemManager 1.24.2 段错误，所以加了防重入。用两个并行的 `mmcli -b N --connect` 也能复现。
2. 承载被外部断开时退出，由 systemd 重启，让基带重新请求。

承载互相挤掉的两个原因：

- `spacebar-daemon` 6.3.4 每新增一个承载，就对其它所有承载调用 `DeleteBearer`。已用 polkit 规则 `49-negroni-spacebar-bearers.rules` 禁止，实测返回 Unauthorized 且不崩溃。
- NetworkManager 关闭移动数据时用 `Simple.Disconnect` 断开**所有**承载。之后 ModemManager 1.24.2 在下次连接时大概率段错误（4 轮开关崩 4 次），约 20 秒后自动恢复。根因未找到：没有调试符号，仓库里也没有更新的包。

其它要点：IMSA / IMS settings 查询即使在能打电话时也返回 `InvalidOperation`，不能用来判断 IMS 是否注册。打电话不需要把 IMS 接口拉起来。81voltd 是在手机上编译的二进制，来源、补丁和校验和见 [81voltd.source](../config/volte/81voltd.source)。安装与限制见[构建集成说明](build-integration.md)。

通话音频：SM8450 用 AudioReach，当前内核没有 q6voice，只有 4 个 MultiMedia PCM，也没有语音 UCM，所以接通后没有声音。这是下一步要做的工作。

## 5. 相关事实

- rmtfs 使用 `rmtfs-oplus`，把 `/oem/nvbk/static|dynamic` 映射到 `oplusstanvbk` / `oplusdycnvbk`，以只读（`-r`）运行。`fsg` / `fsc` 分区全为 0。
- 内核实际在 WSL 发行版 `NegroniBuild-Ubuntu-26.04` 的 `/opt/negroni-build/linux` 中构建（Windows 检出的 `linux/` 子模块为空）。那是浅克隆，重建 bundle 时需要让 `GIT_SHALLOW_FILE` 只列出两个前置提交。
- 原始调试脚本与测试镜像放在本地 `logs/modem-qrtr-20261111/`、`logs/volte-20261112/`（不纳入 Git）。
