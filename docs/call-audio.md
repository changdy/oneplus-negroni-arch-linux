# 通话语音（AudioReach，实验）

状态日期：2026-11-14 21:59（对端人耳确认通话听着还可以；听筒/免提切换用户确认可以了）。设备 NE2210，内核 `7.3.0-sm8450+`，中国电信 VoLTE。这里只写当前结论、用法和已知问题；通话调试过程见[2026-11-12 调试记录](archive/call-audio-bringup-2026-11-12.md)，整理过的依据见[研究记录](../artifacts/call-audio-research-20261112/README.md)，新增麦克风实机对照见[原厂 DMIC 路由与共享时钟](../artifacts/mic-clock-20261113/README.md)。

## 现状

| 功能 | 状态 | 依据 |
| --- | --- | --- |
| 通话下行（听到对方） | **可用**，通话时自动打开 | DSP 日志：VCPM 进入运行态，EVS 解码器处理下行语音帧；用户在一通来电中反馈“好像听到一个声音”。音量和清晰度没有仔细听过 |
| 向对方播放音频 | **可用**（`hw:0,6`） | 用户在被叫手机上听到 1 kHz 测试音：干净、无失真、音量略偏大 |
| 通话录音 | **可用**（`hw:0,7`） | 16 秒双声道录音：下行声道有对端的声音，上行声道有注入的测试音。内容只看过电平，没有人工听过 |
| 通话上行（对方听到本机麦克风） | **可用** | 2026-11-14 20:01 拨出后语音图打开。8 秒 `hw:0,7` 录音里上行每秒 RMS 43–224、峰值 330–1602；下行前 6 秒接近 0，第 8 秒 RMS 5888、峰值 27394。用户在对端听完并自行挂断，反馈听着还可以。没有回声消除。拨号前 RX SoundWire 告警曾对空 regmap 读寄存器，控制器中断线程因此退出；修复为内核 `baa7d74668f4`，三个编解码器模块随这次重启装入后没有再崩溃 |
| 回声消除、扬声器保护 | 没有 | 厂商的设备后处理模块需要 FastRPC audio PD，没有启用 |
| 听筒/免提切换 | **可用** | 2026-11-14 21:56 拨出 `18649735816`。振铃时两颗功放 `L=0x0018 R=0x0018`；写入 `earpiece` 后右侧关掉并保持到接通（`R=0x0010`）；再写回 `speaker` 后两侧都是 `0x0018`。用户确认这次切换可以了。没有加载原厂 receiver 音效，音量可能与原厂听筒不同 |
| 耳机、蓝牙通话 | 未做 | 没有耳机和蓝牙的通话路由 |
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
- **内核**：语音图在内核提交 `81637d2a07f3`（hostless 前端、VCPM 校准共享内存、跨图控制连接、路由修正）。录音和放音的起点在语音图里，作为原始的图打开参数下发，后端用不带控件的 DAPM 路由挂接。

## 文件

| 文件 | 用途 |
| --- | --- |
| [voice-topology.py](../config/audio/voice/voice-topology.py) | 把提取的 handset 图和校准转成语音图的拓扑片段 |
| [incall-topology.py](../config/audio/voice/incall-topology.py) | 生成通话录音和放音两个前端 |
| [build-voice-topology.sh](../scripts/build-voice-topology.sh) | 合并基础媒体拓扑并用 `alsatplg` 编译 |
| [negroni-call-audio.py](../config/audio/voice/negroni-call-audio.py)、[.service](../config/audio/voice/negroni-call-audio.service) | 通话期间自动打开和关闭语音图 |
| [negroni-voice-test.py](../config/audio/voice/negroni-voice-test.py) | 限时手动打开语音图；服务复用它的 PCM 和 mixer 代码 |
| [install-test.sh](../config/audio/voice/install-test.sh) | 安装或恢复三个实验内核模块和拓扑，不重启 |
| [sm8450-audioreach-voice.patch](../config/audio/sm8450-audioreach-voice.patch)、[sm8450-oneplus-negroni-dmic.patch](../config/audio/sm8450-oneplus-negroni-dmic.patch) | 语音图内核改动已进入内核提交 `81637d2a07f3`；补丁文件仍保留对照。DMIC 偏置试验没有进入该提交 |
| [sm8450-oneplus-negroni-dmic34-va.patch](../config/audio/sm8450-oneplus-negroni-dmic34-va.patch) | 2026-11-13—14 增量诊断候选：修正 VA CPU DAI、补齐 DMIC4，已刷入 B 槽并重启；VA 录音可以打开但仍无信号，DT 改动尚未接入正式源码/构建 |

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

镜像里的 `/usr/lib/firmware/qcom/sm8450/OnePlus-10-Pro-tplg.bin` 就是上表那份通话语音 + 录音 + 放音拓扑（`5fb6fba6…`）。`scripts/build-audio-topology.sh` 只生成桌面拓扑，不能单独再现这个文件。`configure-audio.sh` 会安装这份拓扑，并把通话服务装到 `/usr/local/libexec/negroni-voice/`、设为开机自启。2026-11-14 这次只把打包路径接上，没有构建新镜像，也没有刷入手机。手机上已有的服务和拓扑保持原样。换拓扑或语音模块后必须重启（见下文“不能热更新”）。

通话音频服务的行为：

- 有通话处于 `ringing-out` 或 `active` 时打开 MM5/MM6，没有时关闭并恢复改动过的 mixer 值；来电振铃阶段不打开。
- 打开前把桌面声音服务（PipeWire/PulseAudio）的声卡 profile 切到 `off`，关闭后切回。否则通话期间桌面打开的媒体流会让扬声器 PCM 卡死，麦克风输入也会从 PipeWire 中消失。副作用是通话期间桌面提示音不响。
- 原 profile 记录在 `/run/negroni-call-audio.json`，服务异常退出后下次启动时据此还原。
- 它不拨号、不接听、不挂断、不录音，也不管理 `hw:0,6` 和 `hw:0,7`。

```sh
sudo systemctl disable --now negroni-call-audio.service   # 停用
journalctl -u negroni-call-audio.service    # 查看每次通话的打开/关闭
```

通话中切换听筒和免提（服务约每秒读一次；默认免提）：

```sh
echo earpiece > /run/negroni-call-audio.route   # 听筒：只留左侧 TFA9874
echo speaker  > /run/negroni-call-audio.route   # 免提：左右两颗都开
```

原厂 `handset` 路径是 `TFA_CHIP_SELECTOR=1` 加 profile `receiver`，`speaker` 是 selector `3` 加 profile `speaker`。主线 `tfa987x` 不加载 NXP 的 receiver 固件，这里只在语音图已经打开之后清掉右侧功放（I²C `0x35`）的放大使能位，左侧 `0x34` 继续播放。2026-11-14 21:53–21:54 用户听 10 秒单侧短音后确认：左侧 `0x34` 是手机正上方的喇叭，右侧 `0x35` 是手机下面的喇叭。右侧播放中寄存器为 `L=0x0010 R=0x0018`。通话过程中的实际切换已在 2026-11-14 21:56 用寄存器核对，并于 21:59 由用户确认可以了：拨出后振铃阶段两侧都开，服务按路由文件关掉底部功放并保持到接通，再打开底部功放，然后挂断。挂断时驱动会自行关掉两颗功放，下一次普通播放仍是双扬声器。音量和音色与原厂听筒不同，可能偏响。服务把这个文件设成 `audio` 组可写。2026-11-14 20:35 已装上并重启服务，日志是 `waiting for calls; output file /run/negroni-call-audio.route`，文件属主 `root:audio`、模式 `0664`。21:56 那通才听过切换。

通话中录音和放音（必须在通话接通、语音图已打开之后，并在挂断前结束）：

```sh
arecord -D hw:0,7 -f S16_LE -r 48000 -c 2 --period-size=1920 --buffer-size=7680 -d 16 call.wav
aplay   -D hw:0,6 --period-size=1920 --buffer-size=7680 clip.wav
```

- 录音周期不能小于 6144 字节，且要是 480 帧的整数倍。
- 放音的电平只能由文件本身控制。幅度 8000（约 −12 dBFS）的测试音在对端听起来略偏大，真实音频建议再低 3–6 dB；这是估计值，换成语音后需要重新听。

## 已知问题

- **内置麦克风的 ALSA 录音已在 2026-11-14 傍晚恢复**；20:04 对端人耳确认通话上行听着还可以。原厂用 DMIC3/DMIC4，不是最初假定的 ADC1。此前稳定段全零的排查保留在下面。`MICB3_TEST_CTL_2` 的两次试验一次无效、一次无结论。
  - **2026-11-14 下午的结论（取代下面各条里“没有时钟”的判断）**：从主 TLMM 一侧读同一焊盘（LPI gpio n 即 TLMM gpio 165+n），录音时 GPIO8、GPIO12 上都有约 2.4 MHz 的时钟，此前 LPI 一侧的采样读不到功能复用输出脚的电平；数据脚恒为 0，说明麦克风没有供电。原因是本机设备树给 `audio-codec` 写了 `sleep` 引脚状态并把复位脚 gpio43 配成 `output-low`：ASoC 在声卡空闲时选用该状态，WCD9385 一直处于复位，打开 PCM 时才放开，而带隙和模拟偏置的初始化只在驱动探测时做过一次，之后的 regcache 回写赶在芯片重新枚举之前，落空了（上午旁路读到的 `SLEEP_CTL` 硬件 0x16、缓存 0xde 即此状态）。MICBIAS 寄存器写上了，偏置脚没有输出。
  - 不刷机验证：空闲时手动把 gpio43 置高，让 TX SoundWire 从设备枚举后再经历一次运行时挂起/恢复（回写到已枚举的芯片），随后按原厂路由录音。两路数据脚出现约 49% 占空的 PDM 数据，两声道稳定段非零；扬声器播放 1 kHz 测试音的两秒内，1 kHz 分量左 252–255、右 350–354，其余时间 ≤1.1。试验后已全部复原。
  - 2026-11-14 傍晚已把同样的改动刷进 `vendor_boot_b` 并重启：`pinctrl-names` 只保留 `default`，删掉 `pinctrl-1`。空闲时 gpio43 保持高电平、引脚状态保持 `default`，从设备保持已枚举。没有再做手动置位。8 秒 ALSA 录音录到 2 秒 1 kHz 测试音（左 172/158，右 448/407）。之后三次短振结束即录 10 秒，并从喇叭外放，用户听过；第 1 秒是满幅启动瞬态，其后 9 秒 RMS 约 27–86。通话上行、桌面录音、耳机及耳机检测误报仍未测。内核提交 `67d9e35c9ac0` 已包含该改动，尚未重新构建镜像。数值见[刷入记录](../artifacts/mic-clock-20261113/README.md#2026-11-14-傍晚去掉-sleep-状态并刷入验证)。
  - 以下各条是此前的排查记录，其中“GPIO 无时钟翻转”均来自 LPI 一侧的读回，不能再当作时钟不存在的依据；偏置、BOB、eFuse 等对照都是在 WCD9385 模拟部分未上电的状态下做的，结论需要在修复后重新评估。
  - 2026-11-12 晚用限时诊断模块直接读 LPI 引脚电平（脚本和源码在本地 `logs/mic-20261112/`），观察到 **GPIO8 没有软件可见的时钟翻转**，尚无物理波形测量，不能单凭该采样确定直接根因：
    - 录音期间 GPIO8（`dmic2_clk`）两万次采样零翻转；同样方法读 SoundWire 时钟脚 GPIO0 约一半为 1、翻转上万次。把 GPIO8 临时改成普通 GPIO 输出，读回能跟随高低电平，所以读回可信。
    - VA 宏硬件寄存器直读 `0x000=1`、`0x004=1`、`0x080=2`、`0x088=5`（使能、四分频），不是 regmap 缓存假象。改二分频、十六分频、重新使能，或把 GPIO8 切到其余四个复用功能后，软件采样仍无翻转。
    - 数据脚 GPIO9 在当时试验中完全跟随上下拉，未观察到麦克风主动输出。保持 `dmic2_data` 功能只加上拉时，录音立刻出现大幅跳变，说明“数据脚 → TX 宏解码器 → 录音”这一段是通的。
    - 置配置寄存器 bit 11、去掉时钟脚输出使能位，都无效。录音同时让 MIC BIAS2/MIC BIAS4 上电也无效。
    - 临时申请 `VA_CORE_MCLK` 成功但仍无时钟。**随后申请 `VA_CORE_2X_MCLK` 和 `TX_CORE_NPL_MCLK` 超时（−110），ADSP 的 `audio_process` 崩溃（`PRM:0xba`），内核在 ADSP 重启路径上 oops，手机卡死，只能强制重启。不要再做申请额外 q6prm 时钟的试验。**
  - DMIC4 的设备树原先未配齐：它在另一组引脚（GPIO12/13，`dmic3_clk`/`dmic3_data`）。2026-11-13 对照本机原厂 DTBO 的量产候选 0/11，更正其偏置为 **MIC BIAS1**（旧记录误写为 BIAS4）。临时添加引脚复用、`TX DMIC4 -> VA DMIC4`、MIC BIAS1 与 VA_MCLK 依赖后，VA `0x08c=5`、MICB1=`0x50`，DAPM 显示对应 widget 均为 On；两轮 12 秒录音的第一秒之后仍全零，GPIO8/12 各两万次采样均无翻转。上述临时试验已恢复；后续同样的引脚/依赖已随 VA CPU DAI 候选部署到 B 槽并重启，仍无信号。
  - 原厂 `lpass_cdc_dmic_clk_enable` 已由本机模块反汇编确认：按 DMIC 对维护 TX/VA 共享引用计数，操作 VA DMIC_CFG 和 `0x084/088/08c/090` 的分频、使能。函数本身不申请 PRM 时钟。补齐试验中现有 TX_CORE_MCLK、FS generator 和两个 DMIC 门控均已使能，仍不能恢复采集；不能把“主线缺少共享函数”直接当成全部根因。细节和数值见[2026-11-13 记录](../artifacts/mic-clock-20261113/README.md)。
  - `VA Capture` 的 CPU DAI 原先与 TX 重复，现已在运行 DT 改为 `VA_CODEC_DMA_TX_0` 并重启验证：可以正常完成独立 VA 录音，12 秒稳定段仍全零。完整分区备份与回滚材料保留。
  - 2026-11-14 已修正 TX/VA 多通道 mixer 的重复计数/关闭遗漏，以及 TX 只静音最后一个解码器的问题；内核提交 `463023bf84b1`，对应模块已安装并重启验证。UCM 的 Mic1 改为 DMIC3/4、两路 0 dB，真实 UCM 启停和 11 个控件还原均通过；新 TX 12 秒、VA 6 秒录音稳定段仍全零。
  - 逐路弱上下拉试验确认 GPIO9 对应左声道、GPIO13 对应右声道，两个数据输入到 PCM 的对应关系有效。BOB 实际请求到 3.320 V 并配合原厂 MICBIAS 初始化顺序仍无信号，电压/寄存器已恢复；此前精确 3.296 V 请求在写入前失败，不能作为有效电压对照。全部整理结果见[续测记录](../artifacts/mic-clock-20261113/README.md)。
  - 用户确认刷机前没有测试原厂麦克风，原厂正常采集基线仍缺失。2026-11-14 对照本机 WCD 模块发现主线省略 eFuse30 → SLEEP_CTL 校准；运行时字段调整、启动时实验模块，以及原厂偏置顺序/BOB 组合均未恢复信号。实验 WCD 模块已还原并重启，详见[续测记录](../artifacts/mic-clock-20261113/README.md#同日续测原厂基线未测与-wcd9385-启动校准)。
  - “VA 宏分频寄存器正确但 GPIO 软件采样没有时钟翻转”已在 2026-11-14 下午查明是 LPI 读回方式的问题，见本节开头。物理波形、偏置电压仍没有用仪器测过，原厂 Android 下采集和 TX/VA 并发未测。
- **重启后 IMS 承载经常不自动建立**，拨号返回 `InvalidArgument`，见[基带说明](modem.md)。
- **通话之外打不开 `hw:0,6`/`hw:0,7`**。桌面声音服务探测它们时，内核会记录 `set config … rejected` 或 `Failed to Start Graph`。普通播放和录音不受影响。
- **录音和放音必须先于语音图关闭**，目前没有任何保护；语音图先关闭时 DSP 的行为没有测过。
- **多通道 mixer 还原问题已修正**：2026-11-14 更新 TX/VA 模块并重启后，两路 UCM mixer 均能关闭，完整还原通过。新驱动下的实际通话建立/挂断回归未测，不能据此宣称通话流程的全部还原问题已验证。
- **扬声器没有保护**，桌面音量可能是 100%；通话下行不受桌面音量影响。
- **不能热更新**：unbind/bind 或卸载 `qcom-apm` 会丢失 GPR port 1；单独重绑声卡时 WCD TX SoundWire 设备无法重新上线。换模块或拓扑只能重启。
- **语音图和 DMIC 设备树实验仍未走完内核流程**：这些改动仍只保留补丁和测试部署，未纳入固定源码；WSL 内核树里还混有相机会话未提交的改动。TX/VA 通道状态修正已独立提交，gitlink 和 `local-7.3.bundle` 已更新，不能据此认为其他实验也已接入构建。
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
- 用内核提交 `67d9e35c9ac0` 重新构建镜像。运行中的 `vendor_boot_b` 已是同一改动的字节补丁，ALSA 录音、外放和这次通话上行已验证。
- 让重启后的 IMS 承载自动恢复。
- RX 中断修复已提交为内核 `baa7d74668f4` 并写入恢复 bundle。完整镜像尚未重建。
