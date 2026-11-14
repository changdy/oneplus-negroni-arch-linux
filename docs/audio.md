# 音频（扬声器、麦克风、耳机）

状态日期：2026-11-14。**声卡已经可用**：刷入路由修正后的 `vendor_boot_b`，开机即生成 `OnePlus-10-Pro` 声卡，PipeWire 识别出扬声器、耳机、内置麦克风和耳机麦克风。用户已确认扬声器正常出声。**内置麦克风从 2026-11-14 傍晚起可以录音**。此前稳定段全零：早期非零样本只是启动瞬态；原厂路由是 DMIC3/DMIC4，2026-11-13 补齐 DMIC4 的 MIC BIAS1、双 DMIC 门控与 VA_MCLK 并部署后 VA 端口能打开但仍全零；2026-11-14 的 TX/VA 多通道修正和 DMIC3/4 UCM 启停通过，声学信号仍为零。当天下午定位到 `audio-codec` 的 `sleep` 引脚状态把 WCD9385 复位脚在空闲时拉低；傍晚去掉该状态、刷入 `vendor_boot_b` 并重启后，ALSA `hw:0,2` 录到扬声器播放的 1 kHz 测试音。同一改动已进入内核提交 `67d9e35c9ac0`，这次提交没有重新构建镜像。见[本轮记录](../artifacts/mic-clock-20261113/README.md)。耳机出声和插拔检测尚未测试。通话相关的内容（语音图、通话录音与放音、麦克风排查）统一写在[通话语音](call-audio.md)。

2026-11-14 补充：用户未测试刷机前的原厂麦克风，当前没有正常采集基线。对照原厂 WCD 模块又验证了 eFuse/SLEEP_CTL 校准：运行时字段调整及启动时模块对照均未恢复信号，实验 WCD 模块已还原并重启；详见[续测记录](../artifacts/mic-clock-20261113/README.md#同日续测原厂基线未测与-wcd9385-启动校准)。

2026-11-14 下午定位到原因，傍晚已刷入并重启验证。从主 TLMM 一侧读回确认录音时两路 DMIC 时钟都在，此前“没有时钟”是 LPI 读回方式的假象；设备树给 `audio-codec` 配了 `sleep` 引脚状态，声卡空闲时 WCD9385 的复位脚（gpio43）被拉低，打开 PCM 才放开，带隙和模拟偏置的初始化随复位丢失且没有被回写。临时绕过证明两路麦克风能录到 1 kHz 测试音。傍晚的持久改动只动运行中的 `vendor_boot_b`：备份 SHA-256 `c86b6e9a1f861047f9bd71cb40af2e8f508216f600ce94cfd2cc551491233ce8`，刷入镜像 `2714b634cc0fadbc96378c9c71f92851c41357a92ed4635476389e3b65473703`。`pinctrl-names` 只保留 `default`，删掉指向 gpio43 `output-low` 的 `pinctrl-1`，`pinctrl-0` 仍是 `output-high`；ramdisk、USB2 LPM 和相机设备树未动。重启后 B 槽仍是 Active/Successful/Bootable=1。空闲、录音和关闭 PCM 之后 gpio43 都保持高电平，引脚状态保持 `default`，WCD 的 TX/RX 从设备保持已枚举，没有再做 `/dev/mem` 置位或 `power/control` 切换。8 秒 `hw:0,2` 录音里，扬声器播放 2 秒、幅度 1500 的 1 kHz 测试音落在第 3–4 秒：左声道 1 kHz 分量 172 和 158，右声道 448 和 407，其余各秒接近 0；两路数据脚在录音时各翻转约一万次。第一秒仍有启动瞬态（RMS 约 1100）。关闭后 mixer 已还原。启动时有两条 `Impedance detect ramp error`，这次录音期间没有新增。随后三次 80 ms 短振结束后录了 10 秒并从喇叭外放，用户听过。第 1 秒峰值打满 32767，是启动瞬态；其后 9 秒去直流 RMS 约 27–86，峰值 187–585。外放把第 1 秒之后的峰值放大到约 6000，并把瞬态限制在 10000。通话上行、PipeWire 桌面录音、耳机出声和插拔仍未测。内核提交 `67d9e35c9ac0` 已去掉该状态，但没有用这次提交重新构建镜像，手机上跑的仍是字节补丁过的 `vendor_boot_b`。详见[刷入记录](../artifacts/mic-clock-20261113/README.md#2026-11-14-傍晚去掉-sleep-状态并刷入验证)。

## 现状诊断（7.3.0-sm8450+，实机 `journalctl -k`）

内核侧大部分已经就绪：

- ADSP 正常启动，GPR/APM 服务 `gprsvc:service:2:1` 已注册。
- WCD9385 通过 SoundWire 绑定（RX `sdw:2:0`、TX `sdw:3:0`），耳机/麦克风编解码器可用。
- 两颗 TFA9874 功放（I²C13 `0x34`/`0x35`，修订 `0x0c74`）被 `tfa987x` 驱动识别。

声卡失败只有一个直接原因：

```
qcom-apm gprsvc:service:2:1: Direct firmware load for qcom/sm8450/OnePlus-10-Pro-tplg.bin failed with error -2
snd-sc8280xp sound: ASoC: failed to instantiate card -2
```

公开的 [linux-msm/audioreach-topology](https://github.com/linux-msm/audioreach-topology) 和 linux-firmware 中没有一加 10 Pro 的拓扑，只有 `SM8450-HDK`。

## 修改内容

| 文件 | 作用 |
| --- | --- |
| [config/audio/topology/SM8450-OnePlus-10-Pro.m4](../config/audio/topology/SM8450-OnePlus-10-Pro.m4) | 基于 SM8450-HDK 的 AudioReach 拓扑：MM1/MM2 播放、MM3/MM4 录音；后端为 WCD RX0（耳机）、Tertiary MI2S（扬声器）、WCD TX3 与 VA TX0（麦克风） |
| [scripts/build-audio-topology.sh](../scripts/build-audio-topology.sh) | 用上游 m4 宏和 `alsatplg` 生成 `OnePlus-10-Pro-tplg.bin`；在 audioreach-topology `d6bb205` 上两次构建结果一致 |
| [config/audio/sm8450-oneplus-negroni-audio.patch](../config/audio/sm8450-oneplus-negroni-audio.patch) | 内核 DT：扬声器链路由 `TERTIARY_TDM_RX_0` 改为 `TERTIARY_MI2S_RX` 并添加位时钟投票；`audio-routing` 换成上游 SM8450-HDK 的有效路由。目前只在 WSL 内核树中未提交，尚未进入 `linux/` 子模块 |
| [config/audio/ucm2/](../config/audio/ucm2/) | ALSA UCM：`conf.d/sm8450/OnePlus-10-Pro.conf`，hw:0 耳机、hw:1 扬声器、hw:2 麦克风 |
| [config/audio/negroni-audio-test.sh](../config/audio/negroni-audio-test.sh) | 手机端测试脚本（见下） |

### 为什么扬声器改用 MI2S

DT 原本把 TFA9874 接在 Tertiary **TDM**。在 7.3 的 AudioReach 驱动中，TDM 端口只能通过新的 `AUDIO_IF`（QAIF，`0x0700117C`）模块驱动，上游只在 Hawi/Nord/Shikra 等新平台使用；SM8450 的 HDK 拓扑只用到 `I2S_SINK`（`0x0700100A`）和 Codec DMA。Tertiary TDM 与 Tertiary MI2S 共用 `mi2s2_*` 引脚，`tfa987x` 驱动在探测时把功放配置为每帧 2×16 bit（等同 16 bit 立体声 I²S），按 `sound-channel` 选择左右声道，所以改为 Tertiary MI2S、数据线 SD1（`mi2s2_data1`）。

这是**推断**，需要实机确认：
- ADSP 固件是否接受 Tertiary MI2S；
- 功放是否需要 MCLK；
- 帧格式与 Android 是否一致。

若播放无声或 hw_params 报错，就要按 Android 的 TDM 参数排查（槽数、位宽、同步模式）。

### 风险

- `tfa987x` 驱动没有扬声器保护（无 I/V 反馈、无 NXP 校准参数）。测试时请**先把音量调低**，不要长时间大音量播放。
- UCM 中扬声器设备没有音量控件，音量只能由 PipeWire 软件调节。
- 内置麦克风已按原厂改成 DMIC3/DMIC4（MIC BIAS3 / MIC BIAS1）。2026-11-14 傍晚去掉复位脚的 `sleep` 状态并重启后，ALSA 直接录音能录到 1 kHz 测试音；UCM / PipeWire 桌面录音未再测。耳机麦克风仍沿用 AMIC2 → ADC2，实机声学验证未测。
- 耳机通过 USB-C 模拟转接（FSA4480），插拔检测和模式切换是否正常尚待测试。

## 2026-11-11 实机结果（阶段 1）

- 安装拓扑后不能用 unbind/bind 重新探测 `qcom-apm`：`apr_device_remove()` 会从 GPR 路由表中删除端口 1，bind 后不会重新登记，DSP 的回复随即被丢弃（`GPR: Port(1) is not registered`，命令 5 秒超时）。脚本已改为提示重启。
- 重启后拓扑加载成功（不再出现 `-2`），声卡走到注册路由（DT 中 VA/DMIC 等 widget 缺失会报 `Failed to add route`，属于警告），但最终没有生成声卡，也没有错误日志；`devices_deferred` 为空，`sound` 设备未绑定驱动。
- 此后手动 bind `snd-sc8280xp` 时，DSP 拒绝共享内存映射（`Error (1) Processing 0x0100100c`，`Buffer Allocation failed rc = -22`）。这与上游 2026-10 修复的问题一致：上一次失败的探测没有解除缓冲区映射，重新映射时被 DSP 拒绝，见 [ASoC: qcom: q6apm: Fix shared memory unmap](https://lore.landau.one/lkml/20261016141153.1346219-2-shengchao.guo%40oss.qualcomm.com/T/)。所以这不是根因，真正要查的是开机时第一次探测为什么静默失败。
- 开机时 `APM_CMD_GET_SPF_STATE`（0x1001021）总是超时 5 秒；其他 SM8450 移植也有相同现象，被认为无害。
- 第二次重启后，手机超过 30 分钟没有重新连上网络，原因未知。参照此前 A 槽因缺少启动成功标记耗尽重试次数的经历，怀疑 B 槽也是同样情况，需在手机旁确认。

## 2026-11-12 根因：DT 路由引用不存在的 widget

第三次开机（槽位 B，`qbootctl` 显示 B 为唯一可启动槽位且已标记成功，此前“重试次数耗尽”的猜测不成立）的日志显示，声卡探测停在 29 条 `ASoC: Failed to add route`，例如 `Analog Mic1 -> VA AMIC1`、`Digital Mic0 -> TX DMIC0`、`WCD_TX_OUTPUT -> TX SWR_INPUT`。这些 widget 在主线 lpass 宏/WCD938x 驱动中不存在，路由失败会使声卡放弃实例化（驱动核心对 `-ENODEV` 不打印错误，所以看起来像静默失败）。

修正：`audio-routing` 换成上游 `sm8450-hdk.dts` 的路由（去掉 WSA 扬声器条目）。新的 `vendor_boot-audio-test.img`（SHA-256 `70a5c017…`）同时包含该修正和扬声器 MI2S 修改，已复制到手机 `~/audio-test`，**尚未刷入**。路由修正与拓扑同样关键：不刷这个 DTB，耳机和麦克风也不会出现。

## 2026-11-12 刷入后的实机结果

`vendor_boot_b` 已写入（原分区备份 SHA-256 `0b873148…`，在手机 `~/audio-test/vendor_boot-backup-sde54.img` 和本地 `logs/audio-20261111/backup/`），重启正常。

| 项目 | 结果 |
| --- | --- |
| 声卡 | `card 0: OnePlus10Pro [OnePlus-10-Pro]`，播放 hw:0,0 / hw:0,1，录音 hw:0,2 / hw:0,3 |
| 耳机播放 hw:0,0 | `speaker-test` 正常运行无错误；未插耳机，未人耳确认 |
| 扬声器播放 hw:0,1 | `speaker-test` 正常运行；两颗 TFA9874 的 `SYS_CTRL0` 由 `0x0011` 变为 `0x0018`（上电、功放使能），`STATUS0` 的 NOCLK 位清零，说明 Tertiary MI2S 时钟已送达功放；**用户确认扬声器出声** |
| 内置麦克风 | hw:0,2 只接受双声道。当时测得 ADC1 在声道 0 去直流 RMS 约 1290、峰值 16001，通过 PipeWire 录音去直流 RMS 645；**后来按 100 ms 分窗复查，这只是启动瞬态，稳定段没有信号**，不能算作麦克风可用 |
| PipeWire / UCM | 配置组合 `HiFi (Headphones, Mic1, Speaker)`；输出为扬声器（默认）和耳机，输入为内置麦克风（默认）和耳机麦克风 |

UCM 修正：麦克风设为 `CaptureChannels 2`（单声道会使 PipeWire 丢弃 Mic1）；耳机音量控件改为 `HP`（`HP Digital` 不存在）。

已知遗留：
- 开机时 `APM_CMD_GET_SPF_STATE` 仍超时 5 秒，不影响使用。
- `MultiMedia4 Capture` 没有路由（未在 UCM 中使用）。
- 扬声器无保护：PipeWire 重载后音量可能被重置为 100%，建议保持在 40% 左右。
- 耳机插拔检测（FSA4480 + MBHC）尚未测试。

## 实机测试步骤

测试包已在手机 `~/audio-test`（拓扑、UCM、`vendor_boot-audio-test.img`、脚本、`SHA256SUMS`）。

**阶段 1：耳机与麦克风（不写分区）**

```sh
cd ~/audio-test
sudo bash negroni-audio-test.sh install
```

脚本会安装 `alsa-utils`、拓扑和 UCM。安装后需要重启，然后执行 `sudo bash negroni-audio-test.sh probe`。出现声卡后，接入 USB-C 耳机转接器，执行 `sudo bash negroni-audio-test.sh tone`，它会依次播放耳机和扬声器测试音并录 3 秒麦克风到 `mic-test.wav`。在当前 DT 下扬声器预计无声。

**阶段 2：声卡 DT（写 `vendor_boot`，耳机、麦克风、扬声器都需要）**

先确认 Linux 所在槽位（2026-11-11 的记录为 `b`）：

```sh
sudo bash negroni-audio-test.sh flash-dt b
sudo reboot
```

脚本会先把原分区备份到 `~/audio-test/vendor_boot-backup-*.img`，再写入并校验。重启后执行 `tone` 测试扬声器。需要回退时执行 `sudo bash negroni-audio-test.sh restore b`。`vendor_boot-audio-test.img` 用 `images/7.3/vendor_boot.img` 的参数重新封装，DTB 相对旧版只有上述 3 处变化（已用 dtc 反编译对比），CPU 能力/功耗参数校验通过。

所有日志写入 `~/audio-test/audio-test-*.log`。

> 2026-11-12 11:25 起，手机 `vendor_boot_b` 是相机会话刷入的合并镜像（内核 `ead3411b6e6` 加上未提交的 S5KJN1 相机设备树改动，SHA-256 `326eed0b…`），已确认声卡 `OnePlus-10-Pro` 与相机 `s5kjn1 6-0010` 同时存在。手机上旧的 `vendor_boot-audio-test.img` 不含相机改动，已改名为 `*.STALE-no-camera.img`，不要再刷。之后更新 `vendor_boot` 时要从包含相机改动的工作树构建，或以已提交的内核为准。

## 构建集成（2026-11-12）

- 内核：音频设备树修复为 `linux` 提交 `ead3411b6e6`（只含音频改动），父仓库 gitlink 与 `patches/linux/local-7.3.bundle` 已更新，空仓库恢复测试通过。补丁副本见 [sm8450-oneplus-negroni-audio.patch](../config/audio/sm8450-oneplus-negroni-audio.patch)。
- rootfs：`configure-audio.sh`（新建）、`update-audio-image.sh`（续建）、`verify-audio-image.py`（封装前校验），已接入 `finalize-rootfs.sh`、`build.sh`、`pack-images.sh` 和 `check.sh`。在已有 `root.img` 的副本上实测安装、重复运行与篡改检测均符合预期。
- 拓扑二进制 `config/audio/firmware/OnePlus-10-Pro-tplg.bin` 随仓库提供，来源与哈希见同目录 `.source`。

## 尚未完成

- 内置麦克风：2026-11-14 傍晚已在运行中的 `vendor_boot_b` 去掉 `audio-codec` 的 `sleep` 状态并重启，ALSA `hw:0,2` 录到 1 kHz 测试音。内核提交 `67d9e35c9ac0` 已包含该改动，尚未用它重新构建镜像。耳机和耳机检测未重测。2026-11-14 20:04 通话上行已由对端听过，反馈听着还可以。实际偏置电压与 PDM 时钟波形仍未用仪器测过。
- 通话语音、通话录音与放音已单独成文，见[通话语音](call-audio.md)；通话下行、录音和向对方放音可用。内置麦克风的 ALSA 录音已恢复，2026-11-14 20:04 通话上行对端听着还可以。
- 单独重绑声卡会遇到 WCD TX 重新初始化超时，换拓扑或模块只能重启。

- 耳机出声与 USB-C 耳机插拔检测。
- 全新完整镜像的构建与刷入验证（目前只在已有镜像副本与手机现有系统上验证）。
- 扬声器保护（TFA9874 无 I/V 反馈与校准）。
- 开机时 `APM_CMD_GET_SPF_STATE` 5 秒超时。
- 可选：将拓扑与 UCM 提交到上游 audioreach-topology / alsa-ucm-conf。

<!-- superseded list below kept for history -->
### 旧待办（2026-11-11）


- 以上所有实机测试。
- 把 DT 补丁提交到 `linux/` 子模块并更新 bundle。
- 在 rootfs 构建中安装拓扑与 UCM（`configure-audio.sh` / `update-audio-image.sh` / 校验），需等实机确认可用后再加。
- 可选：将拓扑与 UCM 提交到上游 audioreach-topology / alsa-ucm-conf。
