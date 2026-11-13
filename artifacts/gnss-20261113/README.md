# NE2210 GNSS：卫星接收与 XTRA 辅助

2026-11-13，USB SSH，内核 `7.3.0-sm8450+`。原始日志、原厂配置和源码 clone 在本地 `logs/gnss-20261113/`，不提交固件、辅助星历文件或位置数据。

## 已验证

- 手机本次启动约 5 分钟时，ModemManager 和 GNSS 解锁服务已 active，引擎锁为 none；本轮没有执行手机重启。
- 辅助数据刷新前的 180 秒测试收到真实 GLONASS 信号，1 颗进入 TRACK，有效 C/N₀ 约 28 dB-Hz；没有有效位置报告。相较 11-12 的全部 SEARCH，现已证实部分射频接收可用。
- 时间注入、XTRA 更新后的 300 秒接收测试最多同时跟踪 2 颗卫星，采样中的有效 C/N₀ 峰值 34.8 dB-Hz；收到 299 份卫星、300 份位置状态报告，仍没有坐标。接收条件和卫星几何未控制，不能把 C/N₀ 变化归因于星历更新。
- 随后 high accuracy + full power 测试 300 秒，最多同时 TRACK GPS、QZSS、GLONASS 各 1 颗；收到 299 份卫星、301 份位置状态、2406 份 NMEA 报告，仍无有效定位。Stop 成功，结束后没有持续测试 session。先后测试不是同条件对照，不能断言差异由功率策略造成。

## 新接口与辅助数据

旧 `GetPredictedOrbitsDataSource (0x36)` 在 AFW 注册前后、Master 注册后都只有请求响应，没有对应 indication。高通公开 API 中的 `QueryXtraInfo (0xb0)` 可返回地址；实测仅 AFW 注册即可使用，无须 Master。

基带返回 3 个 HTTPS 地址，文件为 `xtra3Mgrbej.bin`。下载时保留系统证书校验；本次文件 61970 字节，sha256 为 `c90decb41b62358aa99c435977f3b2adda0b7e62c7b49c4e2aeeecb746ee1e65`。

`InjectXtraData (0xa7)` 按 1024 字节分成 61 片，逐片响应与 indication 成功，最后一片确认号为 61。随后查询有效期为 `2026-11-12T22:00:00Z` 起 168 小时，即至 `2026-11-19T22:00:00Z`（北京时间 11-20 06:00）。原有数据曾显示从 11-06 起仅有效 72 小时，已过期。

[gnss-assist.py](../../scripts/gnss-assist.py) 已在手机原生执行：HTTPS 下载、全部分片确认、有效期检查和缓存跳过通过，安装在 `/usr/local/libexec/negroni-gnss-assist.py`，手动调用；未安装自动刷新服务。

工具要求系统 NTP 已同步；UTC 注入字段为毫秒，有效期字段为秒。仅建立独立 AFW 客户端，完成后关闭 socket，不开启持续搜星，也不修改 NV/RF 或固件。

## 官方源码与原厂配置核对

| 来源 | 固定版本与发现 |
| --- | --- |
| OnePlus 官方 Android 内核 | [2953daac](https://github.com/OnePlusOSS/android_kernel_oneplus_sm8450/tree/2953daac4fd6da6ff95460d8df44c44976b16ed8)，Android 14；GNSS 目录只有通用/串口类驱动，没有发现 SM8450 专用驱动 |
| OnePlus 官方模块、DTS | Android 12.1 `42180e1e`、14 `92531016`、15 `877203a7`；已查 `wly-20846`、`waipio` 与相关 PMIC 文件，未找到明确 GNSS/ELNA 控制项。WLY DTS 的项目号包括本机 20846 |
| 高通定位协议 | [location-apis-qcom aa950a78](https://github.com/qualcomm-linux/location-apis-qcom/tree/aa950a783a4b8fbb41807bab4d840d44643878a9)，`location_service_v02.h/.c` 定义身份、XTRA 查询、分片注入与有效期单位 |
| 高通 HAL | [location-hal-qcom cecac263](https://github.com/qualcomm-linux/location-hal-qcom/tree/cecac263bde2574fa5376782d2d7e056fea8cf42)，用于对照启动与配置；API 的 `LocApiV02.cpp` 中普通高精度请求显式设置 high accuracy，可选择 full power |
| 本机原厂文件 | `android-ro/vendor_b` / `odm_b` 下的 gps/izat 配置、GNSS HAL 和 rfs 布局；只读核查，未整体复制到 Linux 的服务路径或写入基带 |

对 tqftpserv 在一次搜星窗口内抓取文件系统调用，未发现新请求；开机日志只有 `ota_firewall/ruleset` 不存在。这个窗口不能排除启动时、缓存中或其它远程文件服务的问题。

只读 `GetConstellationControl (0xbf)` 查询显示 GPS 为 mandatory enabled，GLONASS、北斗、QZSS、Galileo 均 internally enabled，NavIC internally disabled；未发现“只启用了 GLONASS”的配置。没有修改星座控制或多频 NV。

## 诊断工具修正

[probe.py](../gnss-20261112/probe.py) 修正有效位置判定：坐标是 TLV 0x10/0x11，0x13/0x14 是不确定度轴，不能用来判断坐标存在。只有 session status=SUCCESS 且两个 8 字节坐标字段都存在时才记为有效定位。之前报告均 IN_PROGRESS，所以此修正不改变 11-12 的无定位结论。

新增 `--full-power`，仅针对测试自己的 session 请求 high accuracy 与非 DPO 全功率；结束仍只停止自己的 session。

主机协议回归覆盖有效期单位、URL 长度前缀、TLS 降级拒绝、TLV 截断/重复、indication 先到、分片确认和错误的坐标判定。模拟检查不能替代实机接收与室外定位验证。

`bash scripts/check.sh`、7 项 GNSS 协议回归、文档链接与 `git diff --check` 通过。结束时 ModemManager、GNSS 解锁、81voltd 和通话音频服务均 active，未重新拨测电话。

开阔天空、真实坐标、首次定位耗时、导航、SUPL、完整镜像和自动刷新尚未验证；不可将本次结果写成“GPS 已完全修复”。

## 窗边条件下的进一步排查

用户明确手机位于窗边；不能将“室内”直接当成故障结论。后续测试仍未得到有效位置，先前最多 3 颗 TRACK 的结果也没有稳定保持。

- 只读 `GetOperationMode (0x4b)` 返回 Standalone=4，未处于依赖服务器计算坐标的 MSA 模式。
- `GetBlacklistSv (0xb7)` 返回的 GLONASS、BDS、QZSS、Galileo、SBAS、NavIC 六个掩码均为 0；本次响应没有 GPS 黑名单字段。`GetMultibandConfig (0xe1)` 返回 `0x1d`，没有修改这些配置。
- 600 秒射频记录中得到 600 份频段报告、602 份位置状态，仍无坐标；39 份定时摘要的 USB carrier 均为 1。24 份摘要的 L1/L5 PGA 为 -12/-12 dB，后 15 份变为 +4/+6 dB。增益在没有拔线的情况下恢复，不能凭低增益断言 USB 干扰或硬件损坏。拔线对照**未测**；后来 Wi-Fi SSH 不可用，未断开 USB 调试通道。
- 按高通 `LocApiV02::setSvMeasurementConstellation()` 增加 `0x88` 报告配置后，180 秒实验确实收到 1790 份 `0x86` 测量报告。随后用仓库工具复测 180 秒，同样收到 1790 份测量、180 份频段、180 份位置状态及 179 份卫星报告，仍无坐标。输出的 120 份按星座/频段抽样摘要中，卫星测量数组数量均为 0；这不是已经解出坐标、上层没显示的证据。
- GPS/QZSS 的时间来源为 EXTERNAL_INPUT=3，其它星座为 TIME_TRANSFORM=10，说明报告反映了外部注入/转换的时间；不能据此宣称已经从卫星确认时间。固件未提供可选 `agc_status (0x43)`，不能将缺省当成“未饱和”。

[probe.py](../gnss-20261112/probe.py) 现在支持：

```sh
python probe.py --duration 180 --full-power --rf-metrics --measurements
```

`--measurements` 在订阅 `0x01000000` 后发送 `SetGNSSConstellationReportConfig (0x88)`，仅启用报告；不会改变星座的启用状态。退出时先清除测量报告配置，再 Stop 自己的 session。普通定时结束的两个请求及 indication 均已成功；另用 `timeout --signal=TERM 5s` 实测 SIGTERM 路径，报告配置清除及 Stop 均成功，没有遗留测试进程。

`0xce` 的 PGA 按有符号 dB 解码，其 BP I/Q 和 jammer 保留原始整数；`0x86` 的 AGC/BP 则有明确的 0.01 dB 协议单位。工具只摘要计数、增益、时间来源和 C/N₀，不输出坐标、伪距或卫星时间。新增回归覆盖有符号增益、缩放、测量有效位、缺省状态、截断数组及配置 indication 在 ACK 前后到达/失败的处理，共 10 项协议检查。

## SUPL 数据连接线索

当前普通 Internet bearer 已连接，实际为 `ctnet` / IPv4，另有独立 IMS bearer；没有改动或断开它们。配置的服务器为 `supl.google.com:7275`，本次从手机直接测试 IPv4 TCP 连接在 4 秒内超时，IPv6 无可用路由。这只描述当前可达性，没有验证 TLS 或 SUPL 交互，也不能证明该服务器永久不可达。

高通 [LocApiV02.cpp](https://github.com/qualcomm-linux/location-apis-qcom/blob/aa950a783a4b8fbb41807bab4d840d44643878a9/loc_api/loc_api_v02/LocApiV02.cpp) 的 `atlOpenStatus()` / `atlCloseStatus()` 使用 `InformLocationServerConnStatus (0x53)` 回复 `LocationServerConnectionReq (0x31)`；已查 ModemManager 1.24.2 `mm-shared-qmi.c` 的 LOC 路径只有模式切换，没有这套连接请求处理。仅切换 MSB 不等于在线辅助已经可用。

独立 AFW 客户端的短测中，切换 MSB=2 后收到 OPEN 请求（WWAN type=AGNSS），复用已连接的普通 IPv4 bearer 并按公开 IDL 回复 `0x53`，响应和 indication 均成功；随后收到 CLOSE 请求并确认，没有关闭共享移动数据。这验证了连接握手，未验证 SUPL 数据成功下载或辅助定位成功。没有改服务器、证书策略、RF/NV 或固件。

该轮持续 120 秒，收到 120 份位置状态、119 份卫星和 953 份 NMEA 报告，仍无有效坐标。结束时 Stop 成功，恢复 Standalone=4 并再次只读确认。ModemManager、解锁服务、`negroni-81voltd` 和通话音频服务均 active；`mmcli --location-status` 中持续 GPS 已关闭，移动数据 bearer 保持连接，未重新拨测通话。

本轮未执行手机重启、刷写分区或服务重启。10 项 GNSS 协议检查、仓库 `scripts/check.sh`、修改文档的相对链接和 `git diff --check` 通过。接收性能、SUPL 端到端交互和真实坐标仍未解决。
