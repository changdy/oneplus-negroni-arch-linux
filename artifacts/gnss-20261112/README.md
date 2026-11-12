# NE2210 GNSS：2026-11-12

USB SSH 实测，内核 `7.3.0-sm8450+`。原始日志保存在本地 `logs/gnss-20261112/`，这里不保存坐标、基站信息或固件副本。

## 对照结果

| 引擎锁 | 客户端注册 | 结果 |
| --- | --- | --- |
| all | 原版 qmicli / ModemManager | Start：GeneralError (46)；卫星事件注册：InvalidArgument (48) |
| none | 原版 | 仍然失败，排除“只需清锁” |
| none | Register Events 带 AFW，再 Start | 两项成功，收到 NMEA、卫星、位置状态报告；Stop 成功 |
| all | 同样 AFW 注册 | 注册成功，Start 失败；位置状态 ENGINE_LOCKED (7) |

AFW 注册使用 QMI LOC 0x0021，事件 mask、客户端字符串、类型 AFW=1、通知 false。没有使用 PRIVILEGED 类型。实现依据是[高通公开接口](https://github.com/qualcomm-linux/location-apis-qcom/blob/aa950a783a4b8fbb41807bab4d840d44643878a9/loc_api/loc_api_v02/location_service_v02.h)和 [libqmi 上游修复](https://github.com/linux-mobile-broadband/libqmi/commit/532de37e84dac82936b056e28fb71ce4c7af60d6)。

## 接收状态

用户确认手机在室内、距窗不远。最后一轮有界测试持续 180 秒，收到 180 份卫星报告、181 份位置状态报告、900 份 NMEA 报告。列出了 69 个搜索目标：GPS 16、QZSS 3、GLONASS 8、北斗 26、Galileo 16。全部 SEARCH，没有 TRACK，也没有有效 SNR 字段；NMEA GGA quality=0、GSA type=1。这个结果只证明引擎开始搜索、报告通路恢复，不能认定天线接收或定位可用。

卫星报告使用 expandedSvList（TLV 0x11），不是旧版 libqmi 只建模的 svList（0x10）。只查看旧字段可能漏掉这些信息。

## 有界诊断工具

将 [probe.py](probe.py) 放到手机，确保解锁服务已成功，然后执行：

```sh
python probe.py --duration 180
```

工具从 `qrtr-lookup` 自动发现节点 0 的 LOC 端口，建立独立 socket，注册 AFW 并启动自己的 session 222。每 15 秒只打印星座计数、TRACK 数量、有效 C/N₀ 数量和是否得到有效位置报告；不打印坐标。正常退出、Ctrl+C 或异常时会尝试停止本次 session，不停止 ModemManager 的 session。`--duration` 范围为 1–1800 秒。

修改 engine lock、固件、辅助数据和 NMEA 输出类型均不在该工具的操作范围内。搜索目标数量会随环境/时间变化，不能作为定位通过标准。

## 来源与验证边界

- OnePlus Android DTS：`OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8450`，提交 `877203a7cf9b79973d44a9db716490f95d820110`，本地已有 clone。对照 `kernel_platform/qcom/proprietary/devicetree/qcom/waipio*`、PMIC DTS 和 `oplus/*20846*`，未找到明确 GNSS/ELNA 配置，未改引脚。
- 固件：沿用当前手机原厂 `modem_b`，`modemr.jsn` 包含 `gps/gps_service`；主线 qcom_pd_mapper 的 SM8450 表已有相应服务。
- libqmi：1.38.0 + 上游身份 TLV 补丁，native aarch64 编译，5/5 上游测试通过。
- ModemManager：1.24.2 + AFW 注册顺序补丁，native aarch64 编译，实测 GPS 开关和 DBus NMEA 数据。部署来源见 [sources.txt](../../config/gnss/sources.txt)。
- 未测：开阔天空、真实信号与坐标、A-GPS、导航、无 SIM、完整重启、完整镜像构建。

部署、回退和当前状态见 [GNSS 说明](../../docs/gnss.md)。
