# 音频（扬声器、麦克风、耳机）

状态日期：2026-11-11。**尚未实机验证**：本文档记录的拓扑、DT 和 UCM 修改都在主机上编译通过，测试包已复制到手机 `~/audio-test`，但由于需要 root，安装和播放/录音测试还没有执行。

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
| [config/audio/sm8450-oneplus-negroni-speaker-mi2s.patch](../config/audio/sm8450-oneplus-negroni-speaker-mi2s.patch) | 内核 DT：扬声器链路由 `TERTIARY_TDM_RX_0` 改为 `TERTIARY_MI2S_RX`，并添加 Tertiary MI2S 位时钟投票。目前只在 WSL 内核树中未提交，尚未进入 `linux/` 子模块 |
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
- 麦克风映射沿用 SM8450/SM8550 HDK（AMIC1 → ADC1 内置麦克风、AMIC2 → ADC2 耳机麦克风），尚未确认一加的实际走线。
- 耳机通过 USB-C 模拟转接（FSA4480），插拔检测和模式切换是否正常尚待测试。

## 实机测试步骤

测试包已在手机 `~/audio-test`（拓扑、UCM、`vendor_boot-audio-test.img`、脚本、`SHA256SUMS`）。

**阶段 1：耳机与麦克风（不写分区）**

```sh
cd ~/audio-test
sudo bash negroni-audio-test.sh install
```

脚本会安装 `alsa-utils`、拓扑和 UCM，重新绑定 APM 服务并打印声卡信息。如果没有出现声卡，重启一次后执行 `sudo bash negroni-audio-test.sh probe`。出现声卡后，接入 USB-C 耳机转接器，执行 `sudo bash negroni-audio-test.sh tone`，它会依次播放耳机和扬声器测试音并录 3 秒麦克风到 `mic-test.wav`。在当前 DT 下扬声器预计无声。

**阶段 2：扬声器 DT（写 `vendor_boot`）**

先确认 Linux 所在槽位（2026-11-11 的记录为 `b`）：

```sh
sudo bash negroni-audio-test.sh flash-dt b
sudo reboot
```

脚本会先把原分区备份到 `~/audio-test/vendor_boot-backup-*.img`，再写入并校验。重启后执行 `tone` 测试扬声器。需要回退时执行 `sudo bash negroni-audio-test.sh restore b`。`vendor_boot-audio-test.img` 用 `images/7.3/vendor_boot.img` 的参数重新封装，DTB 相对旧版只有上述 3 处变化（已用 dtc 反编译对比），CPU 能力/功耗参数校验通过。

所有日志写入 `~/audio-test/audio-test-*.log`。

## 尚未完成

- 以上所有实机测试。
- 把 DT 补丁提交到 `linux/` 子模块并更新 bundle。
- 在 rootfs 构建中安装拓扑与 UCM（`configure-audio.sh` / `update-audio-image.sh` / 校验），需等实机确认可用后再加。
- 可选：将拓扑与 UCM 提交到上游 audioreach-topology / alsa-ucm-conf。
