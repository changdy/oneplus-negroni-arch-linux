# 下拉快捷开关

2026-11-17：Plasma Mobile 6.8.2 的下拉栏已有 Wi-Fi、蓝牙、飞行模式、手电筒和“自动旋转”开关。本机的“自动旋转”控制 KWin 的旋转策略；它不关闭 SLPI，也不代表加速度计、光线、距离等传感器全部断电。光线和距离供自动亮度、贴耳熄屏等功能使用，不能随意与旋转绑在一起关闭。

本项目新增 NFC、GPS 和陀螺仪快捷项。NFC 关闭时卸载 `nxp_nci_i2c`，使 `1-0028` 不再绑定驱动；镜像通过 `blacklist nxp_nci_i2c` 默认阻止自动加载。开启时显式加载模块，读卡和监听仍需对应程序主动运行；若先前的 GPIO 46 中断风暴复发，应立即关闭 NFC。陀螺仪项控制 `negroni-gyro.service` 并持久设置开机状态；默认关闭常驻角速度采样。SMEM 初始化、`hexagonrpcd` 和 `iio-sensor-proxy` 继续服务其他传感器。

GPS 项控制 ModemManager 的 `gps-nmea` 和 `gps-raw` 定位源。开启任一源便会启动 GPS 引擎，两个源都关闭后 ModemManager 停止该引擎；蜂窝基带与通话、移动数据仍继续运行。独立的 QMI/AFW 调试客户端不归 ModemManager 管理，开关不能停止它们。GPS 状态从 ModemManager 实时读取，外部应用启用 GPS 时也会显示“开”。当前系统尚未安装 GeoClue，不能将这个开关当成已经完成的应用定位服务。

三个快捷项由 `configure-desktop.sh` 安装到 `/usr/share/plasma/quicksettings/`。首次登录时 `negroni-desktop-defaults.py` 把它们加入下拉栏，尊重已有的禁用列表；用户之后移除快捷项，不会在下次登录时被重新加回。已有 NFC 和陀螺仪设置的用户仅增加 GPS 项。点击快捷项通过 Polkit 只授权当前本机活动会话运行受限的控制程序。普通状态查询不需要提权。

手工检查命令：

```sh
/usr/local/libexec/negroni-hardware-control nfc status
/usr/local/libexec/negroni-hardware-control gyro status
/usr/local/libexec/negroni-hardware-control gps status
pkexec /usr/local/libexec/negroni-hardware-control nfc toggle
pkexec /usr/local/libexec/negroni-hardware-control gyro toggle
pkexec /usr/local/libexec/negroni-hardware-control gps toggle
```

关闭 NFC 后应检查 `/sys/bus/i2c/devices/1-0028/driver` 不存在，且 `/proc/interrupts` 中的 `nxp-nci_i2c` 不再增长。关闭陀螺仪后应检查服务为 `inactive`、`disabled`，且角速度采样进程退出。

2026-11-17 已在手机上手工部署，并验证 NFC 与陀螺仪均能 `关 → 开 → 关`，最终均为关闭。Qt QML 的状态读取及命令执行路径单独通过；图形会话中实际显示、触控与 Polkit 授权尚未测。见[实机记录](../artifacts/quicksettings-20261117/README.md)。完整镜像未构建、未刷入，重启后的默认状态和节电量未测。

GPS 项同日已手工装到手机，状态正确显示 Satellite 使用的 GPS 为“开”。待它结束定位会话后，实机完成 `关 → 开 → 关`；开启时 ModemManager 同时启用 `gps-nmea` 和 `gps-raw`，关闭后两项均消失，ModemManager 保持 active。图形会话中实际触控、重启后状态和节电量仍未测。
