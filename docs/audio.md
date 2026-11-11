# 音频（扬声器、麦克风、耳机）

状态日期：2026-11-12。**尚未出声**：拓扑和 UCM 已安装到手机，拓扑能被加载，但声卡仍未生成（见下方实机结果）。扬声器 DT 尚未刷入。

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
- 麦克风映射沿用 SM8450/SM8550 HDK（AMIC1 → ADC1 内置麦克风、AMIC2 → ADC2 耳机麦克风），尚未确认一加的实际走线。
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

## 尚未完成

- 以上所有实机测试。
- 把 DT 补丁提交到 `linux/` 子模块并更新 bundle。
- 在 rootfs 构建中安装拓扑与 UCM（`configure-audio.sh` / `update-audio-image.sh` / 校验），需等实机确认可用后再加。
- 可选：将拓扑与 UCM 提交到上游 audioreach-topology / alsa-ucm-conf。
