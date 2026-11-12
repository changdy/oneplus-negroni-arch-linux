# 通话语音调试记录（2026-11-12）

> 这是 2026-11-12 当天按时间顺序写下的调试过程，保留作为依据，其中较早的小节反映的是当时尚未解决的状态。当前结论、用法和已知问题见[通话语音](../call-audio.md)。

状态日期：2026-11-12。用户已确认可以拨打、接听电话。17:19 的一通来电中 VCPM 首次放行并运行语音子图，用户反馈“好像听到一个声音”；下行是否清晰、上行（麦克风）是否可用仍未确认。

USB SSH 实机检查显示声卡只有 MultiMedia1/2 播放和 MultiMedia3/4 录音，没有基带语音图。普通扬声器、麦克风可用并不代表通话链路可用。SM8450 使用 GPR/AudioReach/VCPM，不能直接套用旧 APR 平台的 q6voice。

## 候选方案

参考 [royka1/diting-ubuntu](https://github.com/royka1/diting-ubuntu/tree/c68ff47db94792fb5fd608e98d1ae489c2e592b1) 的补丁 0046、0049、0050；该项目记录的是 SM8475 的 3G 双向语音，不能据此认定本机电信 VoLTE 已可用。

- 内核添加 hostless AudioReach 图、VCPM 校准共享内存、跨图控制链接；没有用户态 PCM 数据传输。
- 保留 MM1–MM4，新增 MM5（通话下行）和 MM6（通话上行）。
- 从本机原厂 ODM 的 ACDB 提取 handset RX/TX 图，映射到 Tertiary MI2S 扬声器与 TX Codec DMA 3；内置麦克风的实际 DMIC 路由正在补查。
- 第一阶段跳过需要 FastRPC audio PD 的设备后处理模块，因此**没有回声消除**，也未添加 TFA9874 扬声器保护。每个方向仍保留一个不含厂商模块的后处理容器，否则 VCPM 不会启动通话（见下文“VCPM 消息解码与直接原因”）。
- 单独插入 48 kHz/S16/stereo 下行转换器、16 kHz/S16/mono 上行转换器和 −24.08 dB 下行增益。上行暂固定 16 kHz，其他协商语音采样率未测。
- 测试脚本最多运行 300 秒，默认 20 秒；检测 PCM 占用，保存并恢复所有改动的 mixer 值，不自动拨号或录音。

原厂 ACDB 的 I2S 端点是 `0x425d`，映射为现有拓扑的 `0x6061`；麦克风端点 `0x43af` 映射为 `0x6090`。实际音量索引是 0–8，不能照搬参考机型的 0–4。去掉设备后处理也会去掉原来的音量控制，所以必须独立设置低增益。

## 文件与构建

| 文件 | 用途 |
| --- | --- |
| [voice-topology.py](../../config/audio/voice/voice-topology.py) | 将本机提取的图与校准转为 ALSA 拓扑片段 |
| [build-voice-topology.sh](../../scripts/build-voice-topology.sh) | 合并现有媒体拓扑并用 `alsatplg` 编译 |
| [negroni-voice-test.py](../../config/audio/voice/negroni-voice-test.py) | 限时打开通话图并恢复路由 |
| [install-test.sh](../../config/audio/voice/install-test.sh) | 检查测试包哈希与模块 ABI，备份、安装或恢复；不重启 |
| [negroni-call-audio.py](../../config/audio/voice/negroni-call-audio.py) 与 [.service](../../config/audio/voice/negroni-call-audio.service) | 通话期间自动打开/关闭语音图，并暂时收走桌面声音服务的声卡 |

本地原始资料、校准、模块与测试包在 `logs/call-audio-20261112/`，不纳入 Git。校准来自手机自己的 `~/android-ro/odm_b/etc/acdbdata/acdb_cal.acdb`，SHA-256 为 `da0cd92a94e77d6f7894de44f4afe4c701715ba46c6cf9bbe0b45fe1ea1ab63a`。

ACDB 提取使用 Qualcomm [AudioReach graphservices](https://github.com/AudioReach/audioreach-graphservices/tree/e0ecb6a1f10b9a0fced2de8101160e160ad02e5d) 和参考项目的 `acdb-query`；查询键保存在本地 `acdb/extract.sh`。图生成脚本和测试 PCM 顺序的参考代码为 GPL-2.0，原厂校准与生成二进制不随源码发布。

```sh
bash scripts/build-voice-topology.sh /path/to/audioreach-topology \
  logs/call-audio-20261112/acdb/handset-rx \
  logs/call-audio-20261112/acdb/handset-tx \
  logs/call-audio-20261112/OnePlus-10-Pro-voice-tplg.bin
```

`alsatplg` 对已有四个硬件后端提示 undefined widget：这些 widget 由内核后端驱动提供，与原媒体拓扑相同。编译仍须成功退出并产出有效文件，不能忽略其他错误。

## 验证与限制

- 已完成：实机基线检查、原厂图提取、候选模块编译、拓扑编译与 RX/TX 主路径静态检查；6 项测试工具故障注入/恢复测试及仓库检查通过。
- 首次加载：驱动模块可加载，但声卡在首个媒体 widget 处返回 `-EINVAL`；generic buffer loader 的旧返回值被新错误传播逻辑放大，已修正。修正后用真实 C loader 对原媒体/候选拓扑及边界输入运行 104 项 ASan/UBSan 检查通过；仍须实机验证。首次失败时尚未打开 DSP 通话图。
- 修正版重启后已注册全部 6 个 PCM；MM5/MM6 可重复打开、配置、启动和关闭，3 秒独立测试退出为 0，路由恢复检查通过。这只能说明命令被接受，不能证明 VCPM 实际启动了语音子图。
- 实际 VoLTE：呼叫到达 `active`，用户确认双向无声。另一次暂停 PipeWire/WirePlumber 及其 socket、核对 MM5 输出路由开启后的独占测试仍双向无声，尚未修复。
- 媒体回归：hw:0,2 短时录音曾有非零 RMS，hw:0,1 的 0.5 秒低幅度播放曾退出 0。后续按 100 ms 窗口分析发现 ADC1 路径只有启动瞬间的信号，稳定段 RMS 约 0.3，不能据此认定录到了真实声音。
- 持续播放自检发现路由驱动缺陷：先开 MM2 后关 MM5，会无条件清掉后端的 MM2 连接，7 秒播放报 I/O 错误。改为先关未使用通道、最后开 MM2 后，7 秒播放和 9 秒录音均退出 0；已构建只清除匹配连接的内核修正，11 项真实 C 路由顺序/隔离检查通过，尚未加载该修正。声学录音仍未检测到三个已知测试频率，不能把 PCM 成功当作扬声器到麦克风的声学验证通过。
- 桌面集成待处理：拨号应用未运行时，通过 mmcli 拨号不会自动出现电话窗口；启动 plasma-dialer 后能识别通话。音频图运行期间，桌面服务曾尝试打开普通 MM3，产生 graph 2 错误，不能直接把当前手动脚本当作自动通话服务。
- DSP 本地回环：重启恢复声卡后，以 `0x12006000` 和 1000 ms 延时打开图，用户未听到回声。F3 日志确认 VCPM 选择 AMR/8 kHz，而候选 TX MFC 固定 16 kHz，存在采样率不匹配，尚不能把这次实验当作正确配置后的回环结果。
- 未测：可听见的窄带/宽带/超宽带通话、听筒/免提切换、回声消除。
- 测试候选暂未接入全新镜像构建，也未默认启用通话服务。
- 禁止通过 unbind/bind 或卸载 `qcom-apm` 来热更新，已知 GPR port 1 生命周期问题仍要求经用户同意后重启。
- **本机也不能依赖单独重绑声卡来热换拓扑**：2026-11-12 实测解绑 `snd-sc8280xp` 的 `sound` 设备后 APM/GPR 端口仍在、无共享内存解除映射错误，但重绑时 WCD TX SoundWire slave 无法重新上线，`Initialization not complete` / `-110`。强制 runtime-active 后 RX 恢复 Attached、TX 仍 UNATTACHED；已恢复原电源策略，不继续尝试不确定的 codec 解绑，改为经用户批准重启恢复。
- 目前候选只替换根文件系统中的三个音频模块与拓扑，不需要刷写 boot/vendor_boot 分区；安装器保存原文件与 SHA-256，回退后同样需要另行获准重启。

### DSP 日志定位（2026-11-12）

限时 F3 工具成功与 ADSP DIAG 握手，仅收集文字/字符串哈希日志，关闭二进制音频日志，结束后禁用掩码并撤销服务。原始日志和派生工具保存在忽略的 `logs/call-audio-20261112/`。

根据官方 AudioReach 源码重建部分 QShrink 哈希，与实机日志精确匹配，确认 RX 和 TX 的 PREPARE/START 回复都是 **`Permitted proxy sg list is empty`、状态 0**：APM 返回成功，但 VCPM 尚未授权任何语音子图启动。这解释了 PCM 状态为 RUNNING 而双向无声，下一步应定位 VCPM 的启动前置条件。VSID 已正确变为回环 ID；默认 VSID 跳过只出现在早期阶段。当前删除的 TX 设备处理子图包含唯一的 SmartSync 标签，此外 TX 通道信息/校准晚于 RX 的首次 PREPARE，均需继续验证，不能直接定为根因。

同批可读日志中，MFC 输出 48 kHz/stereo/S16，GAIN 模块接受并转发格式，增益 512 已设置；早期可选属性不支持的警告不能证明增益模块初始化失败。I2S 端点报告 `media_format_set: 0`。独立媒体测试的同类错误已对应到缺失 FE→后端数据连接，调整路由顺序后持续播放恢复。

原厂 `mixer_paths.xml` 的 handset-mic/speaker-mic 实际使用 `MSM_DMIC`、`DMIC3/DMIC4`，并非测试脚本最初假定的 ADC1/SWR_MIC0。运行时尝试 DMIC3 仍只有启动瞬态；当前设备树没有配置 TX 数字麦克风的引脚复用。这一硬件路径问题独立于 VCPM 的空启动许可，需一起修正后再测试通话。

### DMIC3 候选（2026-11-12 14:33）

按 [OnePlus 官方源码](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8450/tree/877203a7cf9b79973d44a9db716490f95d820110/vendor/qcom/proprietary/audio-devicetree) 核对后，候选改用 GPIO8/9、MIC BIAS3（1.8V）、2.4 MHz PDM 时钟，并将 TX DMIC3 连接至 VA DMIC3 的时钟门控 widget。补丁见 [sm8450-oneplus-negroni-dmic.patch](../../config/audio/sm8450-oneplus-negroni-dmic.patch)。主线 TX 宏缺少原厂共享 DMIC 时钟控制，当前借助 DAPM 跨组件依赖做单麦克风实验，独立 VA 低功耗并发尚未验证。

新 `vendor_boot` 与实机备份做绑定感知的设备树比较后，只有四个音频属性发生语义变化；非音频属性、镜像头和其他段均核对。镜像 SHA-256 为 `c46b3d9b3fcef0501457ef755528bdc3007c0c566c9e136fe790e89af785cffb`。原 `vendor_boot_b` 完整备份 192 MiB，SHA-256 为 `9be5ae0f4303392e3608c9ed79bdd1399bdd274c6af007992ad241a1ad1f76ae`，手机与电脑各留一份。经用户明确授权，已写入 B 槽并逐字节核验，14:33:44 重启加载，实机效果待下文补充。

同轮候选还包含已构建的 mixer 断开连接修复，以及恢复 SmartSync、TX 8 kHz、RX Prepare 前先发送 TX channel-info 的本地回环拓扑（SHA-256 `7dd87ffce6392906e0eea78d0cddff93633f3545fdc255c341b3c6b1c71d30a8`）。未加入传输路径尚未验证的 `START_EXCHANGE` 参数；回环配置不代表普通电话配置已经验证。

实机结果：声卡和六个 PCM 正常恢复，GPIO8/9 实际为 DMIC2 时钟/数据功能，分别输出/输入、8 mA、无上下拉。录音期间 VA DMIC3 和 MIC BIAS3 均为 On；VA `0x088=5` 表示启用且四分频（2.4 MHz），`0x094=0` 表示复位已释放。TX 选择器、解静音、48 kHz 和 0 dB 增益寄存器符合预期，但 100 ms 分窗的稳定录音仍为零。只有启动瞬态，未验证真实麦克风信号。

SmartSync 回环的 F3 仍显示 12 次空的 PREPARE/START 许可，语音 SG 保持 STOPPED。随后对照 Diting/Phonewave 补齐 `CAL_KEYS` 的三个 AP key（volume=8、boost=0、BWE=0）；候选 `bd85eef45b5056a26e7e63c77cc6a9eb97df3f02c3e394b6cae2cf84bd3ee917` 经另行获准于 15:04:30 重启加载，F3 证明三项值已送达，启动许可仍为空。可排除“只漏这两项 key”作为唯一阻塞原因。

另发现官方 WCD9385 驱动启用偏置前会设置 `MICB3_TEST_CTL_2` (`0x3072`) bit0，而主线遗漏，实机读值为 0。先用固定目标、固定寄存器、无可写接口的限时诊断模块，在已启用 1.8 V MICBIAS3 时将该位设为 1，20.67 秒后成功恢复为 0，模块已卸载；25 秒声学录音仍无信号。此结果不能排除“需要在偏置启用前设置”的时序要求，不能直接作为永久驱动修正。

随后做预启用对照：在 ADC1 录音保持设备活动时，确认 `0x3025=0x10` 后设置该位，再切至 DMIC3；切换时硬件读值变为 `0x3025=0x00 / 0x3072=0x00`，诊断模块按预设条件中止并核验恢复，没有观测到 `BIAS_ENABLED`。因此这一轮时序试验**无结论**，不能记为该位无效或麦克风供电已验证。另以 DEC1 保持 ADC1/SoundWire 同时采集 DEC0/DMIC3，仍无稳定 DMIC3 信号。

最后一轮同时去掉了测试脚本对旧 mixer 缺陷的顺序规避：保持“先启用 MM2、后关闭 MM5”的原触发顺序，持续播放和双通道录音均退出 0，路由恢复检查通过。由此实机验证了已安装的连接匹配修正，仍不代表声学回路或通话成功。

收尾状态：所有有限时长采集/语音 helper 已退出，临时 MICBIAS 诊断模块均未驻留，桌面 PipeWire/WirePlumber 及原有 socket 已恢复。B 槽 active/successful/bootable 均为 1，ModemManager 与 81voltd 活跃，基带已注册并连接。手机保留实验驱动、DMIC3 设备树和 `bd85…` 回环拓扑；没有自动启用通话音频服务。通话双向声音与真实麦克风采集仍未修复，需对照本机原厂的工作 DSP/校准生命周期以及麦克风供电切换行为继续定位。

### VCPM 内部状态解读（2026-11-12 16:10，仅分析已有日志）

重新阅读 `apkeys-loopback-f3.log` 中未能解出文字的 VCPM 消息，只依据它们的参数（文字含义是推断，未经源码确认）：

- VCPM 为会话维护 4 个语音子图的“主机已请求状态”表：TX 的 `b000003f`/`b00000b1`，RX 的 `b0000040`/`b0000041`。PREPARE 后对应项为 2，START 后为 3，STOP 后为 1。
- 只有 RX 启动时，会话标志（哈希 `4199305301`）为 `0 0`；TX 也启动、四项都为 3 后变为 `1 1`，VCPM 随即向 TX/RX mailbox 模块（`41b0`/`41b1`，tag `0x08001178`/`0x0800117c`）下发配置。主机侧“四个子图都已请求启动”这个条件已经满足，CAL key、通道信息、SmartSync 都不是当前的阻塞点。
- 此后 VCPM 走完固定的两步（哈希 `3462857538` 参数 1、2，再到 `1057654381`）就停住，仍回复空的许可列表。10 秒运行期间没有任何后续 VCPM 动作，TX Codec DMA 持续报告输出缓冲区未提供、数据被丢弃。
- 推断：VCPM 在等主机之外的条件，即声码器客户端（真实通话中是基带语音服务；回环中是 DSP 内部的代理）开始包交换。回环在本机固件上是否能自行启动并不确定：公开的新版 `vcpm_api.h` 为回环另有 `START_EXCHANGE`（`0x08001317`）和 `PARAM_ID_PROXY_VS_CONFIG`（`0x08001366`），本机固件是否支持未知。
- 内核驱动在 TX 首次 START 后会立即 STOP、重发通道信息、再 PREPARE/START；最终状态仍是四项全为 3，未见由此导致的错误。
- **缺口：所有 F3 证据都来自回环，真实 VoLTE 通话从未抓过 F3**；最后一次真实通话测试也早于 SmartSync、通道信息顺序和 CAL key 的修正。回环的停滞不能直接代表真实通话。

下一步是在真实通话中抓 F3。为此已构建普通通话版候选 `OnePlus-10-Pro-sync-call-apkeys-tplg.bin`（SHA-256 `6dde4e4374406501fdb4b1736b5a070e21346f94ab73c1912c9b4d409bc44f0c`，普通 VSID `0x11C05000`、无回环延时、TX 16 kHz，其余与 `bd85…` 相同），**尚未安装**；安装后需要重启。VoLTE 协商的采样率未知，固定 16 kHz 可能不匹配，需由 F3 确认。

### 真实 VoLTE 通话中的 F3（2026-11-12 16:32）

经用户同意，把拓扑换成上面的普通通话版 `6dde4e43…`（只替换根文件系统中的拓扑文件，原 `bd85…` 留在手机 `~/call-audio-test-20261112/topology-replaced-bd85….bin`），16:20 重启；B 槽 active/successful/bootable 均为 1，6 个 PCM 正常。用户接听一通来电，通话 `active` 期间打开语音图 30 秒并抓取 45 秒 F3（68462 条，仅文字）。日志在本地 `logs/call-audio-20261112/vcpm-why/call/call2-*`。第一次尝试因来电铃声仍占用 MM2，测试脚本拒绝运行，未打开语音图。

- **基带语音服务与 VCPM 的通信是通的**：主机打开 RX 图后，基带一侧（GPR 源实例 5）立即映射共享内存，下发时序参考 `0x08001256`（VFR 周期 20000 µs）、编码器/解码器/mailbox 配置，并发出 PREPARE 和 START；通话结束时发出 STOP。此前担心的“基带找不到 ADSP 语音服务”可以排除。
- 本次通话协商的是 **EVS、16 kHz**（`capi_evs_dec`，声码器类别键 `0x0800116a`，采样率键 `0x3e80`），与候选固定的 TX 16 kHz 一致。其他网络或对端下的协商结果未测。
- VCPM 的子图表有两列请求状态，分别对应主机和基带。两列对四个语音子图都到达 3（已请求启动）后，会话状态由 3 变为 5，VCPM 读取两个 mailbox 模块并查询两个硬件端点（`0x6090`、`0x6061`），查询返回状态 0，然后在同一位置停住（哈希 `1057654381`，无参数），许可列表仍为空，语音子图没有启动。
- **真实通话与回环停在完全相同的位置**，所以阻塞点与基带无关，回环可以继续作为等价的复现手段。
- 结论：主机和基带两侧的请求都已齐备，VCPM 在启动前的内部检查中放弃。失败的那条消息解不出文字，具体检查项仍未知；它紧跟在硬件端点查询之后，怀疑与被替换的端点或被删除的设备处理子图有关，这只是推断。
- 本次通话用户是否听到声音未记录；语音子图未启动，预期仍无声。

### VCPM 消息解码与直接原因（2026-11-12 17:00，离线分析）

本机 ADSP 固件剥掉了大部分 F3 文字，但哈希只取决于“文件名 + 格式串”。上游 [linux-firmware](https://gitlab.com/kernel-firmware/linux-firmware) 中若干公开 ADSP 固件（主要是 `qcom/sc8280xp/LENOVO/21BX/qcadsp8280.mbn`、`qcom/qcs6490/radxa/dragon-q6a/adsp.mbn`、`qcom/sa8775p/adsp.mbn`）保留了这些字符串。从中提取 `文件.c:…` 形式的字符串按同一算法求哈希，回环和真实通话两份日志的 797 个哈希对上 793 个，包括全部 VCPM 消息。工具与映射在本地 `logs/call-audio-20261112/vcpm-why/`（`binhash.py`、`dec.py`、`public-fw-matches-partial.json`），下载的固件不纳入 Git。格式串来自别的芯片的固件，与本机固件的源码行不保证逐字相同；这里只采用哈希完全相同的条目。

真实通话日志解码后，停滞点的原文是：

```
vcpm_graph_mgmt_cmd_handler: VSID 0x11c05000, call_state : 0x5, new SG State 0x2, is_modem 0
vcpm_graph_stop_to_prepare_sequencer: current_action[0x2]
VCPM: Defer Prepare operation as complete graph is not yet opened
```

打开图时 VCPM 的统计是 `num_tx_pp_containers 1, num_rx_pp_containers 0`、`num_tx_stream_containers 2, num_rx_stream_containers 1`。四个语音子图在 `apps_state` 和 `modem_state` 两列都到了 3，流子图和 PP 子图的状态检查也都返回 1；唯一缺的是 **RX 方向没有任何后处理（PP）容器**。TX 方向的 PP 容器是恢复 SmartSync 时带回来的 `b00000b1`/`e00000eb`（图位置 3）；RX 方向原厂的 PP 子图 `b0000044` 被整体删除，它的转换器 `41DD` 和增益 `41DA` 被挪进了流容器 `e000004e`（图位置 1）。

“RX 缺 PP 容器导致 VCPM 认为图不完整”是根据计数和这条消息做出的推断，VCPM 源码不公开，尚未经实机验证。

据此构建了新候选，只做一处改动：把 `41DD`、`41DA` 放回原厂的子图 `b0000044` 和容器 `e0000051`（SC 容器、图位置 3），不恢复任何厂商模块，也不注册 `b0000044` 的原校准表；连接关系和 RX 校准数据逐项断言未变。

| 候选 | SHA-256 | 状态 |
| --- | --- | --- |
| `OnePlus-10-Pro-sync-call-rxpp-tplg.bin`（普通通话） | `23bcdd6dfdfd6946f73637c8dc6565fe6769ca25f1ee3cdd2b09baddc9bec7b9` | 已安装并实测，见下文 |
| `OnePlus-10-Pro-sync-loopback-rxpp-tplg.bin`（回环） | `2b4e0b6e803504736db324ec5620bb64681f3840fbb979561bec0e55c92b5ff0` | 已构建，未安装 |

这一修正连同 SmartSync 子图、RX 侧提前发送通道信息和回环 8 kHz 已并入仓库的 [voice-topology.py](../../config/audio/voice/voice-topology.py)（`restore_pp_containers()`）。用 `scripts/build-voice-topology.sh` 从仓库生成的普通通话版和回环版拓扑，与上表两份已构建的候选逐字节相同。内核侧改动仍只以补丁形式保存在 `config/audio/`，尚未在 `linux/` 中提交，也未更新 gitlink 和 bundle。安装仍需重启；VCPM 放行后才会真正运行 SmartSync、编解码器和 `-24.08 dB` 增益这些此前从未执行过的路径，首次测试应保持低音量。

### RX 后处理容器候选的实机结果（2026-11-12 17:19）

经用户同意安装 `OnePlus-10-Pro-sync-call-rxpp-tplg.bin`（`23bcdd6d…`，上一版 `6dde4e43…` 留在手机 `~/call-audio-test-20261112/topology-replaced-6dde….bin`），17:00 重启，B 槽标记正常。用户接听一通来电，通话 `active` 期间语音图打开 40 秒，F3 抓取 58 秒共 369829 条（上一版同类抓取为 68462 条），日志在本地 `vcpm-why/call/call3-*`。

- 打开图时 VCPM 统计变为 `num_tx_pp_containers 1, num_rx_pp_containers 1`，不再出现 “Defer Prepare … complete graph is not yet opened”。
- `vcpm_graph_stop_to_prepare_sequencer` 走完动作 1、2、3、5、9、0xf，`call_state` 由 5 到 6、0xb，最后停在 0xc，并保持到主机关闭语音图为止。
- 运行期间约有 1960 个 20 ms 帧的基带交互；EVS 解码器处理了约 2000 个下行包，其中 287 个为 61 字节的语音帧，其余为 6 字节 SID 或 1 字节无数据帧；TX 侧 SmartSync 和转换器 `4446` 持续处理数据。
- 用户反馈“好像听到一个声音”。这与日志一致，但只是一次主观反馈：下行音量与清晰度、对方能否听到本机、听筒/免提、回声都没有确认。麦克风路径的问题（DMIC3 稳定录音为零）没有改动。
- 由此确认：此前的阻塞点是 RX 方向缺少后处理容器。结论适用于本机这版 ADSP 固件和这一通 EVS/16 kHz 通话，其他声码器与采样率未测。
- 运行中出现两条 `Sending incoming intent set param to module 0x41b0/0x41b1 failed result 4` 和 9 条 `evs_dec_find_operating_mode: received unsupported bandwidth(-1)`，影响未评估。
- 语音图仍由手动测试脚本限时打开，没有自动通话服务；测试候选未接入镜像构建。

### 通话自动开关语音图（2026-11-12 18:58，实验）

[negroni-call-audio.py](../../config/audio/voice/negroni-call-audio.py) 监听 ModemManager 的 D-Bus 信号并用 `mmcli` 读取通话状态：有通话处于 `ringing-out` 或 `active` 时打开 MM5/MM6 语音图，没有时关闭并恢复全部改动的 mixer 值；`ringing-in`、`dialing`、`held` 不打开。打开前最多等 8 秒让其他声音客户端（来电铃声）释放声卡，打开失败会清理后 2 秒重试。它复用 `negroni-voice-test.py` 的 PCM 与 mixer 代码，必须与之放在同一目录，以 root 运行；不拨号、不接听、不挂断、不录音。单元文件为 [negroni-call-audio.service](../../config/audio/voice/negroni-call-audio.service)，假定安装在 `/usr/local/libexec/negroni-voice/`。主机侧 7 项测试见 `tests/test-call-audio.py`。

实机验证（经用户授权由代理拨打用户提供的号码，服务以 `systemd-run` 临时单元运行）：

- 18:58:33 `dialing`，18:58:37 `ringing-out` 时语音图打开，18:58:47 `active`，18:59:19 通话结束时语音图关闭，6 个 PCM 回到 `closed`，内核无 APM/ASoC 报错。
- F3 共 390437 条：RX 后处理容器计数为 1，VCPM 运行到 `call_state 0xc` 并保持到基带在通话结束时发 STOP；EVS 解码器处理 1101 个 61 字节语音帧、147 个 SID 帧、868 个无数据帧；上行编码器为 AMR-WB。
- 这次没有人耳反馈：下行是否可闻、音量是否合适、对方能否听到本机均未确认。
- 当时服务以临时单元运行，测试结束后已停止。

常驻安装（2026-11-12 19:05，经用户同意）：脚本与 `negroni-voice-test.py` 装到手机 `/usr/local/libexec/negroni-voice/`，单元装到 `/etc/systemd/system/` 并 `enable`。停用方法：`sudo systemctl disable --now negroni-call-audio.service`。尚未接入镜像构建。

- 19:06 第一次用常驻服务拨出：语音图在 `ringing-out` 打开、挂断后关闭。但通话期间桌面播放了一个提示音并尝试打开 MM3 录音：内核报 `Failed to open graph 2: -22`，PipeWire 的 MM2 扬声器流停在 `RUNNING`、`hw_ptr` 不前进，通话结束后仍卡住，麦克风输入也从 PipeWire 中消失。手动把声卡 profile 切到 `off` 再切回后恢复。
- 修正：服务在打开语音图前，对每个带 `pulse/native` 套接字的登录用户执行 `pactl set-card-profile <本声卡> off`，记下原 profile（写入 `/run/negroni-call-audio.json`，服务异常退出后下次启动时据此还原），关闭语音图后切回。通话期间桌面的提示音因此不会到达扬声器。主机测试增至 12 项。
- 19:12 用修正后的服务再次拨出：`desktop sound released` → `voice graphs open`（19:12:40）→ 挂断 → `voice graphs closed` → `desktop sound restored`（19:13:14）；内核无 APM/ASoC 报错，6 个 PCM 回到 `closed`，PipeWire 的两个输出和 Mic1 输入都在。
- 已知问题：关闭时报告 `restore TX_AIF1_CAP Mixer DEC0 … to off: readback differs`。不打电话也能复现：profile 为 `off` 时运行 `negroni-voice-test.py`，结束后该控件停在 `on`，再手动 `cset off` 也无效，原因未查（疑为 TX 宏驱动对该控件的处理）。切回 profile 后 UCM 本来也会把它设为 `on`，所以通话后的最终状态与通话前一致；但 profile 保持 `off` 时该控件会残留为 `on`。
- 这两通电话同样没有人耳反馈。未测：来电场景下与铃声的衔接、通话保持/多方、蓝牙或耳机通话、重启后服务自启动、非 PipeWire-pulse 的声音客户端。

### 通话录音与上行放音的图（2026-11-12，仅离线分析）

目标场景：自动接听、录下对方的声音，并向对方播放固定音频。这个场景不需要麦克风和扬声器。在本机 ACDB 中找到了对应的图，离线提取并解码。键名已用官方 [audioreach-conf `qcom/kvh2xml.h`](https://github.com/AudioReach/audioreach-conf/blob/master/qcom/kvh2xml.h)（BSD-3-Clause）核对；模块名来自 audioreach-graphservices 的 SPF 头文件。查询脚本、自写的 tag 查询工具 `acdb-tags` 和输出保存在本地 `logs/call-audio-20261112/acdb/incall/`。

| 图键（官方名） | 子图 | 结构 |
| --- | --- | --- |
| `StreamRX=INCALL_MUSIC`（`a1000000=a1000013`） | `b00000d6` | WR_SHARED_MEM_EP → DATA_LOGGING → PCM 转换/解码 → VOL_CTRL → SOFT_PAUSE → MFC → 分路器 `0x42f2`（SPLITTER）；端口 3 接 TX 语音流的 MFC `0x458b` |
| `StreamTX=INCALL_RECORD`（`b1000000=b100000c`） | `b00000d0` | 从 `0x4561` 端口 3（下行）和 `0x4560` 端口 3（上行）抽取，各经 MFC 转为 48 kHz/S16/单声道 → MUX_DEMUX `0x4207` → RATE_ADAPTED_TIMER → PCM 编码 → RD_SHARED_MEM_EP |
| `INCALL_RECORD` + `ProxyTxType=PROXY_TX_VOICE_RX`（`d1000000=d1000003`） | `b000008d` | 结构同上，改用两个分路器的端口 5；具体用途未确认，普通通话录音应使用上一行 |

录音方向由 MUX_DEMUX 上的 tag `stream_muxdemux`（`0xC0000027`）、键 `Stream_MuxDemux`（`0xBD000000`）选择。从 ACDB 读出的 tag 数据（`PARAM_ID_MUX_DEMUX_CONFIG` / `OUT_FORMAT`）如下：

| 值 | 官方名 | 连接 | 输出 |
| --- | --- | --- | --- |
| 1 | UL_Mono | 输入端口 2（上行，来自 `0x4560`）→ 通道 0 | 单声道 |
| 2 | DL_Mono | 输入端口 4（下行，来自 `0x4561`）→ 通道 0 | 单声道，**只有对方的声音** |
| 3 | UL_DL_Mono | 上行 → 通道 0，下行 → 通道 1 | 双声道 L/R（本机 ACDB 中与值 4 相同，不是混成单声道） |
| 4 | UL_DL_Stereo | 同上 | 双声道 L/R |

上行放音图带 `stream_pause`（`0xC0000006`，SOFT_PAUSE 的暂停/恢复）和 `stream_mute`（`0xC0000007`，VOL_CTRL 的静音）两个 tag。

- 抽头位置已包含在现有候选拓扑中：RX 语音流的分路器 `0x4561`（SG `b0000041`）和 TX 语音流的分路器 `0x4560`（SG `b000003f`）在 ACDB 中都有 3 个输出端口，端口 3/5 预留给录音图。当前 `voice.conf` 已声明 `MAX_OP_PORTS 3`。
- 上行放音的混入点：`0x458b` → EC_SYNC `0x458c`（`0x07001028`）的端口 4，与麦克风路径（`0x455e` → 端口 2）合并后经 `0x458d` → `0x455f` → `0x4560`。所以上行录音（UL）抽头位于混音点之后，会录到注入的音频。值 4 可以把对方的声音（R）和自己播放的音频（L）分开保存。
- 上行放音图另有一路 8 kHz/单声道，经 MFC `0x42f1` 接到模块 `0x07001044`，用途未知。
- 实现所需：新增两个由主机传数据的 PCM（一个录音、一个放音，使用共享内存端点，与 MM1–MM4 相同），并让内核支持跨图的**数据**连接。现有补丁只做了跨图控制连接；APM 是否接受指向已打开语音子图的跨图数据连接，尚未验证。
- 前置条件：语音子图必须真正运行。17:19 的实测中 VCPM 已放行并运行语音子图，这个前置条件在该次通话中已满足。
- 以上为离线分析时的记录；实现与实机结果见下一节。

### 通话录音与上行放音的实现与实机结果（2026-11-12 20:46）

不需要改内核。[incall-topology.py](../../config/audio/voice/incall-topology.py) 从上面两张原厂图生成两个带主机数据的前端，`scripts/build-voice-topology.sh` 在设置 `INCALL_MUSIC_DIR`、`INCALL_RECORD_DIR`、`INCALL_MUX_CONFIG` 三个环境变量时把它们并入拓扑；不设置时输出仍是 `23bcdd6d…`。

| PCM | 方向 | 图 |
| --- | --- | --- |
| `MultiMedia7 InCall`（hw:0,6） | 播放 | 主机写入端点 `458e` → PCM 解码 `4590` → PCM 转换 `4591` → MFC `4596` → 通话 TX 流的 MFC `458b` 端口 2。原厂的音量、软暂停、分路器和 `42f0` 支路没有保留 |
| `MultiMedia8 InCall`（hw:0,7） | 录音 | 原厂录音图 `b00000d0` 原样保留，抽头为 `4561`（下行）与 `4560`（上行，位于放音混入点之后）的端口 3 |

实现要点（均由实机失败后查内核代码或 F3 得出）：

- 内核只在图内建立数据连接。起点在本图内的跨图连接（`4596 → 458b`）用普通的目的模块标记即可，内核不检查目的模块是否在本图；起点在通话图内的两条抽头连接和 `4654 ↔ 41b0` 控制连接作为原始 `CFG_GRAPH_OPEN` 参数下发。DSP 在通话进行中接受了这些连接。
- 两个前端没有自己的硬件端点。为满足 DPCM，各加一条不带控件的 DAPM 路由，挂到通话已在使用的后端（`device20.logger1`、`device120.logger1`）；两端都是模块部件时内核不会在 DSP 侧建立连接。
- PCM 解码器、编码器、转换器必须用 `decoder`/`encoder`/`src` 部件类型并带 `AR_TKN_U32_MODULE_FMT_INTERLEAVE`，否则内核发出的 PCM 格式里交错方式为 0，模块以 `0x08001008` 失败拒绝。
- 录音图的速率适配定时器 `4654` 在 ACDB 中没有媒体格式（安卓由 PAL 在运行时设置），不设置时 START 失败；生成器按 MUX_DEMUX 的输出格式补上 `PARAM_ID_RAT_MEDIA_FORMAT`（`0x080010D0`）。
- 每个模块的原厂设置单独成一个 `CFG_SET` 数组，使其在内核对该模块的默认格式之后下发。

实机经过（用户同意按需重启；每轮由代理拨打用户提供的号码）：前三版分别因 PCM 格式被拒（两次）和定时器未配置而失败，第四版拓扑 SHA-256 `5fb6fba602ed054da1319f06104c374289f9d38ab8955220bd8d7312f64e15a3` 通过。

第四版结果（通话 `active` 后 3 秒开始录 16 秒，再过 3 秒向 MM7 播放 8 秒 1 kHz、幅度 8000 的测试音；MUX 模式 4，左声道上行、右声道下行）：

- 录音文件 16.00 秒、48 kHz 双声道，`arecord` 和 `aplay` 均退出 0，通话期间内核无 APM/ASoC 报错。
- 左声道（上行）：第 3–10 秒 1 kHz 分量幅度约 7999，其余时间样本全为 0。说明注入的声音到达了上行流的抽头，同时也再次确认**麦克风对上行没有任何贡献**。
- 右声道（下行）：第 1–2 秒和第 5–9 秒有 RMS 约 450–1660、峰值到 17513 的信号，其余时间接近 0，与对端断续有声音一致。内容没有人工听过。
- 对端人耳确认（用户在被叫手机上听）：听到蜂鸣声，干净、无失真，音量略偏大。测试音幅度为 8000（约 -12 dBFS），原厂放音图中的音量级没有保留，播放真实音频时应由文件本身控制电平。只确认了这一种信号，语音内容的可懂度未测。

已知问题与未测：

- 桌面声音服务会探测这两个 PCM。通话之外它们打不开（依赖通话图中的模块），内核会记录打开或配置失败；第三版起启动时的格式报错为 0，但切换声卡 profile 时仍会出现 `0x8001007 rejected` 或 `Failed to Start Graph`。
- 必须在通话语音图运行期间打开，并先于语音图关闭。`negroni-call-audio` 目前不管理这两个 PCM；语音图先关闭时 DSP 的行为未测。
- 录音周期需不小于 6144 字节且为 480 帧的整数倍，测试用 1920 帧周期、7680 帧缓冲。
- 未测：其他 MUX 模式、单声道或其他采样率、长时间录音、原厂放音图中被去掉的音量与软暂停、通话保持、来电场景。
- 手机当前安装的拓扑即第四版；尚未接入镜像构建。

### 同时调试时的落盘问题

安装过程中其他会话多次强制复位，曾使新写的模块、拓扑和刚建立的备份同时成为零字节。已从 WSL `linux/output/out-modules` 找回与安装前 SHA-256 完全相同的三个原模块，原拓扑与仓库版本一致；本地 `recovered-original/` 与手机 `original/` 的备份已重新校验。安装器改为临时文件写入、`sync -f`、内容比较、原子重命名，再同步文件系统。后续测试需协调其他会话，避免写入或验证时强制复位。
