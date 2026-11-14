# 相机调试

状态日期：2026-11-14，实机 OnePlus 10 Pro NE2210；本轮实验源码基于 `463023bf84b1`，运行内核仍为此前安装的 `7.3.0-sm8450+`。

**四颗相机均已取得 RAW，主摄、长焦、前摄也已解包出真实场景。2026-11-14 下午修正 CSID 顶层配置与停流路径后，候选模块连续 58 次四摄切换/重复启停未再硬重启；该修正已提交为内核 `a7d9e945d961`，并已编入 `/opt/negroni-build/images/7.3`。2026-11-14 17:03 经同意只写 `boot_b` 并换上对应的 `qcom-camss.ko` 后重启，内核变为 `#5`（16:24:56 构建），模块哈希 `9ca488a3…`，B 槽仍为 Active / Successful / Bootable。17:10 那份只有 CSID 修复的模块不认识 C-PHY，四摄 overlay 探测失败；超广角随后因 `titan_top_gdsc` 卡在 off 而无法再次上电。随后把 C-PHY、gen2 PHY、GDSC 保持和连续 DMA 提交为内核 `d1ca2f4d48c2` 并写入 `boot_b`。17:34 重启为内核 `#6`（17:16:58 构建），模块 `e8d3b218…`，B 槽仍成功。17:35 用这份模块跑主摄→长焦→前摄→超广角共 4 轮、16 次启停全部出帧，`failures=0`，没有 GDSC 卡住，也没有硬重启，boot ID `a8d22d68`。测试结束已卸掉 overlay。长时间运行和睡眠交叉仍未测，尚不可作为日常相机使用。** 当前手机上仍是手动配置的实验采集路径，未接入相机应用。

## 相机应用 Snapshot（2026-11-14 晚）

经用户同意，20:31 在手机上执行 `pacman -Syu`（61 个包，含 PipeWire 1.6.11、WirePlumber 0.5.19、systemd 262.2、BlueZ 5.88；不含内核、mesa、固件），并安装 `libcamera` / `libcamera-ipa` / `libcamera-tools` 0.7.2、`pipewire-libcamera`、`gst-plugin-libcamera` 与 GNOME `snapshot` 51.0。手机原有的包数据库已过期，镜像站删除了旧的 `gst-plugins-good` 等文件，只装应用会 404，必须整体升级。

手机上额外做了两处配置（均未纳入镜像构建）：

- `/etc/udev/rules.d/70-negroni-dma-heap.rules`：`SUBSYSTEM=="dma_heap", KERNEL=="system", GROUP="video", MODE="0660"`。缺少它时 libcamera 报 `Could not open any dma-buf provider`，软件 ISP 被禁用，只能输出 RAW。只开放 system heap，CMA 区仍为 root 独占。
- `~/.config/wireplumber/wireplumber.conf.d/50-negroni-camera.conf`：`monitor.libcamera = required`，并用 `monitor.v4l2.rules` 把描述为 `Qualcomm Camera Subsystem` 的 17 个 CAMSS 原始视频节点设为 `device.disabled`，保留 Iris 编解码节点。随后只重启了 WirePlumber，音频设备恢复正常。

实机结果（开机自动加载的只有超广角 S5KJN1，其余三颗仍需手动 overlay，因此应用内只有一个后置摄像头）：

- `cam -l` 识别为 `Internal back camera`，simple pipeline + 软件 ISP；`cam` 默认选 8152×6144 ABGR8888，约 10 fps，20 帧采集正常。
- Snapshot 经 KDE 相机门户授权后预览 1920×1080 BGRx；用户录得 1.63 s、49 帧、1920×1080 30 fps VP8 + Vorbis 的 WebM，竖屏方向正确、场景可辨认，但偏亮发灰、饱和度低。全程 boot ID `77beb172` 未变，未硬重启。
- libcamera 警告：传感器驱动缺少裁剪矩形（PixelArrayActiveAreas 被默认为整幅）、没有 `s5kjn1` 的静态属性与 sensor helper，IPA 使用 `uncalibrated.yaml`。这些是颜色、曝光不准的直接原因。
- 同时段另一会话向 S5KJN1 的 runtime PM `power/control` 写入时出现 `cam_cc_mclk1_clk status stuck at 'off'` 与 CCI 超时，与 Snapshot 无关，但说明多会话同时操作相机会互相干扰。

未测：Snapshot 拍照、长时间预览/录像、前后摄切换（需其余三颗进入开机加载）、睡眠唤醒后再开相机。

## 启停硬重启修复（2026-11-14 下午）

对照原厂 `cam_ife_csid_hw_ver2.c`、`cam_ife_csid680.h` / `cam_ife_csid_lite680.h` 后，在主线 CSID 680 及公共流程中确认三处代码缺陷：

1. **CSID lite 越界写顶层寄存器**。主线对所有 CSID 都把 `0x101` 写到 wrapper（`0xacb6000`）的 `0x4 × id`。原厂只有完整 CSID0–2 设置 `need_top_cfg`，IO path 寄存器为 `0x0/0x4/0x8`，`0xc/0x10/0x14` 是 CSID0–2 的 dual CSID 配置；lite 不碰顶层。主线中超广角/长焦（CSID3）和前摄（CSID4）因此把 CSID0/1 的 dual 配置写成非零值。wrapper 状态在 GDSC 保持下跨会话残留，原厂在 `disable_core` 中显式恢复复位值并注明是为避免连续会话冲突。
2. **停流从未关闭 CSID**。`need_vc_update` 在开流时清零，停流的 `configure_stream(0)` 因此被跳过；日志中每次停流时 `RDI_CFG0` 仍为 `0x802bf000`（使能位置位），随后 PHY 关 lane、时钟断电，RDI 路径仍保持使能。
3. **开流失败不回退**。传感器 `s_stream(1)` 失败时，`video_start_streaming()` 直接返回，已启动的 VFE、CSID、PHY 既不停止，v4l2 也继续记为已开流；下一次开流触发 `call_s_stream` WARN 并跳过硬件配置。

修正：lite CSID 不再写顶层；完整 CSID 开流时把 dual 配置清零，停流时恢复 IO path 复位值 `1` 与 dual `0`。SM8450 停流总是先 halt RDI、清使能位并下发 RUP；开流失败时自 sink 向上逐个停止已启动的实体。差异见 [camss-stream-stop-fix.patch](../artifacts/camera-20261114/camss-stream-stop-fix.patch)，需叠加在同目录 `camss-experimental.patch` 之上。

实机（只加载 RAM 模块和 overlay，未刷写、未切槽，结束时已恢复原安装模块）：

| 模块 | 序列 | 结果 |
| --- | --- | --- |
| 修正 1+2 | 主摄→长焦→前摄→超广角 ×2 | 8/8 通过；以往该序列每次都在第四步或之前硬重启 |
| 修正 1+2 | 继续 ×5 轮 | 第 5 轮主摄 CCI 写 `0x0136` 超时（`-110`），触发缺陷 3，第 6 轮主摄无帧并出现 3 次 WARN；第 7 轮主摄恢复。随后手机被**另一会话的 `sudo systemctl reboot`** 有序重启（journal 可证），并非相机故障 |
| 修正 1+2+3 | 四摄 ×10 轮；主摄、超广角各连续 5 次；长焦/前摄交替 3 次；前摄、主摄各 30 帧 | **58/58 通过**，无重启、WARN、CSID 复位超时或 SMMU 错误；每次停流后 `RDI_CFG0` 读回 `0x2bf000` |

候选模块 SHA-256 `b9c6904ce0b09a599a3512c29c1d299640553973809c243a2b21a566a454ace5`，在手机 `~/camtest/rear-1348/qcom-camss-fix124.ko` 与忽略的 `logs/camera-analysis-20261114/`。

未测/未完成：开流失败回退分支本身未被触发过（CCI 超时未再出现）；CCI 偶发超时的原因与重试未处理；未做更长时间（数百次、多小时）或系统睡眠交叉测试。修正已提交为内核 `a7d9e945d961`，gitlink 与 `local-7.3.bundle` 已更新。镜像已重新封装到 `/opt/negroni-build/images/7.3`（`boot.img` SHA-256 `3fb7199a69055b9d17c4bed80f1760f48fb27c72b1df6f1657d4ec9449392d98`）。同日 17:03 备份 `boot_b`（SHA-256 `4a745b2f74c2b31a9357b81c28687a977ba2d05606780c2c4197517fa67a079f`，手机 `~/camtest/boot_b-backup-20261114.img`，电脑 `logs/camera-20261114/`）后写入该 boot 并回读一致；ramdisk 与启动参数和原分区相同，`vendor_boot_b` 未动。旧模块备份为 `qcom-camss-backup-20261114.ko`（`0c78430b…`）。重启后槽位标记保持成功。17:10 的四摄和超广角启停见上文，均未出帧。17:33 再备份当时的 `boot_b`（SHA-256 `032c93cceb5cd9768507bd3d87714861ec6c9c0810fdd1533dc20c07bab38c7a`，手机 `~/camtest/boot_b-backup-before-cphy.img`）后写入 `d1ca2f4d48c2` 的 boot（SHA-256 `070cef14…`）并安装模块 `e8d3b218…`。17:35 四轮四摄启停 16/16 出帧，没有硬重启。原厂 CPAS 在任何 PHY/CSID 访问前打开 `cam_cc_core_ahb_clk`、`cpas_ahb`、`camnoc_axi` 等，而主线 CAMSS DT 不含 `CAM_CC_CORE_AHB_CLK`；当前测试中该差异未造成故障，补齐需改设备树及刷写，尚未实施。

## 四摄进展（2026-11-14）

本轮只通过 USB SSH 加载实验模块和 RAM overlay，没有刷写分区或主动重启。传感器配置交叉参考本机 Android sensormodule、原厂 20846 量产设备树及固定提交的 OnePlusOSS 公开源码，详细来源、代码与限制见[四摄实验归档](../artifacts/camera-20261114/README.md)。

| 镜头 | 实机 RAW 模式 | 接收链路 | 结果 |
| --- | --- | --- | --- |
| IMX789 主摄 | 4000×3008 RAW10，stride 5008 | PHY1，三个 C-PHY trio | 读 ID `0789`、真实场景及色条取帧；首次移植低速 C-PHY |
| S5KJN1 超广角 | 4080×3072 RAW10，stride 5104 | PHY2，四通道 D-PHY | 读 ID `38e1`，沿用已验证的 GRBG 路径，新增三次各 30 帧诊断通过 |
| OV08A10 长焦 | 3264×1836 RAW10，stride 4080 | PHY0，两通道 D-PHY | 读 ID `0841`，修正 FTM 表末段的实际高度后取得真实场景 |
| IMX615 前摄 | 3280×2464 RAW10，stride 4112 | PHY5，四通道 D-PHY | 读 ID `0615`，真实场景及标准八色条，RGGB 相位已验证 |

主摄全局表的 `0x0101=3` 同时翻转两轴，候选源码与统一采集工具已从初版 RGGB 元数据改为 BGGR；色条离线核对通过，同日下午修改后的模块也已完成实机单帧拍摄。长焦暂用 BGGR，但测试图案命令未产生可确认的色条，颜色相位仍待验证。上述预览都没有完整色彩标定。

主摄、长焦、前摄分别完成过 60 帧采集，随后切回超广角时硬重启；部分序列存在 66.6 ms 间隔及约 18–24 fps 的平均交付率，不能宣称四摄稳定 30 fps。跳过 PHY 版本读取、原厂复位序列、CSID 停止复位以及保持六组 PHY 时钟的对照均未消除故障。多次失败落在 `v4l2_pipeline_pm_get()` 的 PHY 上电/复位阶段，另一次外部日志捕获到 `Oops - Undefined instruction`，PC 为 `csid_configure_stream+0x14c`；完整 panic 栈仍缺失，不能据此认定 DMA、时钟或片上总线中的某一项为根因。未奏效的诊断修改没有保留为正式修复。（同日下午的 CSID 修正已使该序列通过，见上文“启停硬重启修复”；上述对照均未改动 CSID 顶层写入，也未在停流时清除 RDI 使能位。）

新增[统一单次采集工具](../scripts/negroni-camera-multi-capture.sh)和[离线 sensormodule 检查器](../scripts/inspect-camera-sensormodule.py)。前者要求已经手动加载本轮候选模块及 overlay，不负责安装；同日下午使用最终编译模块，按主摄→超广角→长焦依次丢弃四帧、保存一帧实拍，三次均成功，单帧长度和传回电脑后的 SHA-256 均核对一致。拍摄及卸载恢复期间 boot ID 未改变，未发生重启；这三次成功不代表此前启停故障已解决。前摄尚未用统一脚本重测。后者验证本机观察到的 V3.5.1 文件长度、CRC32、表边界与寄存器位宽，不向硬件写入。RAW 和基础白平衡 PNG 仅保存于忽略的 `logs/camera-20261114/rear-1348-*`，不提交私人场景照片。

结束时已停止采集；故障重启后 RAM overlay 和额外传感器模块均已消失，安装的 CAMSS 模块哈希仍为原来的 `0c78430b…d3fd4`，CCI / CAMSS / CAMCC 的 PM 策略恢复 `auto`，B 槽仍为 Active / Successful / Bootable。实验代码仍在工作区和归档，未提交到内核、未更新 gitlink / bundle、未启用自动加载。稳定启停、AF/OIS、主摄/长焦标准曝光增益控制、EEPROM 标定、AE/AWB、ISP/libcamera、JPEG/录像、多摄并发、HDR 与高分辨率模式仍未完成或未测。

## 超广角已验证（2026-11-13）

- USB SSH 下识别到 `s5kjn1 6-0010`，传感器、CSIPHY2、CSID3 和 VFE3-lite/RDI0 组成完整 media graph。
- 4080×3072、四条 CSI-2 data lane、700 MHz link frequency、GRBG RAW10 可采集。V4L2 格式为 `pgAA`，stride **5104** 字节，单帧 **15,679,488** 字节。
- 传感器测试色条解码后为白、黄、青、绿、品红、红、蓝、黑，顺序和像素值正常。
- 用户确认镜头无遮挡后，实拍 RAW 解码能辨认室内天花板、灯具等真实场景。曝光与模拟增益控制有效；这不代表自动曝光、白平衡、畸变校正或色彩标定完成。
- 独立取帧及两次各 180 帧的采集成功，时间戳约 33.3 ms/帧，即约 30 fps。随后再次启动失败，不能据此声称连续重开稳定。
- 测试内核重启后 USB SSH、声卡枚举和传感器绑定恢复，B 槽仍为 Active / Successful / Bootable。

## 修正与来源

相机补丁副本见 [camera-bringup.patch](../artifacts/camera-20261113/camera-bringup.patch)，整理结果见 [实机依据](../artifacts/camera-20261113/README.md)。WSL 内核树中相机相关修改仍未提交，父仓库 gitlink 和恢复 bundle 未更新，**尚未接入正式完整镜像**；补丁不包含同一工作树里的音频修改。

1. 板级 DT：MCLK1 改为 24 MHz，reset 改为 GPIO24 低有效，CSI 连接改为 CSIPHY2；模拟电源使用 PM8010J L3（2.8 V）、数字核电源使用 PM8010J L1（1.056 V）、I/O 与 EEPROM 使用 PM8350C L2。供电与连接来自上一轮对原厂 DTBO 的核查。本轮读取实际 `vendor_boot_b`，确认设备已经使用这些参数；本轮未重刷设备树。
2. CAMSS PHY：`csiphy_is_gen2()` 补上 `CAMSS_8450`。原代码虽有 SM8450 lane table，实际却选择了旧的寄存器编程路径。原版模块在本轮复现 STREAMON 成功但 8 秒无帧；修正后收到完整色条和实拍帧。
3. CAMCC：移植 Sushmit Singh Rathore 的 [GDSC 状态保持修复](https://lore.landau.one/lkml/20261020142157.1749-3-sushmit718@gmail.com/)和[关闭 RCG 时停到 XO 的修复](https://lore.landau.one/lkml/20261020142157.1749-4-sushmit718@gmail.com/)。原内核热加载相机模块后出现 `titan_top_gdsc status stuck at 'off'`；新内核能够再次探测并采集，但未解决后述重复启动硬重启。
4. DMA：移植 Loic Poulain 的 [Use contiguous DMA buffers](https://lore.landau.one/lkml/20261111135338.27008-2-allan@fatecpompeia.edu.br/)，把 `vb2_dma_sg` 改为 `vb2_dma_contig`，保证每个 plane 在设备地址空间中连续。该修正已单独编译、加载并能取帧，**同样未解决重复启动重启**，不能把内存不连续当成本机故障已确认的根因。

## 一加原厂源码参考

2026-11-13 已从 OnePlusOSS 的 SM8450 公开仓库定位项目 `20846` 的量产相机设备树、JN1 的 299 条 FTM 寄存器表及正常配置的用户空间下发路径。核查记录和精确源码链接见[原厂源码研究](../artifacts/camera-source-20261113/README.md)。这些源码面向原厂 Android 内核，移植到当前主线内核需适配。

原厂 DT 的默认 MCLK 是 19.2 MHz，当前主线 JN1 使用 24 MHz，PLL 与行/帧时序也不同；原厂代码允许上电命令覆盖 DT 时钟，不能从 DT 单个值推断正常拍摄的完整配置。本次所查公开文件未发现本模组完整的 AWB / CCM 调校数据，继续查颜色应沿原厂用户空间相机配置及 EEPROM 标定内容追踪。该核查没有改动手机。

2026-11-13 后续只读核查已在本机保留的 ODM 中找到 JN1 的 730,626 字节 sensormodule、10,821,904 字节 tuning、传感器 ELF，以及两份可读 DNG `ColorMatrix`。这些是后续解码原厂初始化与色彩参数的依据，尚未应用或完成调校验证。原厂场景配置注释为 GBRG，不能直接推翻当前色条已经验证的 GRBG 相位；两者的模式、镜像和处理阶段需继续核对。版本、文件哈希及使用边界见[原厂硬件资料](stock-hardware.md#相机)。

## 超广角硬重启对照（2026-11-13）

本次四组对照均复现：

| 测试 | 结果 |
| --- | --- |
| 每次卸载、重载 CAMSS，再取 1 帧色条 | 前两轮通过，第三轮在 QBUF 后、STREAMON 返回前失联，随后新 boot ID |
| 保持模块加载，普通重复打开，每轮 180 帧 | 前两轮通过，第三轮同样失联并硬重启 |
| 临时保持 CAMCC、CCI、CAMSS 的 runtime PM 为 `on`，并阻止系统睡眠 | 前两轮各 60 帧通过，第三轮仍硬重启 |
| 换用连续 DMA 缓冲区，每轮 30 帧 | 前两轮通过，第三轮仍硬重启 |

每组测试前已有的拍摄次数不同，不能总结成“每次开机第三次拍照必崩”。共同观测是失败发生在新一轮 `VIDIOC_STREAMON` 返回前，而非正在输出帧时。用户确认首次非正常重启并非手动操作；之后的 boot ID 变化及 `oplusboot.startupmode=hard_reset` 进一步支持硬重启判断。另有一次 SDDM 请求的有序重启，已与这些故障区分。

当日持久 journal、实时转发的 kmsg 与 pstore 均未捕获到解释故障的 panic / Oops。2026-11-14 已增加诊断点并捕获部分 Oops，进展见上文；仍不能区分 VFE/CSID 启动、DMA、时钟或片上总线故障，重复同一测试没有定位价值。

结束时已停止采集，USB SSH 恢复，CCI / CAMSS / CAMCC 的 `power/control` 均为 `auto`，没有留下保持电源开启的服务。

## 单次实验采集

这仅用于继续开发；**旧模块不要循环调用或热重载压测**，未含 2026-11-14 下午 CSID 停流修正的模块仍会硬重启。含修正的候选模块通过了 58 次启停，但尚未进入正式镜像。脚本依赖手机已有的 `v4l-utils`、`psmisc`、`util-linux` 与 `coreutils`，会拒绝覆盖已有文件及占用中的相机设备，并在退出时恢复 CCI 的 runtime PM 策略。

把 [negroni-camera-capture.sh](../scripts/negroni-camera-capture.sh) 复制到手机后：

```sh
# 参数：输出文件、保存帧数、测试图案、曝光行数、模拟增益。
# test_pattern=0 为实拍；2 为色条。一次采集先丢弃 4 帧。
sudo bash negroni-camera-capture.sh /tmp/jn1.raw 1 0 3840 8
```

输出是带行尾 padding 的 MIPI RAW10，不是 JPEG。每行仅前 5100 字节为 4080 个像素，余下 4 字节为 padding；必须按 5104 的 stride 解包。传感器旋转属性为 90°，上述文件未自动旋转。保存拍摄文件后先 `sync` 并复制到电脑，避免后续开发中的硬重启丢失缓存内容。

8160×6144 模式、libcamera、实时预览、录像、长时间温控和全新完整镜像均**未测**；其余三颗镜头的后续 RAW 进展见上文。超广角的软件曝光、白平衡和 JPEG 见下一节，尚未在本轮实机跑通。

## 静态照片、闪光灯与模组 EEPROM（2026-11-14）

主线 CAMSS 只出 RAW。原厂 `camera.ko` 约 12 MB，把 sensor、CCI、EEPROM、actuator、OIS、闪光灯、CSID 和 VFE 绑在 5.10 的一套私有接口里，不能装进当前 7.3 内核，也替代不了 Android 的 Spectra ISP、3A 统计和硬件 JPEG。这一节是能在现有 RAW 路径上做的后处理，不是那套 ISP。

当前启动的设备树里只有超广角 S5KJN1。它没有对焦马达。原厂 DT 里主摄 OIS 是 LC898128，长焦 OIS 是 LC898124，另外各有一颗 actuator；从地址和固件都在原厂用户空间里下发，主线没有对应驱动。没有在未知寄存器上动镜头。

超广角模组上的 GT24P128F 在 CAMSS 和传感器都恢复供电后应答的是 I²C `0x50`。正在运行的设备树把同一颗芯片写成了 `eeprom@51`，这个地址没有应答，所以内建 `at24` 绑不上去。内核源码里的节点已改为 `eeprom@50`，还没有编译，也没有刷写。在新的设备树启动之前，读取脚本会临时建立 `24c128 0x50`，读完 16384 字节后删掉，避免留下一个可写的 EEPROM 设备。只把传感器的 runtime PM 设成 `on` 并不会真正上电，必须先把 CAMSS 保持为 active。把下面的脚本和采集脚本放到同一目录后：

```sh
# 先打开 CAMSS 和 JN1，再从 0x50 读出 16384 字节。
sudo bash negroni-camera-eeprom.sh /tmp/jn1-eeprom.bin
# 测光一帧，必要时再拍一帧，做灰世界白平衡并写成 JPEG。
# --torch 是持续低电流；--flash 在 STREAMON 前以 400 mA、最长 1.2 s 软件触发 PMIC 闪光。
# 闪光没有接到传感器的硬件 strobe 脚。
sudo bash negroni-camera-still.sh /tmp/jn1.jpg --flash --eeprom /tmp/jn1-eeprom.bin
```

JPEG 是 2040×1536 的 2×2 合并，假设黑电平 64，套 sRGB 曲线，不使用颜色矩阵和镜头阴影。旁路文件 `jn1.jpg.json` 记录本次曝光、增益和白平衡。

2026-11-14 20:40 左右实机：CAMSS、CCI 和 JN1 保持 active 后，`0x50` 的 16 位读返回数据，`0x51` 无应答。临时 `24c128` 客户端读出 16384 字节，SHA-256 `2059e5f74bfbd484f9def4a1b3809f3a992f2fb2d13841528a5dd08b8b01c2b6`，其中 12336 字节不是 `0x00` 或 `0xff`。读完已删除这个可写客户端，`6-0050` 不再存在。单次 16384 字节的 `read()` 只会得到前 4096 字节，脚本改为 128 字节一块。当时 JPEG 没有拍：WirePlumber 正把 `/dev/media0` 和 `/dev/video2` 交给 `org.gnome.Snapshot`，超广角流是 active。没有关掉这个应用，闪光灯也没有点亮。

21:48 Snapshot 已退出，传感器回到 suspended，但 WirePlumber 仍握着这几个设备节点，桌面上没有 active 的相机流。采集脚本改为只拒绝其他进程或正在预览的流；root 下通过 `runuser` 查询用户会话里的 PipeWire，避免直接调用 `wpctl` 连不上而漏检。无灯静帧写入 `/tmp/jn1-still.jpg`（2040×1536，508337 字节，SHA-256 `31aa993ef7287e260f182e74e824201bca2c5e406a583cefe00d3fb057bebb34`）。测光把曝光推到 4237、增益 58 后，RAW 均值仍停在黑电平 64，白平衡失败，JPEG 平均亮度约 3。随后用 torch（亮度 48）再拍 `/tmp/jn1-still-torch.jpg`（1299233 字节，SHA-256 `505935a1a885d6918625548bf2f722e205ac7f545d3afd52171ddb9fcdd7a6b1`）。同一曝光和增益下 RAW 均值 R/G/B 为 126/149/111，灰世界白平衡生效，JPEG 平均亮度约 56、最高 255。画面是补光照到的近处表面，超广角没有对焦，近距离是糊的。结束时 LED 亮度为 0，传感器、CCI、CAMSS 都回到 suspended，`control` 为 auto，启动 ID 仍是 `77beb172-93b1-4f04-9e19-8d126f440cdc`。`--flash` 的 400 mA 频闪这一轮没有触发。照片留在手机 `/tmp`，没有纳入 Git。

下次完整内核构建会打开 `CONFIG_V4L2_FLASH_LED_CLASS`。当前手机上的内核没有这个选项，闪光灯只有 `/sys/class/leds/white:flash`，拍摄脚本直接写这个 LED。该配置还没有编进正在运行的内核，也没有刷写。

## 预览偏绿的离线核查（2026-11-13）

上一轮展示的 PNG 只做 RAW10 解包、2×2 GRBG 合并、假设黑电平 64 和简易显示转换，**没有白平衡，也没有传感器 RGB 到显示 RGB 的颜色矩阵**。它用于确认出图，不代表相机完成了色彩处理。[libcamera 的处理模型](https://docs.libcamera.org/master/public-api/camera-model.html)将白平衡、去马赛克、颜色矩阵和 gamma 列为不同的处理步骤。

本轮只分析已有 RAW，未启动手机相机：

- 解包方式符合 [Linux `pgAA` / RAW10 定义](https://docs.kernel.org/userspace-api/media/v4l/pixfmt-srggb10p.html)；按 5104 字节 stride 跳过行尾 padding。八条测试色条的 RGB 中心值精确符合白、黄、青、绿、品红、红、蓝、黑，未发现红蓝互换或 Bayer 相位错误。
- 实拍中选择一块疑似中性的梁面，扣除假设黑电平后，R/G/B 中位数为 **66 / 112 / 78**。将该区域视为中性，得到约 **1.697 / 1 / 1.436** 的白平衡增益；在其他天花板区域估计的增益有所不同，说明这不是受控标定。
- 对同一帧采用相同曝光曲线，只改变白平衡增益，整体绿色明显减轻，梁面更接近灰色。这支持“预览遗漏白平衡是偏绿的主要来源”，但不能据此宣称模组颜色准确或排除所有传感器问题。

已补充 [RAW 诊断预览工具](../scripts/negroni-camera-raw-preview.py)。在电脑的 Python 虚拟环境中安装 NumPy 和 Pillow（用于数值解包及无损 PNG 输出）后运行：

```sh
python -m pip install numpy pillow
# 默认最后一帧；显式指定 R/G/B 增益，不会修改原 RAW。
python scripts/negroni-camera-raw-preview.py jn1.raw preview.png --wb 1.697,1,1.436
# 也可指定假定中性区域，坐标以完整 4080×3072 RAW 为准。
python scripts/negroni-camera-raw-preview.py jn1.raw preview-roi.png --wb-roi 240,1560,360,200
```

工具保存半分辨率预览及 `.png.json` 处理参数，采用标准 sRGB 传递函数。上述增益仅适用于本次场景，不应固定写进传感器驱动。真实光照下的自动白平衡、模组颜色矩阵、镜头阴影/色偏、色卡验证仍**未测/未完成**。实拍对比仅保存在 `logs/camera-colour-20261113/`，不提交私人环境照片；整理依据见[颜色核查记录](../artifacts/camera-colour-20261113/README.md)。

## 镜像与回退材料

2026-11-13 用户同意该轮刷写和重启，当日只写 `boot_b` 并安装相机模块，`vendor_boot_b` 保持不变；原 initramfs、启动参数与当前根 UUID 均保留。2026-11-14 没有再刷写或主动重启。测试 boot 的 SHA-256 为 `8030cb0e2fc81c01a3dbeaf1f7f6d200b2ec4f9c2563a0503b9765435cd87f4b`，当前安装的连续 DMA 模块为 `0c78430b93a2e20b3fe9d1b0866e61ef214d9d2b07ca5e800b78a947090d3fd4`。

原分区备份分别在电脑 `logs/camera-20261113/` 和手机 `~/camtest/20261113/`，原模块及 `/boot` 文件也保存在手机该目录。备份、镜像、RAW、实拍预览和原始日志均不纳入 Git。回退若要写分区或重启，仍须先按 [AGENTS.md](../AGENTS.md) 征得用户同意。
