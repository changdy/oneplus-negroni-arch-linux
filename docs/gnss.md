# GPS / GNSS

状态日期：2026-11-12，NE2210，内核 `7.3.0-sm8450+`。

**已修复定位引擎无法启动，尚未验证有效卫星接收和定位。** 修复在用户空间，已部署到本机；没有修改内核、刷写分区或重启手机，也未接入完整镜像构建。

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
- 室内测试没有有效坐标：GGA fix quality 为 0，GSA fix type 为 1。展开的卫星报告列出 69 个搜索目标，状态为 SEARCH；未发现 TRACK，所有条目的 SNR 有效位均未置位。**69 个搜索目标不等于收到 69 颗卫星**，也不能把无效 SNR 字段中的 0 当成实测信噪比。
- 室外开阔天空、天线/射频接收、首次定位耗时、A-GPS、导航、完整重启和无卡定位均**未测**。本机尚未安装 GeoClue；桌面应用的定位集成也未测。

现阶段不能仅凭室内环境解释收不到信号。还需同一套软件在开阔天空测试；如仍全部 SEARCH 且无有效 C/N₀，再排查天线放大器、供电、原厂校准和固件依赖。不要在没有板级依据时照搬其他 SM8450 手机的 GPIO。

详细对照与不含坐标的诊断工具见[实测记录](../artifacts/gnss-20261112/README.md)。

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

本次已利用原有 OnePlus Android 下游仓库，对照 `wly-20846` 和 `waipio` DTS；尚未从这些文件找到本板明确的 GNSS ELNA 控制配置，没有据此改 GPIO。真正使 Start 成功的参考是**高通定位用户空间接口**，并非另一个 GNSS 内核驱动。手机已经加载原厂 `modem_b` 的固件，当前没有证据支持更换固件；也没有下载其它型号的固件覆盖它。
