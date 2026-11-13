# 基带（MPSS）、SIM、移动数据与 VoLTE

状态日期：2026-11-12。设备 NE2210，内核 `7.3.0-sm8450+`，实测用中国电信卡。

| 功能 | 状态 |
| --- | --- |
| 基带启动 | **可用**。QRTR 握手竞争导致的约 40 秒看门狗循环崩溃已由内核 `984f1b07caa` 修复 |
| 无卡上线 | 可用：手动设为 online 后能测到 LTE 信号（RSSI -65 dBm，RSRP -94 dBm） |
| 开机带卡 | 可用：开机选卡成功，ModemManager 显示 `registered` |
| 开机后热插卡 | 已用 `negroni-uim-hotplug.service` 解决；模拟重插约 2 秒恢复，物理重插未测 |
| 移动数据 | 可用（电信 APN `ctnet`），IPv4 + IPv6 均通 |
| VoLTE 拨出 | 能到 `ringing-out` → `active` |
| 通话声音 | 下行、通话录音、向对方放音可用（实验）；对方听不到本机麦克风，见[通话语音](call-audio.md) |
| 来电、短信 | 用户确认来电可接通；短信未测 |
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

2026-11-12 16:21 重启后出现一次 IMS 承载未建立：81voltd 首次 `Connect()` 返回 `call-already-present`，之后进程保持运行但不重试，IMS 承载一直未连接，拨号返回 `InvalidArgument` 或在 `dialing` 约 19 秒后终止。手动 `systemctl restart negroni-81voltd` 后恢复（期间又触发一次 ModemManager 段错误并自恢复）。17:00 重启后再次出现；这次只重启 81voltd 仍报同样错误，`systemctl restart ModemManager` 后 IMS 承载才连接。两次重启两次出现。81voltd 本身仍不重试，改由下面的恢复服务在外部检测结果并分级恢复。

### IMS 承载自动恢复（2026-11-13）

不改预编译的 81voltd：它在 `Connect()` 失败后仍保持运行，而基带只在 QMI 服务出现时请求一次 IMS 连接，所以首次失败后不会自己恢复。`negroni-ims-recovery.service` 直接查询 ModemManager 里 `IMS` APN 的承载是否 `connected=yes`，按结果分级处理：

1. 连续 2 次检查（默认每 15 秒）没有 IMS 承载 → 重启 `negroni-81voltd.service`，让基带重新请求；两次重拉间隔至少 30 秒。
2. 连续 6 次仍没有、且有其它数据承载在线 → 重启 `ModemManager.service`，清掉导致 `call-already-present` 的残留呼叫状态；默认每次启动最多 2 次、间隔至少 5 分钟。IMS 承载恢复后计数清零。

配置在 `/etc/negroni-ims-recovery.conf`。重启 ModemManager 会重连移动数据并可能打断通话，设 `ALLOW_MODEMMANAGER_RESTART=0` 可完全禁用第二级；用户关闭移动数据（没有任何已连接承载）时也不会触发第二级。服务随 ModemManager 启动，**不使用 `BindsTo`**，否则它自己重启 ModemManager 时会被一起停掉。

只读检查（不修改任何东西）：

```sh
sudo python3 /usr/local/libexec/negroni-ims-recovery.py --check
```

输出 modem 状态、承载数和 IMS 承载 up/down。

来源与安装：`config/volte/negroni-ims-recovery.py`、同名 `.conf`、`config/systemd/negroni-ims-recovery.service`，由 `configure-volte.sh` 安装并启用，`verify-volte-image.py` 在封装前核对内容、权限和两个启用链接。

2026-11-13 实机核查与验证（USB SSH；用户已同意重启相关服务）：

- 只读核查：本次开机 81voltd 仍打印一次 `Failed to connect: ... call-already-present`，`NRestarts=0`，但 `IMS` 承载（IPv6、`qmapmux0.1`）最终为 `connected=yes`（`attempts=3`、`failed-attempts=1`）——说明基带重发请求有时能自愈，但不保证。
- 部署：三个文件已装到手机并启用 `negroni-ims-recovery.service`；`--check` 正确报告 `IMS bearer: up`；`systemd-analyze verify` 通过。
- **真实故障注入（第一级）**：先停 81voltd 再删除 IMS 承载，服务在 15:42:57 检出缺失、15:43:12 连续第 2 次后执行 `restart negroni-81voltd.service`，15:43:42 报告 `IMS bearer recovered`。期间 ModemManager 1.24.2 仍自行崩溃重启一次并重建承载。另一次直接删承载的注入由既有链路（81voltd 检测到承载被外部断开后退出重启）自愈，服务只记录 `probe failed ... couldn't find modem`，没有动作。
- **受控注入（第二级）**：停掉后台服务后向同一状态机连续注入 6 次"IMS 承载缺失"，第 2 次真实重拉 81voltd、第 6 次真实重启 `ModemManager.service`（1/2），约 21 秒后 IMS 承载恢复；随后恢复后台服务，三个服务均 active。这是注入模拟探测结果、真实执行动作，**不等于真实故障自然走到第二级**。
- **开机自愈（重启手机，用户已同意）**：16:01 重启后 `call-already-present` 再次复现，恢复服务在 16:01:52 / 16:02:07 连续两轮检出 IMS 承载缺失并重拉 81voltd，约 27 秒后 IMS 承载建立；四个服务均 active，`qbootctl` 显示 b 槽仍 `Active=1 / Successful=1 / Bootable=1`。开机时另留下一条未连接的 IMS bearer，不影响判断。
- **拨号 / 通话**：拨 10000（电信自动服务号）走通 `dialing → ringing-out → active`，`negroni-call-audio` 语音图打开，8 秒通话录音下行声道 RMS 2816、峰值 19804；上行声道全 0（已知内置麦克风无信号，非本次回归）。通话已正常挂断并删除 call 对象。
- 仍未测：全新完整镜像未构建（本机 WSL 被安全策略禁止、Windows 无 `debugfs`）；构建链已静态核查并补齐续建触发，实际构建与封装校验待在 WSL 执行。

其它要点：IMSA / IMS settings 查询即使在能打电话时也返回 `InvalidOperation`，不能用来判断 IMS 是否注册。打电话不需要把 IMS 接口拉起来。81voltd 是在手机上编译的二进制，来源、补丁和校验和见 [81voltd.source](../config/volte/81voltd.source)。安装与限制见[构建集成说明](build-integration.md)。

通话音频不在本文展开：语音图、自动开关服务、通话录音与放音、麦克风问题和排查方法都在[通话语音](call-audio.md)。与基带相关的一点结论是：基带语音服务与 ADSP 的 VCPM 之间通信正常，通话无声的原因曾经在主机一侧的图结构，不在基带。

## 5. 相关事实

- rmtfs 使用 `rmtfs-oplus`，把 `/oem/nvbk/static|dynamic` 映射到 `oplusstanvbk` / `oplusdycnvbk`，以只读（`-r`）运行。`fsg` / `fsc` 分区全为 0。
- 内核实际在 WSL 发行版 `NegroniBuild-Ubuntu-26.04` 的 `/opt/negroni-build/linux` 中构建（Windows 检出的 `linux/` 子模块为空）。那是浅克隆，重建 bundle 时需要让 `GIT_SHALLOW_FILE` 只列出两个前置提交。
- 原始调试脚本与测试镜像放在本地 `logs/modem-qrtr-20261111/`、`logs/volte-20261112/`（不纳入 Git）。
