# 一加官方相机源码核查（2026-11-13）

离线读取官方公开仓库，未连接或启动手机相机，未改动驱动或镜像。原始源码缓存放在 `logs/camera-source-20261113/`，本目录仅保存整理结果。

## 仓库与版本

- [android_kernel_oneplus_sm8450](https://github.com/OnePlusOSS/android_kernel_oneplus_sm8450)：原厂 Android 内核主体。
- [android_kernel_modules_and_devicetree_oneplus_sm8450](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8450)：相机、音频、显示、视频、WLAN 等内核模块和设备树。
- 本次相机文件固定在 `877203a7cf9b79973d44a9db716490f95d820110`，与项目既有下游音频研究使用的快照相同。仓库默认分支为 `oneplus/sm8450_v_15.0.0_oneplus_10_pro`。2026-11-13 已核正本机原厂版本为 `NE2210_15.0.0.401(CN01)`，本机保留的 `my_manifest_b` 也直接记录该版本，见[原厂资料核查](../../docs/stock-hardware.md)。公开源码同属 15 系列，仍不能据此宣称与本机所有二进制逐项一致。

## 本机项目与 JN1 硬件

[wly-20846-camera-waipio-overlay.dts](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8450/blob/877203a7cf9b79973d44a9db716490f95d820110/vendor/qcom/proprietary/camera-devicetree/oplus/wly-20846-camera-waipio-overlay.dts#L13) 包含 `wly_20846_camera_overlay_common.dtsi`，项目列表包含 `20846`，量产硬件版本列表包含 T0 到 PVT1。不要混用同目录的 EVB / preT0 文件。

[common.dtsi 第 210–247 行](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8450/blob/877203a7cf9b79973d44a9db716490f95d820110/vendor/qcom/proprietary/camera-devicetree/oplus/wly_20846_camera_overlay_common.dtsi#L210) 明确注释 `wide JN1`，其节点为 `qcom,cam-sensor1`：

| 项目 | 原厂源码声明 | 当前主线实验配置 |
| --- | --- | --- |
| PHY | `csiphy-sd-index = <2>` | CSIPHY2 |
| CCI | `cci-master = <1>` | CCI I²C bus 1，对应当前 Linux bus 6 |
| MCLK 引脚 | GPIO101，MCLK1 | MCLK1 |
| reset 引脚 | GPIO24；`gpio-reset = <1>` 指向 GPIO 列表第 2 项 | GPIO24，主线使用低有效 GPIO 描述 |
| I/O 电源 | L2C，1.8 V | PM8350C L2 |
| 模拟电源 | L3J，2.8 V | PM8010J L3，2.8 V |
| 数字核电源 | L1J，源码目标 1.05 V | PM8010J L1，1.056 V；与源码声明的差异保留记录 |
| DT 时钟默认值 | 19.2 MHz | 24 MHz |
| 安装角度 | roll 90°，pitch 0°，yaw 180° | V4L2 rotation 90° |
| EEPROM | `eeprom_rear_1` | 当前 DT 的只读 `eeprom@51` |

原厂 EEPROM 节点位于同文件第 177 行起，使用同组电源、MCLK1、GPIO24。原厂 `gpio-reset` 是索引属性，不能单凭该数值推断主线 GPIO 极性。

## 寄存器表与时钟

[cam_sensor_settings.h 第 8295–8603 行](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8450/blob/877203a7cf9b79973d44a9db716490f95d820110/vendor/qcom/opensource/camera-kernel/drivers/oplus/cam_sensor_module/cam_sensor/cam_sensor_settings.h#L8295) 的 `s5kjn1sq03_setting` 含 299 条写寄存器记录。调用者 [oplus_cam_sensor_core.c 第 514 行](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8450/blob/877203a7cf9b79973d44a9db716490f95d820110/vendor/qcom/opensource/camera-kernel/drivers/oplus/cam_sensor_module/cam_sensor/oplus_cam_sensor_core.c#L514) 将其用于 ID `0x38e1` 的 FTM（工厂测试）路径。不能把它称为正常相机应用的全部配置。

选定寄存器的静态对照如下，主线值来自本机 WSL 内核 `drivers/media/i2c/s5kjn1.c` 的 4080×3072 模式；未在手机应用原厂表。

| 寄存器 | 原厂 FTM | 当前主线模式 |
| --- | --- | --- |
| `0x034c` 输出宽 | `0x0ff0`（4080） | `0x0ff0` |
| `0x034e` 输出高 | `0x0c00`（3072） | `0x0c00` |
| `0x0900` | `0x0122` | `0x0122` |
| `0x0136` | `0x1300` | `0x1800` |
| `0x0304` | `0x0003` | `0x0004` |
| `0x0306` | `0x0083` | `0x008c` |
| `0x030e` | `0x0003` | `0x0004` |
| `0x0310` | `0x00c0` | `0x0092` |
| `0x0312` | `0x0001` | `0x0000` |
| `0x0340` 帧长 | `0x0c54` | `0x10c0` |
| `0x0342` 行长 | `0x1700` | `0x1100` |

`cam_sensor_util.c` 的 [SENSOR_MCLK 分支](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8450/blob/877203a7cf9b79973d44a9db716490f95d820110/vendor/qcom/opensource/camera-kernel/drivers/cam_sensor_module/cam_sensor_utils/cam_sensor_util.c#L2035) 会用非零 `power_setting->config_val` 覆盖 DT 时钟值（第 2077 行起）。因此 DT 的 19.2 MHz 不是正常拍摄时最终时钟的充分证据，时钟及 PLL/帧时序应整体核查。

## 正常配置与颜色信息的位置

[cam_sensor_core.c 第 189 行起](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8450/blob/877203a7cf9b79973d44a9db716490f95d820110/vendor/qcom/opensource/camera-kernel/drivers/cam_sensor_module/cam_sensor/cam_sensor_core.c#L189) 分别接收 INITIAL_CONFIG、CONFIG、STREAMON 等 packet；第 318–328 行把命令缓冲区交给 I²C command parser。探测信息和上电序列也由命令填入。

这说明原厂正常传感器设置有用户空间下发路径；仅从 kernel DT 无法还原全部相机配置。在已核查的设备树、JN1 FTM 表、传感器核心及 EEPROM 核心文件中，没有找到可直接用于本模组的完整 AWB / CCM / 镜头阴影调校参数。未对所有原厂软件包做穷尽搜索，不能据此断言这些信息永远无法取得。

继续追查颜色应查原厂 camera HAL/传感器组件、`vendor` / `odm` 下的相机 tuning 文件及本机 EEPROM 标定内容，并验证软件版本和模组供应商；EEPROM 读取方式、二进制布局及可用颜色参数在本次均未实测。当前离线白平衡预览仍只是诊断结果，不能替代这些调校数据。

公开的 CSIPHY、CSID680 与 VFE680 寄存器/硬件表也在 `camera-kernel` 中，可用于后续逐项核对启动和停止顺序；本次没有据此改变现有重启故障的结论。
