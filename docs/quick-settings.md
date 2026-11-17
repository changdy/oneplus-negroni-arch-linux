# 下拉快捷开关

2026-11-17：Plasma Mobile 6.8.2 的下拉栏已有 Wi-Fi、蓝牙、飞行模式、手电筒和“自动旋转”开关。本机的“自动旋转”控制 KWin 的旋转策略；它不关闭 SLPI，也不代表加速度计、光线、距离等传感器全部断电。光线和距离供自动亮度、贴耳熄屏等功能使用，不能随意与旋转绑在一起关闭。

本项目新增 NFC、GPS 和陀螺仪快捷项。NFC 关闭时卸载 `nxp_nci_i2c`，使 `1-0028` 不再绑定驱动；镜像通过 `blacklist nxp_nci_i2c` 默认阻止自动加载。开启时显式加载模块，读卡和监听仍需对应程序主动运行。2026-11-17 驱动已修复关闭状态的 GPIO 46 中断风暴，开关重新加载修复版模块通过，仍默认关闭以节省空闲资源；重启和长期功耗未测，见 [NFC](nfc.md)。陀螺仪项控制 `negroni-gyro.service` 并持久设置开机状态；默认关闭常驻角速度采样。SMEM 初始化、`hexagonrpcd` 和 `iio-sensor-proxy` 继续服务其他传感器。

GPS 项控制 ModemManager 的 `gps-nmea` 和 `gps-raw` 定位源。开启任一源便会启动 GPS 引擎，两个源都关闭后 ModemManager 停止该引擎；蜂窝基带与通话、移动数据仍继续运行。独立的 QMI/AFW 调试客户端不归 ModemManager 管理，开关不能停止它们。GPS 状态从 ModemManager 实时读取，外部应用启用 GPS 时也会显示“开”。当前系统尚未安装 GeoClue，不能将这个开关当成已经完成的应用定位服务。

「远程桌面」项启停当前 Plasma 会话的 KRDP。镜像预装 KRDP，开机和登录时默认关闭。开启后使用 KRDP 的默认监听行为，Windows 的 `mstsc` 可连接手机的可达 IP，默认端口为 `3389`。使用手机系统账号认证，首次接入按手机提示授权桌面共享。关闭时当前连接会断开，退出 Plasma 也会停止服务。首次打开时在用户目录生成 TLS 证书和私钥。详见[远程桌面说明](optional-apps.md#krdp-远程桌面实机手工安装)。

四个快捷项由 `configure-desktop.sh` 安装到 `/usr/share/plasma/quicksettings/`。首次登录时 `negroni-desktop-defaults.py` 把新项目加入下拉栏，并读取已有的禁用列表。NFC、GPS、陀螺仪通过 Polkit 授权本机活动会话运行受限控制程序；KRDP 直接启停当前用户的服务。普通状态查询无需提权。

手工检查命令：

```sh
/usr/local/libexec/negroni-hardware-control nfc status
/usr/local/libexec/negroni-hardware-control gyro status
/usr/local/libexec/negroni-hardware-control gps status
pkexec /usr/local/libexec/negroni-hardware-control nfc toggle
pkexec /usr/local/libexec/negroni-hardware-control gyro toggle
pkexec /usr/local/libexec/negroni-hardware-control gps toggle
systemctl --user status app-org.kde.krdpserver.service
```

关闭 NFC 后应检查 `/sys/bus/i2c/devices/1-0028/driver` 不存在，且 `/proc/interrupts` 中的 `nxp-nci_i2c` 不再增长。关闭陀螺仪后应检查服务为 `inactive`、`disabled`，且角速度采样进程退出。

2026-11-17 已在手机上手工部署，并验证 NFC 与陀螺仪均能 `关 → 开 → 关`，最终均为关闭。Qt QML 的状态读取及命令执行路径单独通过；图形会话中实际显示、触控与 Polkit 授权尚未测。见[实机记录](../artifacts/quicksettings-20261117/README.md)。完整镜像未构建、未刷入，重启后的默认状态和节电量未测。

GPS 项同日已手工装到手机，状态正确显示 Satellite 使用的 GPS 为“开”。待它结束定位会话后，实机完成 `关 → 开 → 关`；开启时 ModemManager 同时启用 `gps-nmea` 和 `gps-raw`，关闭后两项均消失，ModemManager 保持 active。图形会话中实际触控、重启后状态和节电量仍未测。

2026-11-18 在手机上用临时用户服务和独立端口测试 KRDP 项。QML 连续两轮完成 `关 → 开 → 关`，关闭后端口消失。移除早期的 USB 固定监听后，在手机的独立网络命名空间确认新版监听 `*:3389` 并接受非 USB 地址上的 TCP 连接。下拉栏触控、新配置上的 Windows 登录与共享授权，以及新镜像启动未测。

## 其他候选

- **充电限制**适合长期接 USB 或使用扩展坞时快速启停。面板应区分「已开启，正在充电」「已停充」和「错误」，并提示开启期间系统会阻止挂起。[充电限制](charge-limit.md)
- **CPU 均衡 / 性能**适合经常跑基准测试或串流时临时切换。应读取实际策略，关闭后恢复均衡。[CPU 性能模式](cpu-performance.md)
- 临时防休眠、热点、截图和录屏已有 Plasma Mobile 快捷项，可在下拉栏编辑界面调整顺序。
