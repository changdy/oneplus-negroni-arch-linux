# 原厂系统残留与硬件驱动分析

核查日期：2026-11-13。通过 USB SSH 连接本机 OnePlus 10 Pro NE2210；USB 短时断连后改用用户提供的 Wi-Fi SSH。**原厂系统的驱动、板级配置和相机调校资料仍有大量保留，可以继续用于主线 Linux 移植。** 本轮只读分区、解包文件并离线分析，没有刷写、重启、切槽或修改 USB 角色，也没有启动相机、录音或定位测试。

## 原厂内容在哪里

| 位置 | 实际发现 | 可用于什么 |
| --- | --- | --- |
| `super`（10.5 GiB） | 两组逻辑分区元数据，以及 vendor / odm / system / vendor_dlkm 等内容；存在 Virtual A/B COW 条目 | 提取原厂 HAL、配置、模块和版本信息；本轮没有合并快照 |
| `~/android-ro/vendor_b`、`odm_b` | 此前已提取的目录与镜像；相机、音频、GNSS、传感器配置仍可读 | 查初始化依赖、音频路由、颜色参数和固件文件名 |
| `vendor_dlkm_b` | 本轮从 super 的 slot 1 元数据提取，离线解包得到 **373 个 `.ko`** | 查编译版本、依赖、函数符号，反汇编对照公开源码 |
| `dtbo_a` | 有效 DTBO，12 个 overlay；量产候选 0 / 11 的项目列表包含 **20846** | 对照实际板级引脚、电源、CSI 和面板命令；还需结合硬件版本选择 overlay |
| `vendor_boot_a`、`boot_a` | 原厂格式 vendor boot，含 4 个基础 DTB；A 槽内核字符串为 `5.10.209-android12-9-o-g3b3e35ff8a20` | 分析基础 DT、ramdisk 和原厂内核逻辑 |
| `modem_b`、`bluetooth_b`、`persist` | 当前固件加载器已只读挂载 | 当前 Linux 仍在使用原厂固件或设备数据；本轮没有更改这些内容 |

2026-11-13 已按用户要求将完整模块文件树复制到工作区 `downloads/stock-drivers-20261113/vendor_dlkm_b/`，模块位于其 `lib/modules/`。共 373 个 `.ko`，连同加载清单、依赖与分区元数据共 382 个文件、160,304,370 字节（152.88 MiB），逐文件与手机上的提取目录核对大小和 SHA-256。目录根部附 `README.md`、`inventory.csv`、`inventory.json` 和 `SHA256SUMS`。用户随后明确授权纳入 Git 并推送，现为 `downloads/` 忽略规则的精确例外，使用 binary 属性保留原厂文件字节；其他下载产物仍忽略。手机及 logs 中的来源文件保留，没有安装这些原厂模块。

本轮 qbootctl 只读结果：B 槽 Active / Successful / Bootable 均为 1；A 槽 Successful=1、Active=0、Bootable=0。**保留原厂文件不表示 A 槽能够启动 Android**。`userdata` 现在是 Linux 根文件系统，不能从本次发现推断旧 Android 用户数据仍在或能够恢复。

## 版本已有手机自身证据

从 `my_manifest_b` 的 EROFS 文件系统提取 `build.prop`，读到：

- `ro.build.display.id=NE2210_15.0.0.401(CN01)`。
- `ro.build.display.full_id=NE2210domestic_11_15.0.0.401(CN01)_2025010701470186`。
- `ro.build.version.ota=NE2210_11.H.82_3820_202501070147`。
- Android 15 的整机、vendor、odm fingerprint 注入条目。

这与用户回忆及 2026-11-11 刷机日志吻合。单看 `vendor_b/build.prop` 中的 Android 12 / SDK 32，或 `odm_b/build.prop` 的 `NE2210_11_A.01`，会误判整机版本；`my_manifest_b` 另有上述版本和 fingerprint 条目。

A 槽内核的编译日期为 2025-03-10，B 槽 manifest 记录的整机包日期为 2025-01-07；两槽资料不能当作同一个更新包。模块 vermagic 为 `5.10.209-gki-gac3f956b8fca`，也不能据此宣称某个公开源码快照与所有二进制完全一致。

版本术语：这批资料对应的系统标识是 **ColorOS 15 / Android 15**；**Linux 5.10.209** 是原厂内核/模块的版本，当前主线系统内核为 Linux 7.3。此前“Android 5.10”的表述不准确。内核名中的 `android12-5.10` 代表内核分支来源，不能据此把整机判为 Android 12；[AOSP 兼容表](https://source.android.com/docs/core/architecture/kernel/android-common#compatibility-matrix)明确列出 Android 15 支持 `android12-5.10` 和 `android13-5.10`。

## 已取得的具体驱动线索

### 相机

ODM 的 `lib64/camera` 中保留四组传感器组件：IMX789、S5KJN1SQ03、OV08A10、IMX615，分别还有模组配置和 tuning 文件。这是原厂软件支持的硬件配置证据；本轮没有逐个通电读 ID，不能等同四颗传感器都已实测。

JN1 资料包括：

- `com.qti.sensormodule.waipio.qtech_s5kjn1sq03.bin`（730,626 字节）：有 `QTI Chromatix Header`，不是明文寄存器 XML，需继续解码其结构。
- `com.qti.sensor.s5kjn1sq03.so`（23,856 字节）：ARM64 ELF，导出 `GetSensorLibraryAPIs`；已生成离线反汇编，可继续追踪注册的曝光、增益与寄存器填充回调。
- `com.qti.tuned.qtech_s5kjn1sq03.bin`（10,821,904 字节）：原厂 tuning 负载已找到，但本轮未完整解码 AWB / CCM / LSC 等结构。
- `etc/camera/dng/ColorMatrix1_s5kjn1sq03_2.txt`、`ColorMatrix2_s5kjn1sq03_2.txt`：两份可读的 3×3 矩阵，另有色相/饱和度映射和 ToneCurve 文件。这些为色彩分析提供了实物依据；矩阵方向、参考光源和使用流程还需核对，不能直接乘到显示 RGB 上就称为完成标定。
- `etc/camera/config/s5kjn1sq03`：`SENSOR_PHYSICAL_ID=2`，`NIGHT_SCENE_SENSOR_BAYER_PATTERN=3`，文件注释将 3 定义为 GBRG。当前主线色条已经按 GRBG 验证；原厂字段可能对应不同模式、镜像或后处理阶段，**本轮没有据此改动当前 RAW 解码相位**。

实际 DTBO 的量产候选再次确认 JN1 使用 CSIPHY2、CCI master 1、MCLK1/GPIO101、reset GPIO24，以及 1.8 V / 2.8 V / 约 1.05 V 电源；DT 默认时钟为 19.2 MHz。正常拍摄的最终时钟和寄存器序列还受用户空间命令影响，不能只移植这个 DT 默认值。相机重复开启硬重启的原因本轮没有验证或修复，见[相机说明](camera.md)。

### 麦克风与音频

本机原厂 `mixer_paths.xml` 再次确认 `handset-mic` / `speaker-mic` 选择 `MSM_DMIC`：DEC0 接 DMIC3，DEC1 接 DMIC4，开启 TX_AIF1 capture，音量 84。实际 DTBO 中 TX DMIC 采样时钟配置为 2.4 MHz、VA 为 600 kHz。

新提取的 `lpass_cdc_dlkm.ko` 保留 `lpass_cdc_dmic_clk_enable` 函数符号；`lpass_cdc_tx_macro_dlkm.ko` 引用它，模块另有 `audio_prm_dlkm`、VA macro 和 LPI pinctrl。这让后续能用本机编译产物检查共享 DMIC 时钟、TX/VA 分频和资源申请路径，而不只依赖网上的同型号源码。模块存在不能证明当前 GPIO8 已有时钟，内置麦克风无信号的问题仍未解决，见[通话语音](call-audio.md)。

### 原生屏幕分辨率

实际 DTBO 的 `samsung_amb670yf07_1440_3216_dsc_cmd` 面板节点同时保存两组模式：

| 模式 | 刷新率条目 | DSC 分块宽×高 | 每包 slice 数 | 压缩 bpp / DSC 版本 |
| --- | --- | --- | --- | --- |
| 1080×2412 | 60 / 90 / 120 Hz，另有 Oplus 120 Hz | **540×36** | 2 | 8 / 1.2 |
| 1440×3216 | 60 / 90 / 120 Hz，另有 Oplus 120 Hz | **720×24** | 2 | 8 / 1.2 |

这补足了当前主线面板驱动固定 540×36 的对照依据。后续还要核对各模式 PPS、面板初始化/切换命令、DSI 时序和带宽，再做实机验证；本轮没有切换显示模式，不能称为原生分辨率已修复，见[显示说明](gpu.md)。

## 当前硬件观察与验证边界

本轮读到 SM8450 / SoC ID 457；I²C 已绑定 Synaptics S3908、NXP NFC、两颗 TFA9874、FSA4480 和 S5KJN1；两个 Hall 节点与相机 EEPROM 节点没有 driver 绑定。绑定状态只说明 Linux 当前识别情况，不是对每颗硬件功能的验收。SLPI / ADSP / CDSP / modem 四个 remoteproc 均为 running，`systemctl --failed` 为零。

本次没有做硬件完整性压测、传感器逐项功能测试或原厂 Android 启动对照。原厂 5.10 模块不能直接加载进当前 7.3 内核；可复用的是其逻辑、配置和有依据的参数，需适配当前内核接口。下一步优先利用 JN1 色彩资料、LPASS DMIC 时钟函数和面板 WQHD 模式配置，分别解决现有问题。

整理依据和 SHA-256 见[核查记录](../artifacts/stock-hardware-20261113/README.md)。用户授权归档的模块及配套元数据保存在上述 Git 目录；其余分区提取文件、固件、相机调校二进制和原始日志只在本地 `logs/stock-hardware-20261113/` 与手机 `~/stock-analysis-20261113/`，不纳入 Git。USB 无人工插拔断连已按用户要求另开会话调查，不能仅凭本轮短时恢复认定 USB 稳定性没有问题。
