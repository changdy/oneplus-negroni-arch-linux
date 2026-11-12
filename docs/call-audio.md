# 通话语音（AudioReach，实验）

状态日期：2026-11-12。设备 NE2210，内核 `7.3.0-sm8450+`，中国电信 VoLTE。这里只写当前结论、用法和已知问题；当天的完整调试过程见[调试记录](archive/call-audio-bringup-2026-11-12.md)，整理过的依据见[研究记录](../artifacts/call-audio-research-20261112/README.md)。

## 现状

| 功能 | 状态 | 依据 |
| --- | --- | --- |
| 通话下行（听到对方） | **可用**，通话时自动打开 | DSP 日志：VCPM 进入运行态，EVS 解码器处理下行语音帧；用户在一通来电中反馈“好像听到一个声音”。音量和清晰度没有仔细听过 |
| 向对方播放音频 | **可用**（`hw:0,6`） | 用户在被叫手机上听到 1 kHz 测试音：干净、无失真、音量略偏大 |
| 通话录音 | **可用**（`hw:0,7`） | 16 秒双声道录音：下行声道有对端的声音，上行声道有注入的测试音。内容只看过电平，没有人工听过 |
| 通话上行（对方听到本机麦克风） | **不可用** | 录音的上行声道在测试音之外样本全为 0；内置麦克风稳定录音为零 |
| 回声消除、扬声器保护 | 没有 | 厂商的设备后处理模块需要 FastRPC audio PD，没有启用 |
| 听筒/免提切换、耳机、蓝牙通话 | 未测 | 下行固定走扬声器 |
| 自动接听 | 未做 | |

只在一种条件下验证过：电信 VoLTE，下行 EVS、上行 AMR-WB，16 kHz。其他网络、声码器和采样率未测。

## 工作方式

SM8450 用 GPR/AudioReach，通话音频由 DSP 里的 VCPM 管理，不能套用旧 APR 平台的 q6voice。主机不传输通话 PCM 数据，只负责打开图。

- **语音图**：从手机自己的 ACDB 提取 handset RX/TX 图，生成两个不传数据的前端：MM5（下行，到 Tertiary MI2S 扬声器）和 MM6（上行，来自 TX Codec DMA 3）。原有 MM1–MM4 保留。
- **VCPM 的放行条件**：打开图时 VCPM 会统计每个方向的流容器和后处理容器，任一方向没有后处理容器就一直推迟启动（`Defer Prepare operation as complete graph is not yet opened`），而且不向主机报错，表现为 PCM 显示 RUNNING 却没有声音。所以即使不用厂商的后处理模块，每个方向也保留一个后处理容器：TX 是 `b00000b1`（转换器 `4446` 加 SmartSync `4449`），RX 是 `b0000044`（转换器 `41DD` 加增益 `41DA`）。
- **下行音量**：厂商的音量级不在图里，RX 用独立增益固定在 −24.08 dB。
- **通话录音与放音**：另外两个传数据的前端，接在语音图的模块上，没有自己的硬件端点。

  | PCM | 方向 | 接法 |
  | --- | --- | --- |
  | `MultiMedia7 InCall`（`hw:0,6`） | 播放 | 主机 → 解码 → 转换 → MFC `4596` → 通话 TX 流的 MFC `458b` 端口 2 |
  | `MultiMedia8 InCall`（`hw:0,7`） | 录音 | 原厂录音图 `b00000d0`，抽头是分路器 `4561`（下行）和 `4560`（上行，在放音混入点之后）的端口 3 |

  录音的声道由 MUX_DEMUX 的模式决定：1 只录上行，2 只录下行（只有对方的声音），3/4 左声道上行、右声道下行。实测用的是模式 4。
- **内核**：语音图需要 `config/audio/sm8450-audioreach-voice.patch`（hostless 前端、VCPM 校准共享内存、跨图控制连接、路由修正）。录音和放音没有再改内核：起点在语音图里的跨图连接作为原始的图打开参数下发，后端用不带控件的 DAPM 路由挂接。

## 文件

| 文件 | 用途 |
| --- | --- |
| [voice-topology.py](../config/audio/voice/voice-topology.py) | 把提取的 handset 图和校准转成语音图的拓扑片段 |
| [incall-topology.py](../config/audio/voice/incall-topology.py) | 生成通话录音和放音两个前端 |
| [build-voice-topology.sh](../scripts/build-voice-topology.sh) | 合并基础媒体拓扑并用 `alsatplg` 编译 |
| [negroni-call-audio.py](../config/audio/voice/negroni-call-audio.py)、[.service](../config/audio/voice/negroni-call-audio.service) | 通话期间自动打开和关闭语音图 |
| [negroni-voice-test.py](../config/audio/voice/negroni-voice-test.py) | 限时手动打开语音图；服务复用它的 PCM 和 mixer 代码 |
| [install-test.sh](../config/audio/voice/install-test.sh) | 安装或恢复三个实验内核模块和拓扑，不重启 |
| [sm8450-audioreach-voice.patch](../config/audio/sm8450-audioreach-voice.patch)、[sm8450-oneplus-negroni-dmic.patch](../config/audio/sm8450-oneplus-negroni-dmic.patch) | 内核改动，仅以补丁形式保存 |

原厂 ACDB、提取出的图和校准、生成的拓扑、内核模块和原始日志都在本地 `logs/call-audio-20261112/`，不纳入 Git。校准来自手机自己的 `~/android-ro/odm_b/etc/acdbdata/acdb_cal.acdb`，SHA-256 `da0cd92a94e77d6f7894de44f4afe4c701715ba46c6cf9bbe0b45fe1ea1ab63a`。许可见[来源与许可](licensing.md)。

## 构建拓扑

ACDB 提取用 Qualcomm [AudioReach graphservices](https://github.com/AudioReach/audioreach-graphservices/tree/e0ecb6a1f10b9a0fced2de8101160e160ad02e5d) 和参考项目 [diting-ubuntu](https://github.com/royka1/diting-ubuntu/tree/c68ff47db94792fb5fd608e98d1ae489c2e592b1) 的 `acdb-query`，查询键保存在本地 `acdb/extract.sh` 和 `acdb/extract-incall.sh`。

```sh
# 只有通话语音
bash scripts/build-voice-topology.sh /path/to/audioreach-topology \
  logs/call-audio-20261112/acdb/handset-rx \
  logs/call-audio-20261112/acdb/handset-tx \
  logs/call-audio-20261112/OnePlus-10-Pro-voice-tplg.bin

# 加上通话录音和放音
INCALL_MUSIC_DIR=logs/call-audio-20261112/acdb/incall/music \
INCALL_RECORD_DIR=logs/call-audio-20261112/acdb/incall/rec-c \
INCALL_MUX_CONFIG=logs/call-audio-20261112/acdb/incall/tool/rec-mode4.bin \
bash scripts/build-voice-topology.sh ...同上四个参数...
```

| 拓扑 | SHA-256 | 状态 |
| --- | --- | --- |
| 只有通话语音 | `23bcdd6dfdfd6946f73637c8dc6565fe6769ca25f1ee3cdd2b09baddc9bec7b9` | 实测通过，手机上留有备份 |
| 通话语音 + 录音 + 放音（MUX 模式 4） | `5fb6fba602ed054da1319f06104c374289f9d38ab8955220bd8d7312f64e15a3` | 实测通过，**手机当前安装的版本** |

加 `--loopback` 生成 DSP 内部回环版（8 kHz，不经过基带），只用于诊断；它和真实通话停在同样的位置，但没有验证过能否听到回环声。

`alsatplg` 会对四个硬件后端报 undefined widget，这些部件由内核后端驱动提供，属于预期；其他错误不能忽略。

## 安装与使用

拓扑在 `/usr/lib/firmware/qcom/sm8450/OnePlus-10-Pro-tplg.bin`，三个实验模块在 `/usr/lib/modules/7.3.0-sm8450+/kernel/sound/soc/qcom/qdsp6/`。都只改根文件系统，不刷分区，但**换拓扑或模块后必须重启**（见下文“不能热更新”）。

通话音频服务装在 `/usr/local/libexec/negroni-voice/`，已设为开机自启：

- 有通话处于 `ringing-out` 或 `active` 时打开 MM5/MM6，没有时关闭并恢复改动过的 mixer 值；来电振铃阶段不打开。
- 打开前把桌面声音服务（PipeWire/PulseAudio）的声卡 profile 切到 `off`，关闭后切回。否则通话期间桌面打开的媒体流会让扬声器 PCM 卡死，麦克风输入也会从 PipeWire 中消失。副作用是通话期间桌面提示音不响。
- 原 profile 记录在 `/run/negroni-call-audio.json`，服务异常退出后下次启动时据此还原。
- 它不拨号、不接听、不挂断、不录音，也不管理 `hw:0,6` 和 `hw:0,7`。

```sh
sudo systemctl disable --now negroni-call-audio.service   # 停用
journalctl -u negroni-call-audio.service    # 查看每次通话的打开/关闭
```

通话中录音和放音（必须在通话接通、语音图已打开之后，并在挂断前结束）：

```sh
arecord -D hw:0,7 -f S16_LE -r 48000 -c 2 --period-size=1920 --buffer-size=7680 -d 16 call.wav
aplay   -D hw:0,6 --period-size=1920 --buffer-size=7680 clip.wav
```

- 录音周期不能小于 6144 字节，且要是 480 帧的整数倍。
- 放音的电平只能由文件本身控制。幅度 8000（约 −12 dBFS）的测试音在对端听起来略偏大，真实音频建议再低 3–6 dB；这是估计值，换成语音后需要重新听。

## 已知问题

- **麦克风无信号**。原厂用 DMIC3/DMIC4，不是最初假定的 ADC1。DMIC3 的引脚、MIC BIAS3、2.4 MHz 时钟已按 OnePlus 下游源码配置并刷入 `vendor_boot_b`，寄存器读值符合预期，但稳定段录音仍为零，只有启动瞬态。`MICB3_TEST_CTL_2` 的两次试验一次无效、一次无结论。
- **重启后 IMS 承载经常不自动建立**，拨号返回 `InvalidArgument`，见[基带说明](modem.md)。
- **通话之外打不开 `hw:0,6`/`hw:0,7`**。桌面声音服务探测它们时，内核会记录 `set config … rejected` 或 `Failed to Start Graph`。普通播放和录音不受影响。
- **录音和放音必须先于语音图关闭**，目前没有任何保护；语音图先关闭时 DSP 的行为没有测过。
- **`TX_AIF1_CAP Mixer DEC0` 还原失败**：关闭语音图时该控件停在 `on`，手动设回 `off` 也无效，不打电话也能复现，原因未查。桌面 profile 切回后 UCM 本来也会把它设为 `on`，所以通话前后状态一致。
- **扬声器没有保护**，桌面音量可能是 100%；通话下行不受桌面音量影响。
- **不能热更新**：unbind/bind 或卸载 `qcom-apm` 会丢失 GPR port 1；单独重绑声卡时 WCD TX SoundWire 设备无法重新上线。换模块或拓扑只能重启。
- **内核改动没有走完流程**：只有补丁文件，没有在 `linux/` 中提交，gitlink 和 `local-7.3.bundle` 未更新；WSL 内核树里还混有相机会话未提交的改动。
- **没有接入镜像构建**，全新刷入的系统不包含以上任何内容。
- 运行中有两类未评估的 DSP 消息：mailbox 的 `intent set param … failed result 4`，以及 EVS 解码器的 `unsupported bandwidth(-1)`。

## 未测

通话保持与多方通话、来电时铃声到语音图的衔接、长时间通话和录音、只录对方的单声道模式、语音内容经编码后的可懂度、其他声码器与采样率、漫游或其他运营商。

## 排查方法

VCPM 的拒绝不会以错误返回给主机，只能看 ADSP 的 F3 日志。

1. 用本地 `adsp-f3` 工具限时采集（仅文字，不含音频数据）。
2. 本机固件剥掉了大部分日志文字，但消息哈希只取决于“源文件名 + 格式串”：取 MD5 最后四字节按大端解释，低两位为零时加一。上游 [linux-firmware](https://gitlab.com/kernel-firmware/linux-firmware) 里的公开 ADSP 固件（`qcom/sc8280xp/LENOVO/21BX/qcadsp8280.mbn`、`qcom/qcs6490/radxa/dragon-q6a/adsp.mbn`、`qcom/sa8775p/adsp.mbn` 等）保留了这些字符串，从中提取 `文件名.c:格式串` 求哈希即可对上。两份通话日志的 797 个哈希对上 793 个，VCPM 的消息全部可读。只采用哈希完全相同的条目。
3. 先看 `vcpm_process_proxy_graph_info_cmd` 的容器计数、`vcpm_utility_update_sg_states` 的 `apps_state`/`modem_state`，以及 `vcpm_graph_*_sequencer` 走到哪一步。

工具和映射在本地 `logs/call-audio-20261112/vcpm-why/`（`binhash.py`、`dec.py`）。

## 下一步

- 自动接听，并把“接通 → 录音 → 播放固定音频 → 挂断”做成一个服务，同时让它管理录音和放音的关闭顺序。
- 修好内置麦克风。
- 让重启后的 IMS 承载自动恢复。
- 把内核改动提交到内核树，再接入镜像构建。
