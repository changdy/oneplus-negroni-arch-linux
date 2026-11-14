# 原厂驱动归档 vs 当前项目驱动：逐子系统差异核对

核对日期：2026-11-13。**全程只读、未连接手机、未刷写/重启、未修改内核树**。本报告是静态差异清单，不是实机验收结论。

---

## 0. 范围、材料与判定口径

**原厂侧**：`downloads/stock-drivers-20261113/vendor_dlkm_b/lib/modules/` 共 373 个 `.ko`，另有 `modules.load`、`modules.dep`、`modules.alias`、`modules.softdep`、`modules.blocklist`。模块 vermagic 为 `5.10.209-gki-gac3f956b8fca`，来自 `NE2210_15.0.0.401(CN01)` 的 `vendor_dlkm_b`。用 Python 解析 ELF64 抽取可打印字符串与 `.modinfo`（本机无 `strings`/`readelf`），并核对加载顺序与依赖；**没有加载或执行任何原厂模块**。

**项目侧**：手机当前 DTB 反编译 `logs/camera-20261113/phone-current.dts`、内核 DTS 副本 `logs/call-audio-20261112/sm8450-oneplus-negroni-before-dmic3.dts`、`config/{audio,wifi,bluetooth,gnss,usb-debug,kernel}/*`、`artifacts/*` 下各补丁与记录、`docs/*`、`logs/7.3/kernel.config`、`scripts/*`。WSL 构建树 `/opt/negroni-build/linux` 因本机程序黑名单无法访问，故未直接读取内核源码树；`patches/linux/local-7.3.bundle` 缺前置提交，也无法在本地解包。

**分级**：`A` 确认错误 · `B` 确认遗漏 · `C` 疑似（证据不足，需复核） · `D` 仅 vendor 架构差异（不应照搬） · `E` 证据不足。

**必须守住的边界**：

1. 原厂是 5.10 GKI vendor 模块，项目跑主线 7.3。模块存在 ≠ 硬件存在 ≠ 主线必须实现同名驱动；任何"缺某个 .ko"都不能直接判为项目缺陷。
2. 静态字符串只能证明驱动里写了什么，不能证明寄存器时序、物理波形、供电电压或功能已工作。
3. 项目已实机验证的结论（扬声器出声、Wi-Fi/蓝牙可用、JN1 出 RAW、GNSS 能跟踪少量卫星）不因静态差异被推翻；同样，"已出声/已出图"不等于相关配置完全正确。

---

## 1. 声音（扬声器、耳机、功放）

**原厂证据**：`machine_dlkm.ko` 同时含 `TDM-LPAIF-RX-TERTIARY` / `MI2S-LPAIF-RX-TERTIARY` 与 `qcom,tdm-audio-intf` / `qcom,mi2s-audio-intf`；`audio_extend_dlkm.ko` 用 `oplus,speaker-i2s-id`、`oplus,speaker-vendor`、`oplus,dac-i2s-id` 由 DT 选口。`tfa98xx-v6_dlkm.ko` 有 `nxp,tfa9874`、`tfa98xx_vdd`、`tfa no clock`、`fw_name:TFA98xx DSP firmware (container file)`、`tfa98xx.cnt`、`tfaRunSpeakerCalibration_v6`，依赖 `oplus_mm_kevent*`。`fsa4480-i2c.ko` 有 `qcom,fsa4480-i2c`、`fsa4480,hs-det-gpio`、`set mic to sbu2 for 3 pole`；`mbhc_dlkm.ko` 有 `oplus,mbhc-*`、`wcd9320_mbhc.bin`、`*** micbias2 force disable! ***`。`sia9175_dlkm.ko`（`sipa.bin`）、`wsa883x`、`wcd937x*` 也在 `modules.load` 音频段，属多机型共用模块集。

**项目现状**：`config/audio/sm8450-oneplus-negroni-audio.patch` 把 `Primary Spkr Playback` 的 CPU DAI 由 `TERTIARY_TDM_RX_0` 改为 `TERTIARY_MI2S_RX`，并把 `audio-routing` 换成 SM8450-HDK 路由；`docs/audio.md:32-41` 明确把 TDM→MI2S 标为**推断**。用户 2026-11-12 人耳确认扬声器出声。当前 DTB（`phone-current.dts:6658-6664`）仍是该 HDK 路由。

| 编号 | 级别 | 判断 |
| --- | --- | --- |
| 1-1 | `C` | **CPU DAI 与 pinctrl 不一致**：`&sound` 的 `pinctrl-0/1` 仍引用 `tert_tdm_*_active/sleep`（`before-dmic3.dts:1473-1476`），而 CPU DAI 已改 MI2S。两者共用 `mi2s2_*` 引脚时可能无害，但项目没有做引脚组核对，属未复核的不一致，不是已证实错误。 |
| 1-2 | `C` | **功放供电/校准缺失**：主线 `tfa9874` 节点（`before-dmic3.dts:1419-1435`）无 `vdd-supply`，原厂有 `tfa98xx_vdd`；`docs/audio.md:45-46` 自承无 I/V 反馈、无 NXP 校准、音量可能重置到 100%。已出声不代表供电描述完整。 |
| 1-3 | `B` | **耳机链路未验证**：`docs/audio.md:82,124` 明确耳机出声与 USB-C 插拔检测尚未测试。项目用 `fcs,fsa4480` + `JackControl "Mic Jack"`，原厂走 `qcom,fsa4480-i2c` + `oplus,mbhc-*` + 3/4 极切换与 micbias 时序。这是测试覆盖遗漏，不等于实现错误。 |
| 1-4 | `D` | TFA9874 的 DSP container 固件、`tfaRunSpeakerCalibration`、SIA9175/WSA883x/WCD937x 是 vendor 框架与多机型共用模块；主线不应照搬，也不能据此推断本机装了第三颗功放。 |
| 1-5 | `E` | 原厂扬声器最终接口制式、TDM 槽数/位宽/同步模式、功放是否需要 MCLK：`.ko` 字符串无法判定（`machine_dlkm` 两种接口都有，最终由 DT/ vendor 属性选）。`docs/audio.md:36-41` 已列为待实机确认。 |

---

## 2. 麦克风

**原厂证据**：`lpass_cdc_tx_macro_dlkm.ko` 含 `MSM_DMIC`、`TX DMIC0..7`、`TX DMIC MUX0..7`、`TX DEC0/1 MUX`、`TX_AIF1 CAP`；项目 `docs/stock-hardware.md:53` 与 `artifacts/mic-clock-20261113/README.md:10` 记录本机原厂 `mixer_paths.xml` 为 DEC0=`MSM_DMIC/DMIC3`、DEC1=`MSM_DMIC/DMIC4`、音量 84。原厂 DTBO：TX DMIC 2.4 MHz、VA 600 kHz；DMIC3→MIC BIAS3、DMIC4→**MIC BIAS1**（旧记录"BIAS4"已更正）。`lpass_cdc_dlkm.ko` 导出 `lpass_cdc_dmic_clk_enable`，TX/VA macro 在 `modules.dep` 中均依赖它；VA macro 另有 `qcom,fs-gen-sequence`、`qcom,va_mclk_mode_muxsel`、`va-vdd-micb-supply`。

**项目现状**：当前 DTB `phone-current.dts:6664` 的 `audio-routing` 含 `AMIC1 → MIC BIAS1`…`TX DMIC3 → VA DMIC3`，`qcom,dmic-sample-rate = 0x249f00`（2.4 MHz，`phone-current.dts:2948`）；`VA Capture` 仍指向 `TX_CODEC_DMA_TX_3`。UCM `config/audio/ucm2/OnePlus/negroni/HiFi.conf:46-58` 把内置麦写成 `AnalogMic1EnableSeq` + `CaptureMixerElem "ADC1"`；拓扑注释 `SM8450-OnePlus-10-Pro.m4:8` 直接写 `TX_CODEC_DMA_TX_3 -> WCD9385 analog microphones / headset mic`。

| 编号 | 级别 | 判断 |
| --- | --- | --- |
| 2-1 | `A` | **内置麦被当作模拟麦配置**：UCM 走 `AnalogMic1EnableSeq`/ADC1，拓扑注释把 TX3 后端定义为 analog microphones；而本机原厂是 DMIC3/DMIC4 经 `MSM_DMIC` 进 DEC0/1。`docs/audio.md:47` 自承"沿用 HDK 映射，尚未确认一加走线"。这与稳定录音全零的现象方向一致，是**优先级最高的可复核错误**（但不能就此认定它是唯一根因）。 |
| 2-2 | `A` | **VA Capture CPU DAI 用错**：`before-dmic3.dts:1552` 与当前 DTB 都是 `TX_CODEC_DMA_TX_3`（与 WCD Capture 相同），应为 `VA_CODEC_DMA_TX_0`。原厂 `machine_dlkm.ko` 中 `CODEC_DMA-LPAIF_VA-TX-0` 与 `CODEC_DMA-LPAIF_RXTX-TX-3` 是两个不同 DAI；项目 `config/audio/sm8450-oneplus-negroni-dmic34-va.patch:25` 已备好修正，**尚未应用、未刷写、未验证**。 |
| 2-3 | `B` | **DMIC4 相关属性在正式 DT 中缺失**：GPIO12/13 `dmic45_default`、`VA DMIC4` / `TX DMIC4` 路由、`MIC BIAS1`、`VA_MCLK` 依赖只存在于上述候选补丁；当前 DTB 只有 DMIC3 一侧。原厂两份量产 DTBO 均使用双 DMIC。 |
| 2-4 | `C` | **采样率与仲裁被简化**：原厂 TX 用 `qcom,tx-dmic-sample-rate`、VA 用 `qcom,va-dmic-sample-rate` 两个独立属性；主线只有 `qcom,dmic-sample-rate`，`dmic.patch:28` 把 600 kHz 改成 2.4 MHz。`mic-clock README:20` 明确这是临时让 VA 服务 TX，不是完整的 TX/VA 并发仲裁。 |
| 2-5 | `C` | **偏置初始化顺序**：`mic-clock README:66` 记录原厂启用偏置前置四个 `MICBx_TEST_CTL_2` 的 bit 0，主线遗漏；限时实验补上后仍无稳定信号。该结论来自反汇编，`.ko` 字符串层面无法复核，且已证明**补上不等于修好**。 |
| 2-6 | `D` | `lpass_cdc_dmic_clk_enable` 共享组引用计数、PRM 时钟申请、FS generator 序列属 5.10 vendor LPASS 架构，主线 `lpass-va-macro.c` 已有相近门控逻辑；`mic-clock README:57,114` 明确不能把"缺共享函数"当成全部根因。 |

**不能下的结论**：麦克风无信号的根因究竟在 DSP、主机时钟配置、偏置上电时序还是物理电气（`mic-clock README:57,47`）；GPIO8/12 无翻转只是软件采样，未用示波器测物理时钟；MICBIAS 实际电压未测。耳机麦（`ADC2`/AMIC2）映射同样未经确认。

---

## 3. 网络 / Wi-Fi

**原厂证据**：`cnss2.ko`（`qcom,cnss-qca6490`/`qcom,cnss-kiwi`/`qcom,cnss-qca6390`、`bdwlan.bin`/`bdwlan%02x.e%02x`、`regdb.bin`、`wlfw_cal_db.bin`、`cnss_wlfw_ini_file_send_sync`、`cnss_register_coex_service`、`Received DMS MAC`、`vdd-wlan-*`）、`icnss2.ko`（`qcom,wcn6750`、`use-nv-mac`、`QMI_DMS_GET_MAC_ADDRESS`）、`cnss_utils.ko`（`Provisioned/Derived MAC addresses`）、`wlan_firmware_service.ko`（`wlfw_bdf_download_req_msg_v01_ei` 等 QMI WLFW 编码）、三个 `qca_cld3_*.ko`（`wlan/qca_cld/kiwi/wlan_mac.bin`、`qca6490/athwlan.bin`、`CoexMgrPolicy`）。`modules.load:314-319` 三个 qcacld 模块**重复两遍**，`modules.dep` 中每个只出现一次、`modules.alias` 中无其 alias。

**项目现状**：主线 `ath11k_pci` + mac80211，`config/wifi/` 关闭省电、MAC 用 `stable`、国家域 `CN`；`docs/wifi.md` 记录 PMU 与 IOMMU 告警的取舍；`logs/7.3/kernel.config:2529-2532` 有 `ATH11K=m`/`ATH11K_PCI=m`、`QRTR=y`、`BT_QCA=m`。

| 编号 | 级别 | 判断 |
| --- | --- | --- |
| 3-1 | `D` | CNSS2/qcacld-3.0 的 WLFW QMI、BDF/INI 下发、coex 服务是 vendor 私有架构；主线 ath11k 内建固件加载。`docs/wifi.md:30` 已声明 INI 不由主线驱动读取。**不算遗漏**。 |
| 3-2 | `C` | **设备专用板级数据未核准**：`scripts/finalize-rootfs.sh:88` 只校验 `board-2.bin`（或 `.zst`/`board.bin`）存在；`analysis/kernel-branches.md:135` 指出"没解决设备专用 board-2.bin 的准备问题"，`docs/wifi.md:32` 记录 CN 域下 2.4 GHz 仍只开放信道 1–11。存在 ≠ 与本机校准/初始监管域匹配。 |
| 3-3 | `C` | **MAC 地址来源不同**：原厂走 NV/DMS provisioned MAC，项目用 NetworkManager `stable`（`docs/wifi.md:12` 明示不恢复原厂 NV 地址）。这是明确取舍，不是驱动错误；但白名单/绑定场景需注意。 |
| 3-4 | `C` | `vddpmumx-supply`/`vddpmucx-supply` 在主线 DT 缺失、用 dummy regulator；`docs/wifi.md:36` 记录补齐后出现 PCIe 设备未枚举并已回退。属**已记录的有意取舍**，不是新发现的错误。原厂 `cnss2.ko` 只有 `vdd-wlan-*`，没有这两个主线 binding 名。 |
| 3-5 | `E` | `modules.load` 中三个 qcacld 模块重复两遍是清单拼接冗余，不是双芯片或加载两次；也不能由 `qca6490/qca6750/kiwi/WCN6750_V1` 字符串断定本机芯片型号——三变体共用同一模块包。`config/kernel/negroni.config` 只有 11 行增量片段，不能据此判断缺 `CONFIG_ATH11K*`（完整配置里都有）。 |

---

## 4. 蓝牙

**原厂证据**：`btpower.ko` 有 `qcom,wcn6750-bt`/`qcom,qca6490`/`qcom,kiwi`、`qcom,bt-vdd-aon/asd/core/dig/io/pa/rfa*`、`qcom,bt-reset-gpio`、`qcom,wl-reset-gpio`、`qcom,xo-clk-gpio`、`bt-sw-ctrl-gpio`、`btpower_register_slimdev`；`bt_fm_slim.ko` 有 `BTFM_SLIM`、`btfm_bt_sco_a2dp_slim_rx`、`btfm_fm_slim_tx`。**373 个 `.ko` 全局扫描未发现任何 `bdaddr` / `ro.boot.btmacaddr` / `local-bd-address` / `public-address` 字符串**。`modules.softdep:16` 要求 `machine_dlkm pre: bt_fm_slim`。

**项目现状**：`config/bluetooth/negroni-bt-address` 由 `soc0/serial_number` 派生 `02:4E:xx:xx:xx:xx`，经 `btmgmt public-addr` 写入；`docs/bluetooth.md:7-10` 记录固件/HCI/扫描已验证、完整重启与配对/A2DP 未测。当前 DTB 的 `bluetooth` 节点只有 8 路 `vdd*-supply` 与 `max-speed`，无 `local-bd-address`、无 slimbus/btfm 节点。

| 编号 | 级别 | 判断 |
| --- | --- | --- |
| 4-1 | `C` | **出厂 BD 地址未恢复**：项目用派生的本地管理地址；原厂 NV/DMS 地址路径在用户空间 HAL 与 persist/bluetooth 分区里，不在 `.ko` 中，本轮无法证明原厂是否有可读出厂地址。`docs/bluetooth.md:14` 只证明"Linux 读不到"。这是取舍，不是驱动错误。 |
| 4-2 | `C` | **历史固件失败日志不是当前遗漏**：`artifacts/wake-latency-20260916/baseline.txt:83-94` 显示 `qca/wcnhpbtfw21.tlv`、`qca/hpbtfw21.tlv` 加载 `-2`；但 `docs/build-integration.md:24` 记录后续修正了 A/B 蓝牙路径，`config/firmware-loader/msm-firmware-loader.sh:215-224` 已把 bluetooth 分区链到 `target/qca/`，`docs/bluetooth.md:7` 称固件加载正常。仓库缺"修复后成功加载"的日志证据，建议补一次只读确认，但**不能据此判当前缺固件**。 |
| 4-3 | `D` | BT/FM SLIMBus 通路（`bt_fm_slim`、`slimbus`、`radio-i2c-rtc6226-qca`）是 vendor 音频私有路径，主线 `hci_uart` 不走此路；FM 与 `rtc6226` 不移植不构成错误。 |
| 4-4 | `C` | **coex 无显式配置**：原厂 `cnss2.ko` 有 `cnss_register_coex_service`、天线切换请求，qcacld 有 `CoexMgrPolicy`；项目只有 `docs/bluetooth.md:9` 一次"扫描 10 个设备期间 Wi-Fi 稳定"的观察，高并发/长时间共存未测。 |
| 4-5 | `E` | 原厂 `qcom,bt-vdd-*` 命名与主线 8 路 `vdd*-supply` 不同，属架构差异；8 路是否覆盖原厂全部电源轨，静态字符串无法判定。 |

---

## 5. GPS / GNSS

**原厂证据**：373 个 `.ko` 全库扫描**没有 GNSS 接收驱动**（严格匹配 `gnss`/`gps`/`izat.conf`/`qmi_loc`/`loc_api`/`xtra*.bin` 的命中全是误命中：`Initialization` 含 "izat"、Wi-Fi `eLNA bypass`、充电模块 `SUPLLEMENT MODE`）。`qrtr-smd/mhi/gunyah.ko`、`qmi_helpers.ko`、`pdr_interface.ko` 只有通用传输字符串。定位引擎在 modem 固件 QMI LOC（服务 16 / 版本 2 / 节点 0）。

**项目现状**：`docs/gnss.md` 记录引擎锁 + libqmi/ModemManager AFW 注册修复、XTRA 注入已通、可跟踪少量真实卫星但仍无坐标；`logs/7.3/kernel.config` 已有 `QRTR=y`、`GNSS=m`、`PD_MAPPER=m`、`QMI_HELPERS=y`。

| 编号 | 级别 | 判断 |
| --- | --- | --- |
| 5-1 | `D`/`A` | **"缺 GNSS 内核驱动"是误判**：项目走 QMI LOC，`docs/gnss.md:9` 明确不需要 `/dev/gnss0`；原厂也没有专用 GNSS 内核驱动。不要为 GNSS 去照搬或新增内核驱动。 |
| 5-2 | `B` | **SUPL 在线辅助未落地**：`artifacts/gnss-20261113/README.md:74-78` 记录 ModemManager 缺 `0x53 InformLocationServerConnStatus` 处理，MSB OPEN/CLOSE 握手已通但 SUPL TLS 端到端未验证；`docs/gnss.md:34,63` 明确 SUPL/室外/导航未测。这是用户空间链路的确认遗漏。 |
| 5-3 | `C` | 原厂 `oplus_bsp_rfcablemonitor.ko` 有 `oplus,rf_cable`、`rf,cable*-gpio`、`SMEM_RF_INFO`，但**无 GNSS 字样**；`docs/gnss.md:36,119` 已查 Android 12.1/14/15 的 `wly-20846`/`waipio` DTS 未见本板 GNSS ELNA 配置，并明令不得照搬别的 SM8450 手机 GPIO。L1/L5 PGA 从 -12 dB 自恢复（`docs/gnss.md:42`）也不能证明天线或 USB 干扰。 |
| 5-4 | `E` | 无坐标的根因（室内条件、射频增益、天线供电、NV 校准、SUPL）尚未定位；不能把 69 个搜索目标当收到 69 颗卫星、把无效 SNR 当实测、把 XTRA/MSB 握手当定位成功。 |

---

## 6. 重力感应（加速度计 / 陀螺仪等传感器）

**这是本轮最明确的整块遗漏。**

**原厂证据**：`oplus_bsp_sensor_feedback.ko` 含 `device_{acc,gyro,mag,als,ps,sar,hall,barometer}_i2c_err`、`device_acc_cali_data`、`explorer_gyro`、`pressure`、`available_sensor_list`、`SMEM_SENSOR_FEEDBACK`；`oplus_sensor.ko` 含 `alias=of:N*T*Coplus,sensor-devinfo`、`publish-sensors`、`gsensor`/`msensor`/`lsensor`/`psensor`/`ssensor`、`sensor-name`、`bus-number`、`sensor-direction`、`irq-number`、`ldo-gpio`、`SMEM_SENSOR`。`sensors_ssc.ko` 为 `qcom,msm-ssc-sensors`（`slpi2.mdt`）。`modules.load` 在第 68/102/103/104 行加载这四个模块。

**项目现状**：当前 DTB（`phone-current.dts`）逐项检索只有两个 `oplus,hall-mxm1120`（1821/1834 行）与大量 `thermal-sensor`；**没有任何 accelerometer / gyroscope / magnetometer / ALS / proximity / barometer / SAR 节点**，也没有 `qcom,msm-ssc-sensors` / `oplus,sensor-devinfo` / `oplus,sensor-feedback`。`scripts/prepare-rootfs.sh:64-65` 主动移除 `iio-sensor-proxy`（`docs/archive/build-notes-2026-09-16.md:299` 说明是有意移除）。`config/firmware-loader/msm-firmware-loader.sh:146-155` 只在存在 `/usr/share/qcom/sm*/*/*/sensors` 时才链接 `persist/sensors/registry/registry`，否则打印 "No installed qcom sensor registry consumer"。`docs/status.md:42-66` 的状态表、`docs/README.md` 的文档索引里**没有传感器条目**；`artifacts/stock-hardware-20261113/evidence.json:476-560` 的 I²C 绑定清单也无 accel/gyro。

| 编号 | 级别 | 判断 |
| --- | --- | --- |
| 6-1 | `B` | **IMU 与传感器完全未移植**：设备树无节点、无驱动绑定、无用户空间代理、无状态记录。原厂模块字符串证实该机型存在 acc/gyro/mag/als/ps/sar/barometer/hall 至少八类传感器。这不是"未验证"，而是"未实现"。 |
| 6-2 | `A` | **"缺 IIO 内核配置"是误判**：`logs/7.3/kernel.config` 已有 `IIO=y`、`ST_LSM6DSX{,_I2C,_SPI}=m`、`ST_MAGN_3AXIS=m`、`ST_SENSORS_*=m`。缺的是 DT 节点与板级参数，不是内核选项。`CONFIG_RFS_ACCEL=y` 是远程文件系统加速，与加速度计无关。 |
| 6-3 | `D` | `sensors_ssc.ko`（5.10 GKI + SLPI/SSC 框架）、`oplus_sensor.ko` 的 SMEM 发布、`ssc_interact.ko`（实为面板亮度/DC notifier）是 vendor 架构，**不能加载进 7.3、也不应照搬**；主线要走 IIO + 设备树 + iio-sensor-proxy 路线。 |
| 6-4 | `C` | **补齐所需的关键参数不在 `.ko` 里**：原厂模块只有 `gsensor`/`msensor` 等抽象名，扫描不到 bosch/invensense/ST 的具体兼容串或 I²C 地址。具体 `sensor-name`/`bus-number`/`irq-number`/`ldo-gpio` 在原厂 DTBO 的 `oplus,sensor-devinfo` 节点（`docs/stock-hardware.md:12` 记录有 12 个 overlay）。**下一步应只读解析原厂 DTBO，而不是套用通用驱动或别机 GPIO**。 |
| 6-5 | `A` | 名称辨析：`qti_qmi_sensor_v2.ko` 是 QMI 热传感器（`qcom,qmi-sensors`），`cs_press_f71.ko` 是 `chipsea,csa37f71` 压感，`oplus_bsp_ist_*`/`mxm_*`/`tri_key` 是霍尔开关，`aw8697.ko` 是触觉——都不是 IMU/GNSS，不要误当作"传感器驱动已有"。 |
| 6-6 | `C` | 项目里两个 `oplus,hall-mxm1120` 节点在原厂由 `oplus_bsp_mxm_up/down.ko` 驱动，`docs/stock-hardware.md:70` 记录"没有 driver 绑定"，即这两个节点也是挂着的空节点。 |

---

## 7. 摄像头

**原厂证据**：`camera.ko`（12.2 MB，33510 条字符串）是 monolithic vendor 驱动：`modules.alias:269-418` 把 `qcom,cam-req-mgr/cam-sensor/csiphy/cci/eeprom/actuator/ois/camera-flash/csid680/vfe680` 全部指向单一 `camera`；私有 DT 属性 `gpio-vana`/`gpio-vdig`/`gpio-reset`/`cci-master`/`rgltr-min-voltage`；`modules.dep` 还依赖 `oplus_chg.ko`、`dwc3-msm.ko`、`ucsi_glink.ko`。`camcc-waipio.ko` 有 `cam_cc_mclk1_clk`/`bi_tcxo`/`vdd_mm`。全库 `s5kjn1|jn1|imx615` 命中 **0**（传感器名在 ODM 用户空间）。原厂 DTSI `logs/camera-source-20261113/wly_20846_camera_overlay_common.dtsi`：`clock-rates = <19200000>`、`cci-master = <1>`、`gpio-reset = <1>`、`csiphy-sd-index = <2>`、`cam_vio/cam_vana/cam_vdig`、`qcom,cam-sensor0/1/2`、多组 `qcom,eeprom`。

**项目现状**：`artifacts/camera-20261113/camera-bringup.patch` 把 MCLK 改 24 MHz、reset 改 `tlmm 24 GPIO_ACTIVE_LOW`、CSI 改 CSIPHY2、补电源，另有 `csiphy_is_gen2()` 加 `CAMSS_8450`、CAMCC GDSC/RCG 修复、DMA contiguous 修复。`docs/camera.md` 记录 JN1 已出 4080×3072 RAW、重复开启仍硬重启、补丁未提交未接入镜像。

| 编号 | 级别 | 判断 |
| --- | --- | --- |
| 7-1 | `B` | **其余三摄与配套器件未移植**：主线只有 JN1 一颗 + 通用 `eeprom@51`；原厂 ODM 有 IMX789 / S5KJN1 / OV08A10 / IMX615 四组组件，DT 有 `qcom,cam-sensor0/1/2`、多组 `qcom,eeprom`、actuator、flash。`docs/stock-hardware.md:70` 记录 EEPROM 节点无 driver 绑定，OTP/AWB/CCM/LSC 标定未接入。 |
| 7-2 | `C` | **MCLK 24 MHz vs 原厂 DT 默认 19.2 MHz**：数值差异确凿，但 `artifacts/camera-source-20261113/README.md:52` 记录原厂 `SENSOR_MCLK` 上电命令可覆盖 DT 值；`docs/camera.md:29` 也说明不能从 DT 单值推断正常拍摄的完整 PLL/时序。**不能判为错误**，需要原厂正常拍摄路径的实际时钟才能定论。 |
| 7-3 | `E` | reset GPIO24 编号有原厂依据，但"低有效"无直接证据：原厂 `gpio-reset = <1>` 是索引属性（`camera-source README:30`）；主线 `&cci0_i2c1` 与原厂 `cci-master = <1>` 是不同编号体系。实机 `6-0010` 已绑定并出图，不据此判错。 |
| 7-4 | `D` | `camera.ko` 的私有属性与依赖链与主线 CAMSS 架构完全不同，不能照搬；`camcc-waipio.ko` 里没有 19.2/24 MHz 数值（频率不在时钟驱动里）。`config/kernel/negroni.config` 无 `CONFIG_VIDEO_QCOM_CAMSS*` 只是增量片段，相机已实跑，不能据此判配置遗漏。 |
| 7-5 | `E` | 重复开启硬重启的根因未定位（`docs/camera.md:33-46`）；不能归因于 MCLK、极性、DMA、时钟或供电中的任何一项。电源 1.8/2.8/1.056 V 已按原厂补齐，属已完成的对照。 |

---

## 8. USB

**原厂证据**：`oplus_chg.ko`（6.8 MB）含 `!!!!!enable otg`、`!!!!!disable otg`、`!!!!!cid detect || no detect`、`!!!!!typec_state_change_work`、`cid_status`、`oplus_voocphy_set_dpdm_enable`、`oplus_dwc3_config_usbphy_pfunc`、`fastchg/%d/oplus_vooc_fw_op10.bin`；`dwc3-msm.ko` 有 `role_switch_mutex`、`no USB role change`、`LPM is not performed`、`qcom,force-gen1`；`phy-msm-snps-hs.ko` 有 `msm_hsphy_put_phy_in_non_driving_mode` 相关 datapath override 逻辑。`modules.softdep` 要求 `dwc3_msm` 预载四类 PHY；`modules.load:160-178` 还打包了 eUSB2/EMU PHY、NB7VPQ904M redriver、NXP repeater。原厂 DTBO 有 `qcom,otg_scheme = <0>`、`dr_mode = "otg"`、`usb-role-switch`、`qcom,fsa4480-i2c`，未见 eUSB2/repeater/redriver 节点。

**项目现状**：`artifacts/usb2-gadget-20261113/usb2-datapath-candidate.patch` 补了 `qcom_snps_hsphy_release_datapath()`（清 `UTMI_PHY_DATAPATH_CTRL_OVERRIDE_EN`）与 `dwc3_qcom_set_role_notifier()`（同角色 DEVICE 不早退 + `phy_set_mode`），2026-11-13 已刷入 b 槽重启验证 USB2 自动恢复；`docs/usb-debug.md:84-87,113-139` 记录 LPM 实验属性仍在、OTG host 误切换方向已被 21 时实验否定、补丁未纳入 Git 与镜像构建。`config/usb-debug/usb-gadget.sh:18` 只启用 NCM + ACM。

| 编号 | 级别 | 判断 |
| --- | --- | --- |
| 8-1 | `A` | **LPM 实验属性方向错误且未回滚**：`snps,usb2-gadget-lpm-disable` 注入后 DT 属性与 DCFG LPMCap 清零都生效，但 USB2 口仍失败；`docs/usb-debug.md:85,131` 明确该实验属性未纳入 Git、未回滚。10T 用的是 `has-lpm-erratum + hird-threshold=0 + is-utmi-l1-suspend`，且 PHY 硬件不同。属已否证的错误尝试残留。 |
| 8-2 | `B` | **充电/角色状态机能力缺失（但已否定为 USB2 根因）**：主线 `oplus_battmgr` 是最小实现，不识别 `0x53 = BC_CID_DETECT`、不解析 `qcom,otg_scheme`，没有原厂的 OTG/CID/Typec 状态机（`artifacts/usb2-diagnosis-20260916-030952/README.md:44-47`）。`docs/usb-debug.md:84-87` 记录 21 时对照实验已否定它是 USB2 故障根因，因此是能力缺口，**不是当前故障的解释**。 |
| 8-3 | `B` | **已验证的驱动修复未集成**：datapath override 释放与角色通知补丁只在 `artifacts/usb2-gadget-20261113/` 与手机 b 槽里，`docs/usb-debug.md` 明确"未纳入 Git 和镜像构建"；`config/usb-debug/` 只有 gadget 服务。同样情况见第 9 节。 |
| 8-4 | `D` | eUSB2/repeater/redriver 是 waipio 平台通用打包，本机 DTBO 与主线 DT 只有 HS PHY + QMP；原厂 gadget function 是 diag/qdss/ccid/cdev/gsi，项目只要 NCM+ACM，用途不同，不是遗漏。 |
| 8-5 | `C` | 当前 DTB `maximum-speed = "super-speed"` 与 10T 的 `super-speed-plus` 不同，但 `oneplus-10t-dt-comparison.md` 已把该差异判为非 USB2 掉线主因；本机原厂值未取证。 |
| 8-6 | `E` | 22:34–22:36 无人工插拔的 SCP/USB SSH 中断根因未定位（`artifacts/usb-disconnect-20261113/README.md`）；不能归因于 LPM、OTG、PD Hub 或主机虚拟网络。 |

---

## 9. 跨子系统的系统性问题（比单个驱动差异更值得关注）

多项已经实机验证或有完整回滚材料的改动，**只以补丁/工件形式存在，没有进入 Git 与镜像构建**：

| 内容 | 现状 | 依据 |
| --- | --- | --- |
| S5KJN1 相机 DT + CAMSS/CAMCC/DMA 改动 | 只在 WSL 内核树与 `artifacts/camera-20261113/camera-bringup.patch`，未提交、gitlink 与 bundle 未更新 | `docs/camera.md:18` |
| USB2 datapath / 角色通知修复 | 已刷入 b 槽并验证，未纳入 Git 与构建 | `docs/usb-debug.md`、`AGENTS.md` |
| DMIC4 + VA CPU DAI 候选 | 增量实验补丁，仅 `git apply --check`，未应用/提交/刷写 | `artifacts/mic-clock-20261113/README.md:73-85` |
| GNSS 用户空间栈（libqmi/MM 补丁、解锁服务、XTRA 工具） | 只在手机 `/opt/negroni-gnss` 手动部署，未接入完整镜像 | `docs/gnss.md:5,103` |
| 通话语音内核补丁 `sm8450-audioreach-voice.patch` 与语音拓扑 | 仅以补丁形式保存、实验模块热安装，未进构建 | `docs/call-audio.md:34,46,80` |

因此"当前项目的驱动"与"手机实际跑的驱动"并不相同：手机上有若干未入库的临时改动，而全新完整镜像会缺这些能力。核对差异时若只看 `config/`，会低估实际状态；若只看手机，会高估镜像的可复现性。

---

## 10. 优先级建议（仅按证据强度排序，不构成立即修改的授权）

1. **重力感应/IMU 整块缺失**（6-1）：先只读解析原厂 DTBO 的 `oplus,sensor-devinfo`，拿到具体 sensor-name / bus-number / I²C 地址 / irq / ldo-gpio，再谈主线 DT 节点与 iio-sensor-proxy。这是唯一一个"从零开始"的子系统。
2. **麦克风路径**（2-1、2-2、2-3）：UCM/拓扑把内置麦当模拟 AMIC、VA CPU DAI 用错、DMIC4 属性未进正式 DT；三者都有现成补丁或明确的复核点，且对应已存在的功能故障（稳定录音全零）。
3. **未集成的已验证改动**（第 9 节）：相机、USB2、GNSS、通话语音至少四组，需决定是纳入构建还是明确标注为实验。
4. **配置自洽性复核**（1-1、1-2、3-2、4-2）：MI2S 与 TDM pinctrl、功放 `vdd`、board-2.bin 设备专用性、蓝牙固件加载成功日志。
5. **不要做的**：照搬 5.10 vendor 模块、把 qcacld/CNSS2/SLIMbus/SSC/monolithic camera 当主线驱动模板、照搬别的 SM8450 机型的 GPIO、把 LPM 或 OTG 状态机当成已定位的 USB 故障根因。

---

## 11. 本轮不能下的结论 / 需要实机或物理测量

- 原厂扬声器接口制式、功放 MCLK、TDM 参数；DMIC 时钟物理波形（需示波器/逻辑分析仪）、MICBIAS 电压与上电顺序。
- 麦克风无信号、相机重复开启硬重启、USB 偶发断连的三个根因，均未定位。
- 本机是否实装 SIA9175 / WCD937x / WSA883x / SSC 传感器；原厂是否有可读出厂 BD 地址；GNSS 天线/ELNA/射频校准状态。
- 所有"未测"项：耳机出声与插拔、蓝牙完整重启/配对/A2DP、Wi-Fi 5 GHz 与测速、室外 GNSS 定位/TTFF/SUPL、其余三摄、OTG host / PD Hub / 完全断电启动 / 挂起恢复、全新完整镜像逐项验证。
- 原厂 5.10 模块不能直接加载到 7.3（`docs/stock-hardware.md:72`）；本报告全部结论来自静态字符串、DT 文本与项目既有记录，**未执行原厂二进制、未做硬件功能验证**。

---

## 12. 证据索引

- 原厂模块与元数据：`downloads/stock-drivers-20261113/vendor_dlkm_b/lib/modules/`（`modules.load` / `modules.dep` / `modules.alias` / `modules.softdep`），归档说明见同目录上级 `README.md`、`inventory.csv`、`SHA256SUMS`。
- 主线 DTS 副本：`logs/call-audio-20261112/sm8450-oneplus-negroni-before-dmic3.dts`；手机当前 DTB 反编译：`logs/camera-20261113/phone-current.dts`；原厂相机 DTSI：`logs/camera-source-20261113/wly_20846_camera_overlay_common.dtsi`；原厂 DTBO 反编译：`logs/stock-hardware-20261113/overlay-00.dts` / `overlay-11.dts`。
- 项目配置与补丁：`config/audio/*`、`config/wifi/*`、`config/bluetooth/*`、`config/gnss/*`、`config/usb-debug/*`、`artifacts/camera-20261113/camera-bringup.patch`、`artifacts/usb2-gadget-20261113/usb2-datapath-candidate.patch`。
- 内核配置：`logs/7.3/kernel.config`、`analysis/branches/master.config`、`config/kernel/negroni.config`。
- 既有结论：`docs/audio.md`、`docs/call-audio.md`、`docs/wifi.md`、`docs/bluetooth.md`、`docs/gnss.md`、`docs/camera.md`、`docs/usb-debug.md`、`docs/stock-hardware.md`、`docs/status.md`、`artifacts/mic-clock-20261113/README.md`、`artifacts/stock-hardware-20261113/evidence.json`、`artifacts/gnss-20261113/README.md`、`artifacts/usb-disconnect-20261113/README.md`。
