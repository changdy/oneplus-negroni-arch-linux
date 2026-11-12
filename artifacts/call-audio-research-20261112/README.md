# OnePlus Negroni 通话音频研究依据（2026-11-12）

本记录整理源码与实机诊断结论，不包含原始 DIAG 日志、录音、ACDB 校准数据或分区镜像。**当前尚未证明通话双向音频可用。** 候选标识部分保留部署时的未测快照；后续实机诊断结果另列于文末，其中最后一节记录了阻塞原因与修正。最新硬件测试与收尾状态见[通话音频记录](../../docs/call-audio.md)。

## 源码版本与 F3 解码方法

| 来源 | 固定版本与用途 |
| --- | --- |
| [AudioReach engine](https://github.com/AudioReach/audioreach-engine/tree/5562c141d04d0e2c7dffe0432daff4c9bfb52445) | `5562c141d04d0e2c7dffe0432daff4c9bfb52445`，APM proxy、容器、SmartSync 与 VCPM API；源码保留 BSD-3-Clause 声明 |
| [Diting Ubuntu](https://github.com/royka1/diting-ubuntu/tree/c68ff47db94792fb5fd608e98d1ae489c2e592b1) | `c68ff47db94792fb5fd608e98d1ae489c2e592b1`，hostless/VCPM 补丁 0046、0049、0050 与诊断工具参考 |
| [AudioReach graphservices](https://github.com/AudioReach/audioreach-graphservices/tree/e0ecb6a1f10b9a0fced2de8101160e160ad02e5d) | `e0ecb6a1f10b9a0fced2de8101160e160ad02e5d`，查询本机原厂 ACDB；本目录不分发查询输入或校准负载 |
| [OnePlus 官方下游](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8450/tree/877203a7cf9b79973d44a9db716490f95d820110) | `877203a7cf9b79973d44a9db716490f95d820110`，分支 `oneplus/sm8450_v_15.0.0_oneplus_10_pro`，麦克风供电、引脚与时钟依据 |

采集器由 Diting 工具裁减而来，仅输出 F3 消息，主动关闭二进制音频日志与 event 日志，最长运行 60 秒并清理退出；不重启 ADSP/调制解调器。采集器源码 SHA256 为 `9a2416400a39459f550cc5cd71e53b7f7e1b51521560910f31c0e4042ba79b55`，AArch64 二进制为 `9aa1c9b0cb061c3cece53da23e232ea06916ce6ad31f66f2a058c59f15297e06`。

目标固件的 opcode `0x92` 消息携带 QShrink 哈希。算法依据 Qualcomm 脚本镜像中 [QShrinkElf.py 的 `toHash` / `unAlignHash`](https://github.com/arzekrasr/MPSS.HA.1.1/blob/06e735b4036be9280985accc611ba052a7be77e0/modem_proc/perf/scripts/qshrink/QShrinkElf.py)：

1. 展开 C 相邻字符串、`AR_MSG` 的 ` ADSP: ` 前缀以及 `CU_MSG`、`TOPO_MSG` 等框架前缀。
2. 对 `源文件basename + ": ADSP: " + 完整格式字符串` 计算 MD5。
3. 将 MD5 最后四字节按大端解释为 uint32；若低两位均为零，加一。
4. 与日志中的完整 32 位哈希匹配，再代入消息参数；部分旧文件名需去掉当前源码的 `_vcpm` 后缀。

在两份本地 F3 记录的 737 个不同哈希中，公开源码匹配到 285 个；未匹配的消息没有猜译。行号只用于定位，不参与匹配。`%s` 指针不能恢复字符串。公开 VCPM 实现仅有 stub，因此能够确认 APM 许可与状态，却无法从这些源码确定 VCPM 内部拒绝启动的具体条件。

## 已观测到的启动阻塞

以下行号均对应本地忽略目录中的完整 `loopback-f3.log`，没有把原始日志收入 Git。

| 证据 | 观察结果 |
| --- | --- |
| 哈希 `67104325` | 解码为 `PROXY GRAPH MGMT RSP: Permitted proxy sg list is empty ...`；RX/TX 共 12 次 PREPARE/START 响应均为许可列表为空、status 0。例：3090、3233、5197、5246 行 |
| 哈希 `3896013721` | 语音 SG `B000003F/40/41` 只在 GRAPH_OPEN 后变为 state 1，即 `APM_SG_STATE_STOPPED`；整个采集窗口没有进入 PREPARED/STARTED。定位：712、1345、1346 行 |
| 同一状态消息 | 非语音 renderer SG `B0000045` 与硬件 SG `4006/4009` 分别在 4047、4251、5805 行进入 state 4（STARTED） |
| VSID 与参数 | 初始默认 VSID 在 2091 行配置为回环 `12006000`；TX channel-info `08001310` 到 4711 行才发送，晚于首次 RX Prepare |
| 回环采样率 | AMR decoder 与 VCPM rate key `08001165=0x1f40` 表明回环选择 8 kHz；旧注入 TX MFC 固定为 16 kHz |

这说明 ALSA 显示 `RUNNING`、APM 返回成功，都不足以证明语音子图真正启动。空许可行为可直接对照 [APM proxy 响应处理器](https://github.com/AudioReach/audioreach-engine/blob/5562c141d04d0e2c7dffe0432daff4c9bfb52445/fwk/spf/apm/ext/proxy/proxy_vcpm/src/apm_proxy_vcpm_cmd_rsp_handler.c)。公开 [TX channel-info API](https://github.com/AudioReach/audioreach-engine/blob/5562c141d04d0e2c7dffe0432daff4c9bfb52445/fwk/api/vcpm/vcpm_api.h#L1143) 要求在有效 VSID 配置后、voice Prepare 前设置该信息。

`VCPM_PARAM_ID_VOC_PKT_LOOPBACK_START_EXCHANGE` (`08001317`) 没有加入新候选：虽然头文件声明了其 VSID 负载，[APM 分发器](https://github.com/AudioReach/audioreach-engine/blob/5562c141d04d0e2c7dffe0432daff4c9bfb52445/fwk/spf/apm/ext/proxy/proxy_vcpm/src/apm_proxy_vcpm_utils.c#L458) 没有对应分支，未知参数返回错误。当前驱动 CFG_SET_LATE 发往 APM GPR port 1，负载中的 IID 4 不等同于直接发送至 VCPM port 4。

## 独立的 mixer 断连缺陷

普通播放诊断暴露了另一问题：先开启 MM2 speaker route，再关闭原本不活跃的 MM5 route，旧 `audioreach_connect_sub_graphs()` 会无条件清空 backend 的唯一连接记录。对应 F3 中存在 FE 链和 `6060 -> 6061`，缺少应有的 `6015 -> 6060`；这次 I/O 失败不能据此归因于共享 container。

修复只在被关闭 route 的源、目标 module ID 均匹配当前连接时清空记录，并把查找与更新保持在同一锁内，见 [仓库补丁](../../config/audio/sm8450-audioreach-voice.patch)。诊断脚本同时改为先关其他 route，最后开启目标 route。实际 C helper 的 11 项顺序/隔离检查通过 ASan/UBSan；这是本地验证，不替代新内核的实机播放验证。

## 原厂 DMIC3 路径、供电与时钟

本机只读提取的 ODM `mixer_paths.xml` 中，`handset-mic` 与 `speaker-mic` 均选择 `MSM_DMIC`，DEC0 接 DMIC3、DEC1 接 DMIC4，开启对应 TX_AIF1 capture mixer，DEC0/1 音量 84 为 0 dB。该文件 SHA256 为 `93c04a6809ab673f7838009cfbc0b50a7bc59f9a5a4a8798b86bcfd94b7ab8ad`。这是本机路由依据，不是对 ADC1/SWR_MIC0 声学可用性的验证。

| 项目 | 官方源码依据与含义 |
| --- | --- |
| DMIC3 bias | [OnePlus common overlay](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8450/blob/877203a7cf9b79973d44a9db716490f95d820110/vendor/qcom/proprietary/audio-devicetree/oplus/waipio_audio_overlay_common.dtsi#L52) 将 TX DMIC3 接 MIC BIAS3；VA DMIC3 对应 VA MIC BIAS3。[codec 配置](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8450/blob/877203a7cf9b79973d44a9db716490f95d820110/vendor/qcom/proprietary/audio-devicetree/waipio-audio-overlay.dtsi#L334) 设置 bias3 为 1800 mV |
| 引脚 | [LPASS pinctrl](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8450/blob/877203a7cf9b79973d44a9db716490f95d820110/vendor/qcom/proprietary/audio-devicetree/waipio-lpi.dtsi#L1992)：DMIC2/3 时钟用 gpio8/function1，数据用 gpio9/function1；分别输出与输入使能 |
| TX rate | [TX 配置](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8450/blob/877203a7cf9b79973d44a9db716490f95d820110/vendor/qcom/proprietary/audio-devicetree/waipio-audio-overlay.dtsi#L118) 为 2.4 MHz，VA 低功耗默认为 600 kHz；TX MCLK 9.6 MHz 对应四分频 |
| 时钟门控 | [TX DAPM callback](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8450/blob/877203a7cf9b79973d44a9db716490f95d820110/vendor/qcom/opensource/audio-kernel/asoc/codecs/lpass-cdc/lpass-cdc-tx-macro.c#L884) 调用共享 DMIC clock helper；[该 helper](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8450/blob/877203a7cf9b79973d44a9db716490f95d820110/vendor/qcom/opensource/audio-kernel/asoc/codecs/lpass-cdc/lpass-cdc.c#L483) 将 DMIC2/3 映射到 `VA_TOP_CSR_DMIC1_CTL`，维护成对引用计数，选择 TX/VA divider 并设置 enable |

因此只切换 mixer 到 DMIC3 仍不足以保证实际采集。此次 [DT 实验补丁](../../config/audio/sm8450-oneplus-negroni-dmic.patch) 启用 `dmic23_default`，将 DMIC3 bias 修正为 BIAS3，并以 `TX DMIC3 -> VA DMIC3` DAPM 依赖触发 VA 寄存器门控，将 VA DMIC rate 暂设为 2.4 MHz。它是单一 TX 路径的诊断方案；独立 TX/VA 并发的完整时钟仲裁仍未实现，DMIC4 的项目差异也未在本次推断。

## 本次待测候选标识

截至 2026-11-12 14:33:44 的部署/重启节点，以下组合的麦克风、回环和通话效果均 **NOT YET TESTED（未测）**。

| 产物 | SHA256 |
| --- | --- |
| SmartSync 回环 topology，45,944 字节 | `7dd87ffce6392906e0eea78d0cddff93633f3545fdc255c341b3c6b1c71d30a8` |
| DMIC3 DTB | `27889694ce1a52f054dc6e4fee74c71ba60564d7bd545103094612625809ac2f` |
| 包含上述 DTB 的测试 vendor_boot 镜像 | `c46b3d9b3fcef0501457ef755528bdc3007c0c566c9e136fe790e89af785cffb` |

Topology 恢复原始 B1 SG、SC container 与 SmartSync `4449` 标签，连接 `4446:1 -> 4449:2`、`4449:1 -> 47B8:2`；回环的两个 TX MFC 均设为 8 kHz，TX channel-info 提前到 RX VSID 后，保留 RX -24 dB 增益。编译后的配置数组与预期字节完全匹配。

仍有两项未确定：仅连接 SmartSync 主端口可能让其保持 SYNCING；B1 未注册含已删除专有模块的原始 persistent calibration table，VCPM 是否要求该 SG 的校准注册尚无公开实现可核实。因此该候选的成功必须由新 F3 中的 voice SG PREPARED/STARTED 转移及实际声学测试共同确认。

## 后续实机记录：SmartSync 候选仍未获得启动许可

上述重启后进行了约 10 秒 helper 回环尝试，并采集有限时长 F3（本地 `sync-loopback-f3.log`）。实际 TX channel-info 已在 2272 行到达，紧随 VSID，早于 RX Prepare；SmartSync 在 426 行完成初始化。普通静态 property 8/9 不支持的消息出现在成功初始化之前，不能单独认定为致命错误。

RX/TX 仍有 12 次 PREPARE/START 返回空许可、status 0；语音 SG `3F/B1/40/41` 全程只处于 STOPPED，renderer 与硬件 SG 则能 START。SmartSync 主端口被打开，却没有观测到 port-start、voice-timing 或 timer-subscribe；416/459 行提示 event client 尚未注册。26782–26783、27787–27789 行虽出现正向许可，命令是 GRAPH_CLOSE，不能当作启动成功。

6061 在 4453 行报告 underrun 且 `media_format_set=0`，与语音链路未启动一致。27803/27820 行的 GPR rc10 出现在关闭阶段，目标为回环 VSID `12006000`，不足以解释启动阻塞。加入本次记录后，公开源码可匹配 337/832 个不同哈希。结论是：恢复 B1 SmartSync、修正 channel-info 顺序及回环 8 kHz，仍未解决 VCPM 启动条件；公开源码没有给出其内部拒绝许可的具体原因。

## 后续实机记录：补齐 AP calibration keys 仍未启动

单独补齐 AP keys 的 topology SHA256 为 `bd85eef45b5056a26e7e63c77cc6a9eb97df3f02c3e394b6cae2cf84bd3ee917`，45,960 字节。相较上一候选仅将 CAL_KEYS 从 volume 一项改为 volume=8、VOL_BOOST=0、BWE=0 三项，其余七组编译配置数组逐字节一致。这与 [Phonewave 的三键请求](https://github.com/denialwm/phonewave/blob/661450045b3804b30f561134ccfd9daf202add7e/services/audio/voicegen/voicegen.c#L148) 对齐，没有提高 boost。

该候选实机运行 helper 10 秒，25 秒 F3 采集得到 28,074 条消息，退出时确认关闭 F3 mask 并撤销服务。`apkeys-loopback-f3.log` 第 2969 行的 CAL_KEYS 请求为 48 字节；2991–2994 行显示 count=3 及三个 key/value，3887–3889 行再次出现，确认补充项实际送达。

结果仍是 12 次 PREPARE/START 空许可，`3F/B1/40/41` 保持 STOPPED；SmartSync 初始化成功但没有启动或定时器订阅。正向许可仍只发生于 GRAPH_CLOSE。helper 结束后 PCM 关闭，修改的 mixer 值恢复并验证。**缺少两个 AP key 不是本次阻塞的唯一原因。** B1 校准注册、完整 device-PP 依赖与跨 RX/TX 校准生命周期仍待同机原厂/GSL 序列证据核实；没有据此认定某一项必然需要修改。

## 后续实机记录：阻塞原因与修正（2026-11-12 晚）

公开源码只能匹配部分哈希，VCPM 自身的消息一条也解不出。改用上游 [linux-firmware](https://gitlab.com/kernel-firmware/linux-firmware) 中保留了格式串的公开 ADSP 固件（`qcom/sc8280xp/LENOVO/21BX/qcadsp8280.mbn`、`qcom/qcs6490/radxa/dragon-q6a/adsp.mbn`、`qcom/sa8775p/adsp.mbn` 等）：提取 `文件名.c:格式串` 形式的字符串按同一算法求哈希，回环与真实通话两份记录的 797 个哈希匹配到 793 个。只采用哈希完全相同的条目；这些格式串来自其他芯片的固件，与本机固件的源码行不保证逐字相同。固件文件不收入 Git。

解码后的阻塞点是 `VCPM: Defer Prepare operation as complete graph is not yet opened`，同时 `vcpm_process_proxy_graph_info_cmd` 报告 `num_tx_pp_containers 1, num_rx_pp_containers 0`。主机（`apps_state`）与基带（`modem_state`）对四个语音子图的请求状态都已到 3；真实 VoLTE 通话与回环停在同一位置。原厂 RX 后处理子图 `B0000044` 被整体删除，RX 方向没有后处理容器。

修正只把转换器 `41DD` 与增益 `41DA` 放回原厂子图 `B0000044` 和容器 `E0000051`（图位置 3），不恢复厂商模块与该子图的校准表。普通通话版 topology SHA256 为 `23bcdd6dfdfd6946f73637c8dc6565fe6769ca25f1ee3cdd2b09baddc9bec7b9`，回环版为 `2b4e0b6e803504736db324ec5620bb64681f3840fbb979561bec0e55c92b5ff0`；仓库生成器的输出与二者逐字节相同。

实机结果：RX 后处理容器计数变为 1，`vcpm_graph_stop_to_prepare_sequencer` 走完，`call_state` 到达并保持 `0xc`，EVS 解码器在三通电话中处理了下行语音帧；一通来电中用户反馈“好像听到一个声音”。下行质量、上行（麦克风）、其他声码器与采样率仍未验证，**尚不能称通话双向音频可用**。完整过程见[通话音频记录](../../docs/call-audio.md)。


之后在同一天内又验证了通话录音与向对方放音（不改内核，只改拓扑）：录音的下行声道有对端的声音，注入的 1 kHz 测试音以接近满幅出现在上行声道，用户在被叫手机上确认听到该测试音且干净无失真。内置麦克风仍无信号，上行不可用。
