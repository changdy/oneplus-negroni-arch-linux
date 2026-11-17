# GPS / GNSS

2026-11-17 已将 GPS 开关接入 Plasma Mobile 下拉栏和镜像安装，并手工部署到手机。开关仅控制 ModemManager 的 `gps-nmea` / `gps-raw` 定位源，关闭两项会停止它管理的 GPS 引擎，不停止蜂窝基带或独立 AFW 调试客户端。手机状态查询已识别 Satellite 正在使用的 `gps-nmea` 为“开”；为避免中断该会话，本轮未在手机上执行关开往返。图形触控、重启后的默认状态与节电量未测，见[快捷开关](quick-settings.md)。

Satellite 退出后补测下拉开关的控制程序：GPS `关 → 开 → 关` 通过。开启时 `gps-raw` 和 `gps-nmea` 均出现在 ModemManager 的 enabled 列表，关闭后只剩蜂窝定位源；ModemManager 服务保持 active。此为命令路径实测，图形触控仍未测。

状态日期：2026-11-14，NE2210，内核 `7.3.0-sm8450+`。11-14 仅复核日志并做了一次 150 秒射频采样，见“干扰状态复核”。

**已修复定位引擎无法启动，2026-11-13 已收到并跟踪真实卫星信号，尚未获得有效坐标。** 用户空间修复已部署到本机，另已补齐手动刷新时间/辅助星历的工具；没有修改内核或刷写分区，调试期间未执行手机重启；2026-11-15 已把已验证的启动修复接入镜像构建，新完整镜像未构建、未刷入。

## 已确认的问题

本机 GNSS 由原厂 MPSS 固件实现，通过 QRTR 的 QMI LOC 服务（服务 16、版本 2、节点 0）提供接口。ModemManager 1.24.2 已能识别 `gps-raw` / `gps-nmea`，不需要先出现 `/dev/gnss0` 才能使用。

启动有两道独立阻塞：

1. 本次开机引擎锁为 `all`。清锁后必须继续处理客户端注册，单独清锁仍无法启动。
2. 原版 libqmi 1.38.0 的 Register Events 不携带客户端身份，固件将其视为 NFW；事件注册返回 `InvalidArgument (48)`，Start 返回 `GeneralError (46)`。ModemManager 还在 Register Events **之前**发送 Start。

高通公开 [location_service_v02.h](https://github.com/qualcomm-linux/location-apis-qcom/blob/aa950a783a4b8fbb41807bab4d840d44643878a9/loc_api/loc_api_v02/location_service_v02.h) 定义了身份字段。libqmi 上游已有对应[提交 532de37](https://github.com/linux-mobile-broadband/libqmi/commit/532de37e84dac82936b056e28fb71ce4c7af60d6)，但手机的 1.38.0 包尚未包含。

本地方案：

- [libqmi-afw.patch](../config/gnss/libqmi-afw.patch)：原样回移上述上游提交，增加 TLV `0x10`（客户端字符串）、`0x11`（AFW=1）、`0x12`（通知开关）。
- [modemmanager-afw.patch](../config/gnss/modemmanager-afw.patch)：以 `MM` / AFW 注册 NMEA 事件，收到成功响应后才启动引擎；沿用现有停止路径、PDS 路径和定位权限控制。
- [negroni-gnss-unlock.service](../config/gnss/negroni-gnss-unlock.service)：随 ModemManager 启动清锁，失败每 5 秒重试。清锁不等于开启持续定位，定位仍由客户端请求。

没有使用 `PRIVILEGED` 客户端。程序和库安装在 `/opt/negroni-gnss`，用单独的 systemd drop-in 切换；发行版包文件保留。来源、固定源码版本与部署哈希见 [sources.txt](../config/gnss/sources.txt)。

## 实机结果与剩余问题

- 原版、仅清锁：均不能启动。补充 AFW 注册且清锁后，Register Events / Start / Stop 成功，持续返回 NMEA、卫星与位置状态报告。
- 锁回 `all`，保留 AFW：Start 再次失败，位置状态为 `ENGINE_LOCKED (7)`，证明锁和身份问题彼此独立。
- 已部署的 ModemManager 连续 3 轮通过 `mmcli` 关闭/开启 `gps-raw` / `gps-nmea`，DBus 能读取 5 类 NMEA 句子；移动数据重新连接，81voltd 和通话音频服务保持 active。通话未重新拨测。测试结束已关闭持续搜星，保留按需启用能力。
- 2026-11-12 室内测试没有有效坐标：GGA fix quality 为 0，GSA fix type 为 1。展开的卫星报告列出 69 个搜索目标，状态为 SEARCH；未发现 TRACK，所有条目的 SNR 有效位均未置位。**69 个搜索目标不等于收到 69 颗卫星**，也不能把无效 SNR 字段中的 0 当成实测信噪比。
- 2026-11-13 本次手机启动后，解锁服务已自动成功；180 秒基线测试收到 1 颗 GLONASS 卫星，有效 C/N₀ 约 28 dB-Hz 并进入 TRACK。补充时间和新星历后的 300 秒测试最多同时跟踪 2 颗卫星，C/N₀ 曾到 34.8 dB-Hz；尚无有效坐标。前后时间和卫星几何条件不同，不能将信号变化归因于辅助数据，也不能据此认定天线性能完全正常。
- 随后以 high accuracy / full power 再测 300 秒，最多同时跟踪 GPS、QZSS、GLONASS 各 1 颗，仍无有效位置报告；结束后 Stop 成功。测试条件未控制，不能单凭两轮先后结果认定全功率提高了搜星能力。当前已关闭测试 session 和持续定位。
- 室外开阔天空、首次定位耗时、SUPL 在线辅助、导航、完整定位链冷启动和无卡定位均**未测**。本机尚未安装 GeoClue；桌面应用的定位集成也未测。

现有证据说明射频链路可以接收部分真实信号，但尚未证明接收性能正常。用户确认手机就在窗边，因此继续检查射频增益、测量报告、原厂初始化和辅助连接；不能仅凭室内条件解释本次故障。开阔天空的同软件测试仍有对照价值；天线放大器、供电、原厂校准和固件依赖也尚未排除。不要在没有板级依据时照搬其他 SM8450 手机的 GPIO。

详细对照与不含坐标的诊断工具见[实测记录](../artifacts/gnss-20261112/README.md)。

## 射频与测量诊断

2026-11-13 的进一步长测仍无坐标。600 秒记录中 `usb0` carrier 始终为 1，L1 PGA 曾从 -12 dB 恢复至 +4 dB，L5 从 -12 dB 恢复至 +6 dB。当时据此认为低增益不能证明 USB 干扰；**2026-11-14 复核认为这一推断不成立**：carrier 不反映 USB 链路挂起，而增益恢复的时刻与内核记录的 USB 挂起重合，见下文“干扰状态复核”。拔线对照仍**未测**。

[probe.py](../artifacts/gnss-20261112/probe.py) 新增 `--rf-metrics` 和 `--measurements`，按高通公开 IDL 读取各频段增益、AGC/BP、时间来源与卫星测量数量。后者先发送 `SetGNSSConstellationReportConfig (0x88)`，否则只订阅事件也收不到原始测量报告；退出时清除报告配置并停止自己的定位 session，支持 SIGTERM 清理。

```sh
python probe.py --duration 180 --full-power --rf-metrics --measurements
```

工具按 15 秒间隔输出摘要，不输出坐标、伪距和卫星时间。测量报告的 AGC/BP 按协议的 0.01 dB 缩放，频段报告的 jammer 值保留原始整数，避免在单位尚未确认时套用阈值。当前固件没有提供可选的 `agc_status`，缺省不能解释为“未饱和”。该诊断配置仅用于报告，不改变星座启用状态、RF/NV 或引擎锁。详细次数和辅助连接排查见 [2026-11-13 记录](../artifacts/gnss-20261113/README.md)。

### 干扰状态复核（2026-11-14）

重读 2026-11-13 的原始日志并补一次 150 秒采样后，**当前首要嫌疑是 USB3 SuperSpeed 链路工作时对 GNSS 接收的宽带干扰**，尚未做同条件对照，不能写成已定位。

- **阈值其实有公开依据。** `location_service_v02.h` 的 `QMI_LOC_GET_BAND_MEASUREMENT_METRICS_IND (0xce)` 注释给出参考范围：L1 PGA 标称 0 至 +4 dB、极限 -12 至 +18 dB；GPS L1 BP 幅度标称 160–200、极限 89–356；L5 PGA 标称 -4 至 0 dB。11-13 的“低增益”状态是 L1/L5 PGA 都贴在下限 -12 dB，GPS L1 BP 幅度 402–477，已超出极限；“恢复”后 L1 为 +4 dB、174–178，正好落在标称范围。
- **jammer 字段单位是 0.01 dB。** 同一时刻 `0xce` 的 GPS L1 原始值 7374 与 `0x86` 中按 0.01 dB 解码的 BP 指标 73.74 dB 一致，GLONASS、北斗、Galileo 和 L5 同样逐项吻合。按此换算，GPS L1 该指标在三种状态下约为 56 dB（恢复后）、73–74 dB（中间态）、79–81 dB（饱和态），饱和态比恢复后高约 24 dB，L5 高约 20–23 dB。指标升高与实际 C/N₀ 损失的换算关系未验证。
- **恢复时刻与 USB 挂起重合。** 600 秒记录中最后一个饱和样本在 00:20:35 UTC，第一个正常样本在 00:20:50 UTC；同一时段的内核日志在 08:20:40（北京时间，即 00:20:40 UTC）记录 `dwc3 … remote wakeup not configured` 和 `not armed for func remote wakeup`。这两条是 gadget 在链路已挂起时尝试唤醒主机才会打印的（如 NCM 的 `ether_wakeup_host()` 路径），说明当时 USB 链路进入了挂起，而 `usb0` carrier 仍为 1；这是该小时内唯一一次挂起记录。饱和的 6 分钟内没有跟踪到任何卫星，恢复约 2 分钟后才出现第一颗。
- **此前所有长测都在 USB3 super-speed 下进行。** 正常状态的累计观测只有上述约 3.5 分钟，因此“窗边接收性能异常”还没有在无干扰条件下验证过。
- **2026-11-14 15:15 USB2 口采样**（`high-speed`，内核 `#4`，开机约 3 分钟，屏幕关闭，150 秒）：10 个样本的 L1 PGA 为 -4 至 +2 dB，GPS L1 BP 幅度 151–210、指标 58–62 dB，没有出现 -12 dB；L5 PGA 仍为 -12 至 -2 dB、指标 46.5–56.9 dB，来源未定位。149 份卫星报告均不含卫星列表，无定位。本次开机没有注入时间，手机摆放位置未确认，**不能据此评价灵敏度**，也不是与 USB3 的同条件对照。
- **2026-11-14 16:04 窗边 300 秒**。手机刚重启，USB 仍为 `high-speed`。先注入 NTP 时间并重新下载 XTRA（61956 字节，有效至 `2026-11-21T07:00:00Z`），再以 full power 搜星。L1 PGA 全程 -4 至 +4 dB，GPS L1 BP 幅度 154–202，没有回到 -12 dB；L5 PGA 从 -12 dB 升至 +4 dB。前约 3 分 40 秒没有跟踪，之后持续跟踪 1 颗 GPS L1，C/N₀ 16.8–23.6 dB-Hz。测量里这颗星的星历可用位和码相位时间位都未置位，时间来源仍是外部注入，300 份位置状态无坐标。会话已停止。这证明 USB2 下射频能收到真实卫星，信号强度仍不足以定位；与 USB3 的同位置对照和室外对照仍未做。原始输出在 `logs/gnss-20261114/window-usb2-probe.log`。

内核日志同时显示测试期间 Wi-Fi 每隔几分钟在两个 BSSID 之间来回切换，屏幕和充电状态也没有记录；这些因素尚未排除。下一步应在同一位置、同一次开机内依次对比 USB3 口、USB2 口和拔线（脱机记录到文件）三种状态，并在每次开机后先运行时间/XTRA 注入。原始输出在本地 `logs/gnss-20261113/rf-usb-ab.log`、`logs/camera-20261113/baseline.txt` 与 `logs/gnss-20261114/usb2-highspeed-rf.log`。

## 刷新时间和辅助星历

2026-11-13 找到另一处用户空间缺口：现有 ModemManager 使用 `GetPredictedOrbitsDataSource (0x36)` 探测辅助数据，基带只回复接受请求，不发出对应 indication，因而初始化时超时、未公布辅助数据能力。相同基带支持高通较新的 `QueryXtraInfo (0xb0)` 与 `InjectXtraData (0xa7)`。

[gnss-assist.py](../scripts/gnss-assist.py) 通过独立 AFW 客户端执行这套接口，不需要 Master 或 PRIVILEGED 注册，也不启动定位、改 RF/NV、改引擎锁或上传位置。它会：

1. 确认系统 NTP 已同步，按毫秒注入 UTC 时间。
2. 读取已有星历有效期（该时间戳单位是秒）；剩余不少于 12 小时时跳过下载。
3. 通过 `QueryXtraInfo` 获取基带给出的 HTTPS 地址，用系统 CA 校验证书下载；不降级到 HTTP。
4. 以不超过 1024 字节的分片注入，检查每片响应、indication 状态和片号，最后再次确认有效期覆盖当前时间。

实机已从基带指定的 `path1.xtracloud.net` 下载 61970 字节的 `xtra3Mgrbej.bin`，61 片均成功；新数据从 `2026-11-12T22:00:00Z` 起有效 168 小时。工具正常刷新、强制刷新和有效缓存跳过均通过。它补齐的是 XTRA 预测星历辅助，不代表 SUPL 已实现或定位已通过。

手机已安装手动工具：

```sh
python /usr/local/libexec/negroni-gnss-assist.py
# 在有仓库的手机上，也可以直接执行：
python scripts/gnss-assist.py
# 或安装到同一位置：
sudo install -D -m 0755 scripts/gnss-assist.py /usr/local/libexec/negroni-gnss-assist.py
```

`--force` 强制刷新，`--file PATH` 注入事先下载的文件。工具不会自动常驻或开机执行；基带重新启动后，可在联网且 NTP 同步时手动运行，再通过 `mmcli` 开始定位。完整镜像打包、自动刷新和无网络场景尚未集成。来源和本次接收结果见 [2026-11-13 记录](../artifacts/gnss-20261113/README.md)。

## 构建与启用

以下命令在手机上、仓库根目录执行。需要本机开发工具和依赖，当前已验证 gcc、meson、ninja、pkgconf、glib2-devel、libqmi、libmbim、libqrtr-glib、libgudev、polkit 与 systemd；不必更新整套系统。

```sh
bash scripts/build-gnss-stack.sh

sudo install -d /etc/systemd/system/ModemManager.service.d
sudo install -m 0644 config/gnss/ModemManager.conf \
  /etc/systemd/system/ModemManager.service.d/90-negroni-gnss.conf
sudo install -m 0644 config/gnss/negroni-gnss-unlock.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable negroni-gnss-unlock.service
# 会重连移动数据；先确保没有通话。
sudo systemctl restart ModemManager
sudo systemctl start negroni-gnss-unlock.service

sudo mmcli -m any --location-enable-gps-nmea --location-enable-gps-raw
mmcli -m any --location-status
sudo mmcli -m any --location-get
# 测试结束关闭，避免持续搜星耗电。
sudo mmcli -m any --location-disable-gps-nmea --location-disable-gps-raw
```

注意当前 mmcli 使用 `--location-get`，没有 `--location-get-gps-nmea` 子命令。输出可能包含坐标或基站信息，不要把原始输出提交到 Git。

构建脚本已在本机实际执行通过，部署程序/库的哈希与记录一致；libqmi 的 5 项上游测试均通过，systemd 单元校验通过。ModemManager 的验证以本机编译和实际开关/读取为依据，不宣称完整上游回归或冷启动通过。完整 rootfs 的安装和打包仍未集成，只有原始镜像的软件包不能复现这次修复。

回退（会重连移动网络）：

```sh
sudo mmcli -m any --location-disable-gps-nmea --location-disable-gps-raw
sudo systemctl disable --now negroni-gnss-unlock.service
sudo rm /etc/systemd/system/ModemManager.service.d/90-negroni-gnss.conf
sudo systemctl daemon-reload
sudo systemctl restart ModemManager
```

## Android 内核、DTS 与固件是否有参考意义

有，但要先确定故障在哪一层。Android DTS 对照电源、时钟、复位和引脚很有用；对应驱动能说明寄存器与初始化顺序；原厂固件与配置能说明处理器服务、校准和协议要求。它们不能直接证明只移植 DTS 或驱动就能定位。

已对照 OnePlus 官方 Android 12.1、14、15 分支的 `wly-20846` 和 `waipio` DTS；在这些已查文件中未找到本板明确的 GNSS ELNA 控制配置，没有据此改 GPIO。还拉取并查看了官方 Android 14 内核的 GNSS 驱动目录，里面没有发现 SM8450 专用 GNSS 接收驱动。

手机保留的原厂 vendor/odm 提取目录中有 `gps.conf`、`izat.conf`、`gps.cfg`、`gps_modem.cfg` 和 GNSS HAL。它们用于检查初始化和文件依赖，没有将配置或二进制命令流盲目写入基带。搜星期间对 tqftpserv 的文件调用抓取未发现请求缺失文件，但这不覆盖启动早期或其它文件服务。

2026-11-14 重新核对了本机原厂文件，没有发现被遗漏的 GNSS 内核驱动或射频初始化：

- 373 个原厂模块里，`gnss` / `gps` / `izat` / `xtra` / `elna` 的命中都来自 “initialization”“extra”“blanking” 或 Wi-Fi 的 `eLNA bypass`。`oplus_bsp_rfcablemonitor.ko` 只上报 GPIO89 的射频线缆状态。
- `odm_b/etc/gps.cfg`（1761 字节）和 `gps_modem.cfg`（3825 字节）是二进制文件，没有可解析的配置项。全库只有 `diag_mdlog` 引用这两个路径，定位 HAL 不读它们。
- `odm_b/etc/gps.conf` 的 `RF_LOSS_*` 全部是 0，`libloc_api_v02.so` 对这种情况只打印告警。`gnss_antenna_info.conf` 是高通示例，`ANTENNA_INFO_VECTOR_SIZE` 被注释掉。`DR_SYNC_ENABLED = 0`，原厂不依赖 `/dev/pps0`。
- `izat.conf` 里一加明确关闭了 `lowi-server`、`slim_daemon` 和 `edgnss-daemon`，打开的是 `xtra-daemon`。原厂并没有把 IMU 送进 GNSS。`rfs/apq/gnss` 下没有文件。

原厂 HAL 还会发、而当前 Linux 侧没有发的 QMI 请求主要是：响应 `TIME_SYNC` 指示的 `InjectTimeSyncData`、`SetMinGpsWeekNumber`、`SetXtraVersionCheck`，以及 `AGPS_CONFIG_INJECT` 所覆盖的 SUPL/LPP 配置。这些影响星历能否套到已跟踪卫星和在线辅助，不能解释已经跟踪到的卫星只有约 23 dB-Hz。只读的 `GetSupportedFeature` 还没查过。

真正使 Start 成功、以及补齐辅助数据链路的参考是**高通定位用户空间接口**，并非另一个 GNSS 内核驱动。手机已经加载原厂 `modem_b` 的固件，当前没有证据支持更换固件；也没有下载其它型号的固件覆盖它。

## 镜像交付（2026-11-15）

`configure-gnss.sh` 安装已验证的私有 ModemManager/libqmi、drop-in、解锁服务和辅助工具；对应二进制、来源、许可证和哈希在 [runtime](../config/gnss/runtime/README.md)。不覆盖发行版程序，安装时用 `--version` 检查目标 rootfs 能否加载程序和库。`prepare-rootfs.sh` 显式安装提供 `qrtr-lookup` 的 `qrtr-git`。

`build.sh` 根据 GNSS 源文件指纹调用 `update-feature-image.sh gnss` 更新已有镜像；打包前 `verify-gnss-image.py` 检查内容、权限、动态库链接和服务启用。解锁随 ModemManager 启动，定位仍由客户端请求，辅助下载手动调用，没有开机持续搜星。打包核对通过不代表已经定位，坐标、室外首次定位、新完整镜像启动未测。
