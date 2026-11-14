# 原厂 DMIC3/DMIC4 与共享时钟对照（2026-11-13—14）

本轮在 NE2210、`7.3.0-sm8450+` 上通过 USB SSH 完成静态对照与限时录音。**麦克风仍不可用**。补齐 DMIC4 的引脚、偏置依赖、VA 门控，并让 `VA_MCLK` 进入 On 后，稳定录音依然全零；不能把共享函数的缺失直接认定为全部根因。

首轮限时对照没有刷分区或重启；后续已按本对话授权部署 VA/DMIC4 设备树、更新 TX/VA 模块与 UCM，并重启验证，结果见文末。没有切槽、重绑声卡/APM或新增 q6prm 时钟申请。原厂 Android 模块只做离线反汇编，没有加载到主线内核。

## 原厂实物依据

- `downloads/stock-drivers-20261113/vendor_dlkm_b/lib/modules/` 中的 `lpass_cdc_dlkm.ko`、`lpass_cdc_tx_macro_dlkm.ko`、`lpass_cdc_va_macro_dlkm.ko`。来源与版本边界见[原厂模块归档](../../downloads/stock-drivers-20261113/README.md)。
- 本机 ODM `mixer_paths.xml`：`handset-mic`、`speaker-mic` 均为 DEC0=`MSM_DMIC/DMIC3`、DEC1=`MSM_DMIC/DMIC4`，打开 TX_AIF1 的 DEC0/1，两个 `TX_DEC* Volume` 均为 84（0 dB）。
- `dtbo_a` 中项目列表包含 20846 的量产候选 **0 和 11**：以下路由相同；没有在本轮确定 bootloader 最终选择哪一个。A 槽 DTBO 与 B 槽模块没有证明属于同一次更新。

| 通道 | 引脚 / 主线功能名 | 原厂偏置依赖 | 共享门控 |
| --- | --- | --- | --- |
| DMIC3（DMIC2/3 共线） | GPIO8/9，`dmic2_clk` / `dmic2_data`，func1 | **MIC BIAS3** | VA `0x088`（DMIC1_CTL） |
| DMIC4（DMIC4/5 共线） | GPIO12/13，`dmic3_clk` / `dmic3_data`，func1 | **MIC BIAS1** | VA `0x08c`（DMIC2_CTL） |

注意：DMIC 通道号、引脚功能名和门控寄存器编号采用不同的编号方式。旧文档中“DMIC4 用 MIC BIAS4”应更正为本机两份量产候选均使用 MIC BIAS1。DT 依赖是供电配置依据，尚未测量物理偏置电压。

原厂 TX 的 DMIC rate 是 2.4 MHz，VA 是 600 kHz。当前诊断使用 VA 分频来服务 TX，临时把 VA 也设成 2.4 MHz；这不是完整的 TX/VA 并发仲裁实现。

## 找到的函数和实际行为

`aarch64-linux-gnu-readelf -Ws` / `objdump -dr` 确认，原厂 `lpass_cdc_dlkm.ko` 导出 **`lpass_cdc_dmic_clk_enable`**，`.text` 地址 `0x237c`、长度 **788 字节**。TX 和 VA 两个模块都引用它；其 `*_macro_enable_dec` 中分别传入 `tx_mode=0` / `1`，在上电/下电时传 `enable=1` / `0`。

反汇编和已下载的 [OnePlus 官方下游源码](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8450/tree/877203a7cf9b79973d44a9db716490f95d820110/vendor/qcom/opensource/audio-kernel/asoc/codecs/lpass-cdc) 中以下逻辑一致；这只证明相关逻辑吻合，不声称整个模块来自同一源码提交：

1. DMIC0/1、2/3、4/5、6/7 分成四组，各组保存共享引用计数和当前分频。
2. 从 TX 或 VA 的 `clk_div_get` 回调获取该使用者的分频。首个使用者清除 VA DMIC_CFG（逻辑 `0x3094`、物理偏移 `0x094`）的 reset bit `0x80`，写对应 CTL 的 divider mask `0x0e`，再置 enable bit `0x01`。
3. 同组加入更高频率的使用者时，围绕分频修改置位、清除 DMIC_CFG 中的组频率切换位；最后一个使用者退出时清 enable 并清 divider。不同需求的关闭处理仍依赖原厂回调及引用计数，不能用单一固定分频替代完整仲裁。
4. 原厂 `.rodata` 的寄存器表实际为 `0x3084/0x3088/0x308c/0x3090`，每项重复两次；组切换掩码为 `1/2/4/8`，同样重复两次。

该函数本身只访问 ASoC component 和寄存器，**没有直接调用 PRM 时钟申请**。核心时钟与 FS generator 由另外的 `lpass_cdc_va_macro_mclk_event`、`lpass_cdc_va_macro_mclk_enable`、`lpass_cdc_clk_rsc_request_clock` / `fs_gen_request` 等路径管理。主线 `lpass-va-macro.c:va_dmic_clk_enable()` 已有相近的门控逻辑，但 TX 没有原厂统一 component 的共享调用；现有 DT 通过跨组件依赖触发 VA DMIC3 事件。

## 本轮实机对照

录音固定为 `arecord -D hw:0,2 -f S16_LE -r 48000 -c 2`，DEC0/1 采用原厂路由和 0 dB。统计剔除第一秒；同时检查每秒去直流 RMS，避免把启动瞬态误判为声学信号。

| 试验 | 实际配置与观察 | 结果 |
| --- | --- | --- |
| 基线，7 秒 | VA `0x088=5`、`0x08c=0`，MIC BIAS3 On；GPIO8/9 已复用，12/13 尚未复用；GPIO8 的 20,000 次采样均为 0 | 第一秒之后双声道所有样本为 0 |
| DMIC4 临时补齐，两轮各 12 秒 | 添加 `TX DMIC4 -> VA DMIC4`、`TX DMIC4 -> MIC BIAS1`，TX DMIC3/4 均依赖 `VA_MCLK`；GPIO12/13 临时配置为 func1、8 mA、无上下拉 | 两轮第一秒之后双声道所有样本均为 0，逐秒 RMS 均为 0 |
| 补齐期间的独立快照 | `VA_MCLK`、VA DMIC3/4、MIC BIAS1/3 都为 On；VA `0x088=5`、`0x08c=5`、`0x094=0`，WCD MICB1/MICB3=`0x50` | GPIO8/12 各 20,000 次采样均为 0；GPIO0 SoundWire 对照仍有约一半高电平和上万次翻转 |

第二轮补齐期间，现有时钟框架的 `TX_CORE_MCLK` 为 19.2 MHz、enable/prepare=1；`RX_CORE_TX_MCLK` 为 19.2 MHz、计数 2；`RX_CORE_MCLK2_2X_MCLK` 为 19.2 MHz、计数 6；`fsgen` 计数 3。VA GFMUX `0x03420000=0`。这只是现有时钟请求与寄存器状态的读数，**不是输出波形或频率的测量**。

GPIO 软件采样复现了前一日的“没有时钟翻转”观察；本轮没有示波器/逻辑分析仪验证物理时钟，也没有把软件采样结果当成频率计。MICBIAS 实际电压、上电顺序、电源负载和原厂 Android 下的时钟源状态仍未测。

## 恢复与下一步边界

限时诊断模块先保存 GPIO12/13 配置，添加临时路由并同步 DAPM，保持约 4.5 秒，再删除路由、同步并恢复引脚。模块初始化最后返回 `-EAGAIN`，所以 `insmod` 显示 `Resource temporarily unavailable` 是设计行为；日志中的执行和恢复结果才是依据，模块不会驻留。

收尾已核对：9 个触及的 mixer 控件逐项与原值一致；GPIO12/13 回到 `0x401`；DMIC4 的 VA `0x08c` 回到 0（录音尚活动时读取）；MICB1/MICB3 在采集结束后均回到 `0x10`；PCM 关闭，无录放音/helper 进程或诊断模块驻留。声卡仍在，通话音频服务与 ModemManager 活跃。本轮未做新的通话、扬声器声学回归或重启验证。

原始反汇编、模块源码、构建脚本、录音、寄存器快照与还原记录位于忽略的 `logs/mic-20261113/`，手机工作目录为 `~/mic-test-20261113/`。[evidence.json](evidence.json) 只保存哈希与整理后的数值，不含原始音频和个人信息。

后续需要比较**原厂正常采集时**的核心时钟来源/参数、GFMUX、FS generator 与偏置时序，并尽可能测量 GPIO8/12 波形。当前证据尚不能确定根因在 DSP、主机时钟配置还是实际供电。不得重复前一日导致 DSP 崩溃的额外 q6prm 时钟申请。首轮没有提供或部署声称修复麦克风的持久补丁；后续为修正 VA 端口准备的候选见下节。

本地验证：三个原厂 LPASS 模块的 SHA-256 与归档 `SHA256SUMS` 一致；两份量产 DTBO 的偏置映射分别核对；本地重新解析三份 WAV，稳定段全零与手机统计一致。诊断模块以当前 WSL 内核输出构建通过（`W=1`）；`bash scripts/check.sh`（含 63 项测试）及 `git diff --check` 通过。这些检查不代表声学或物理电气验证通过。

## 同日续测：核心时钟、偏置先后顺序与 VA 候选

用户要求继续完成修复后，追加以下可恢复对照。**麦克风仍未修好。下述候选随后已部署、重启并测试，不能再视为待刷写镜像。**

1. 采集 20 秒 ADSP F3 文字日志，共 1937 条；378 个不同哈希中 375 个与既有公开固件字符串完全匹配。DSP 实际收到 `0x30c`、`0x318`、`0x312` 的 19.2 MHz 时钟请求，attribute=1、root=0；与原厂 audio-ref-clock 的配置相符。[原厂 `audio_prm.c`](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8450/blob/877203a7cf9b79973d44a9db716490f95d820110/vendor/qcom/opensource/audio-kernel/dsp/audio_prm.c) 的时钟负载也未显示另一个遗漏的普通录音时钟参数。日志中 Codec DMA type=1、interface index=4、channel mask=3，48 kHz / 16 bit / 双声道，端口成功打开；没有发现本次媒体图的拒绝或 DMA 错误。
2. 重新检查原厂 WCD938x `MICB_ENABLE`：在启用偏置前，原厂会置四个 `MICBx_TEST_CTL_2` 的 bit 0，主线遗漏了这一步。限时模块在 MIC BIAS1/3 已有的 DAPM 请求下先将两路偏置关闭，再设置 `0x306c/306f/3072/3075=1`，最后重新启用偏置。所有寄存器均硬件读回成功；保持后又做了 DMIC 全局 reset 的短脉冲对照。GPIO8/12 仍无翻转，第二秒之后录音全零；声道 1 第二个一秒窗口仅有峰值 12 的 30 个非零样本，不能算作声学信号。四个初始化位及两路偏置均逐个恢复、读回核验，DMIC 寄存器也已恢复。
3. 临时添加 `TX DMIC3/4 -> vdd-micb`，确认该 regulator supply widget 进入 On，录音仍无稳定信号；删除临时路由并恢复引脚和 mixer。这个对照没有证明物理偏置电压正常。

以上三轮新增录音均为 12 秒；本地重读 WAV 确认第二秒之后两个声道所有样本为 0。没有重启，没有新增 q6prm 时钟申请，没有保留诊断模块、录音进程或临时路由。

### 已部署的 VA / DMIC4 设备树候选

[增量实验补丁](../../config/audio/sm8450-oneplus-negroni-dmic34-va.patch) 修正 `VA Capture` CPU DAI：`TX_CODEC_DMA_TX_3` 改为 `VA_CODEC_DMA_TX_0`；补齐 DMIC4 的 GPIO12/13、MIC BIAS1、VA DMIC4 及 VA_MCLK 依赖。它依赖现有 DMIC3 实验改动，只在当前 WSL 工作树执行过 `git apply --check`，**尚未应用、提交到内核树或接入正式构建**。独立 DTS 预处理/编译通过，已有的相机等 DTC 警告不计作本补丁的功能验证。

这次测试镜像直接修改新备份中的 DTB，未使用含其他未提交功能的整棵源码 DTB。逐属性核对只有 14 个麦克风相关属性发生变化（包括新引脚节点属性）；分区中 DTB 区域及头部 DTB size 字段以外的所有字节保持原样，原有 ramdisk、USB2 LPM 与其他设备配置由字节比较保留。镜像全长 201,326,592 字节，与当前分区相同。

| 文件 | SHA-256 |
| --- | --- |
| 原 `vendor_boot_b` 完整备份 | `b6186469f626c4d732f8f6960d727d84a7e54883df8759407a9fa6a3aaa8d67f` |
| `vendor_boot-dmic34-va-test.img` | `c86b6e9a1f861047f9bd71cb40af2e8f508216f600ce94cfd2cc551491233ce8` |
| 候选 DTB | `d233078afbbe2ffa0aa6b98dd7fca04155b037a64828daff80309501066399da` |

手机和电脑都已核对三个文件的 SHA-256。手机目录 `~/mic-test-20261113/boot-candidate/` 含镜像、完整备份、属性差异清单和部署/回滚脚本；电脑副本在 `logs/mic-20261113/boot-candidate/`。部署脚本在写入前重新要求 B 槽 Active / Successful / Bootable 均为 1、所有 PCM 关闭，且分区哈希仍与备份一致；脚本本身不重启。用户明确要求“重启”后，已运行部署脚本写入 B 槽，完整分区读回哈希与候选一致，随后重启；USB SSH 和声卡恢复。回滚脚本没有执行。

重启后 B 槽 Active=1 / Successful=1 / Bootable=1，A 槽 Bootable=0。运行时 DT 的 VA CPU DAI 已是 110（`VA_CODEC_DMA_TX_0`），VA pinctrl 含两组引脚，分区读回哈希仍匹配候选。独立 VA 后端从 `Invalid argument` 变成正常完成 12 秒采集；同轮 TX 也是 12 秒，两者第一秒之后的两个声道均全零。候选修好了独立 VA 路径无法测试的问题，没有恢复麦克风。


## 2026-11-14：数据通道定位、双声道状态修复与重启复测

### 电源和数据引脚对照

- 上一轮 BOB 试验请求精确 3.296 V，实际返回 `-EINVAL`，**在写入前退出**，不能当成已经比较过电压的阴性结果。本轮先查询 regulator 支持范围，再请求 3.296—3.328 V，实际读回为 **3.320 V**；同时按原厂顺序置四个 MICBx_TEST_CTL_2 bit 0 并启用 MIC BIAS1/3。寄存器硬件读回符合请求，录音稳定段仍全零；六个寄存器和 BOB 原值 3.032 V 均已恢复并读回核验。此处是 regulator API 的电压读数，麦克风端实际电压仍未用仪表测量。
- 独立 VA 的 DMIC2/3、DMIC4/5 两种选择各采集 6 秒，稳定段均全零，10 个 mixer 控件逐项还原。
- 保持数据脚为输入，只给 GPIO9/13 的弱上下拉做短时变化，PCM 有大幅响应。进一步分开两路：先只改变 GPIO9，再只改变 GPIO13，各 6 个 100 ms 高/低周期；**左声道只在 GPIO9 阶段响应，右声道只在 GPIO13 阶段响应**，还原后均回零。两路引脚配置完整还原。这说明两路数据输入经过 TX 解码、DSP 和 PCM 的对应关系有效；这些是人为电平变化，不是麦克风声学信号。
- 将 GPIO8/12 临时切成软件 GPIO 时钟输出，分别在高/低相位抽样数据；在 BOB=3.320 V、原厂偏置初始化位已启用的同一时间窗口内，平均写周期约 0.75—0.94 MHz，数据仍全低。两个时钟复用均还原。该频率由 CPU 写循环耗时估算，不能代表物理波形、满足麦克风规格的连续时钟，也不能据此排除供电、连线或时钟问题。
- 再次核对原厂 LPI 的 23 个寄存器偏移，均为 pin×0x1000；未发现 GPIO8/9、12/13 的地址表差异。原厂 FS generator 序列与主线相同，VA probe 未读取的旧 `va-clk-mux-select` 属性也不能直接当成遗漏的初始化操作。

### 修正 TX/VA 多通道状态和内置麦克风 UCM

实机执行 UCM 的 Mic1 Enable/Disable 时发现两路 mixer 不能全部关闭。原因已在主线代码定位：TX 用单个 `active_decimator` 决定多位 channel mask 的更新；关闭一路后把该值置 −1，下一路关闭被跳过；交错或重复使能还会使计数与 mask 不一致。VA 的重复写也会重复修改计数。TX 的数字静音原来只处理最后一个解码器。

内核提交 **`463023bf84b1a26722c7a03c5f005c85a17a30fe`** 改为按各通道当前 bit 判断是否需要更新，保持 mask/count 一致，并让 TX 静音遍历全部已选通道。父仓库 gitlink 和 `local-7.3.bundle` 已更新；没有提交 WSL 中其他相机、DT 或语音图改动。两模块单独用当前内核输出构建，备份手机旧文件后安装到 rootfs 并重启；运行中 ELF build-id note 与新模块逐字节相同，确认新代码已加载。此次模块更新没有再次写启动分区。

[HiFi.conf](../../config/audio/ucm2/OnePlus/negroni/HiFi.conf) 的 Mic1 从 ADC1/SoundWire 改为 DEC0=DMIC3、DEC1=DMIC4、两路 0 dB，移除不对应内置 DMIC 的 ADC1 音量声明。测试脚本也改成该 PCM 实际支持的双声道采集。UCM 已备份并安装到手机。

重启后通过真实 ALSA UCM API 启用 Mic1，8 个路由/增益控件逐项匹配；采集 12 秒后禁用，两个 DMIC MUX 均回 ZERO、两个 AIF mixer 均回 off，随后完整恢复测试前的 11 个控件。**TX 的 12 秒录音与 VA 的 6 秒复测在第一秒后仍全零，麦克风未修复。** B 槽成功位保持为 1，声卡、USB SSH、通话音频服务和 ModemManager 均恢复。未做新的通话上行、扬声器听感或耳机声学回归。重启后停在 SDDM 登录界面，oneplus 桌面会话未登录；该会话的 PipeWire profile/源节点切换未验证，不能把 ALSA UCM 验证写成桌面录音通过。

回归脚本 [test-lpass-capture.py](../../tests/test-lpass-capture.py) 提取真实驱动回调，覆盖重复开关、不同关闭顺序、三个 DAI、8 个通道的计数与 mask、一致的通道映射和双通道静音。新代码通过，分别换回原 TX 或原 VA 回调均触发运行时断言失败。两个 ARM64 模块 `W=1` 构建通过；恢复 bundle 导入临时仓库后移除源码对象引用，仍能读取与测试相同的两个驱动并通过回归。`bash scripts/check.sh` 的 63 项既有测试、43 个 Python 文件语法和 UCM 依赖检查通过。收尾确认所有 PCM 已关闭、无诊断模块或录音/helper 进程，MICB1/3 均为 `0x10`，本次启动未记录 DSP fatal、内核 oops 或 GPR port 1 丢失。

本轮原始材料在忽略的 `logs/mic-20261114/`，phone 端在 `~/mic-test-20261114/`；旧模块、UCM 与分区备份均保留。仍需正常原厂运行时的状态对照，或测量麦克风端偏置和 GPIO8/12 时钟波形，才能继续区分供电、实际时钟输出和初始化差异。现有证据不支持宣布 DSP、主机时钟或硬件中的任一个为已确定根因。
