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
