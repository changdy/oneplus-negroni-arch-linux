# 四摄 RAW 实验移植（2026-11-14）

OnePlus 10 Pro NE2210 的 **IMX789 主摄、JN1 超广角、OV08A10 长焦、IMX615 前摄均已在主线 Linux 收到 RAW**。主摄、长焦、前摄均已离线解包出可辨认的真实场景。**同日下午的 CSID 停流修正使四摄切换/重复启停连续 58 次通过，此前每次都会硬重启；修正仍只在 RAM 模块验证，不能作为日常相机使用。**

本轮全部通过 USB SSH 操作；只加载可卸载模块及 RAM 设备树 overlay，没有刷写分区、主动重启、切槽、修改 USB role 或重绑 UDC。故障测试导致了非正常重启。结束状态及最新限制见 [相机说明](../../docs/camera.md)。

## 实机结果

| 镜头 | I²C / CSIPHY | 传输 | 已收到的 RAW | stride / 单帧字节 |
| --- | --- | --- | --- | --- |
| IMX789 主摄 | CCI0 master 0，`5-001a` / PHY1 | 三个 C-PHY trio | 4000×3008 RAW10 | 5008 / 15,064,064 |
| S5KJN1 超广角 | CCI0 master 1，`6-0010` / PHY2 | 四通道 D-PHY | 4080×3072 RAW10；沿用已有采集路径 | 5104 / 15,679,488 |
| OV08A10 长焦 | CCI1 master 0，`7-0036` / PHY0 | **两通道** D-PHY | 3264×1836 RAW10 | 4080 / 7,490,880 |
| IMX615 前摄 | CCI1 master 1，`8-0010` / PHY5 | 四通道 D-PHY | 3280×2464 RAW10 | 4112 / 10,131,968 |

读回的 ID 分别为 `0x0789`、`0x38e1`、`0x0841`、`0x0615`。上表 bus 编号对应本机本轮枚举结果，不是跨镜像稳定 ABI。

- 前摄八色条按 RGGB 解包，中心值准确为白、黄、青、绿、品红、红、蓝、黑（0 / 1023），相位验证通过。真实场景默认增益下很暗，模拟增益码 960（16 倍）能明显提亮。
- 主摄 FTM 全局初始化写了 `0x0101=3`。初版以 RGGB 标记，色条的方向和红蓝顺序暴露了双翻转后的相位问题；保存的候选源码改为 BGGR / `pBAA`。这是 RAW 格式元数据修正，没有把软件颜色矩阵当成硬件调校。该修正已离线验证，随后也用最终编译模块取得一帧实拍；首轮取帧日志保留原来的 `pRAA` 标记。
- 长焦已解包真实场景，但本轮尝试的 `0x5e00/0x4320` 测试图案未产生可确认的色条，BGGR 相位仍需进一步验证，不能声称颜色准确。
- 各镜头短测可见约 33.3 ms 的帧间隔。主摄、长焦、前摄分别完成过 60 帧采集；其中主摄/前摄长于单帧的取帧序列出现 66.6 ms 间隔及约 18–24 fps 的平均交付率，**不能统一写成稳定 30 fps**。

私人场景 RAW、PNG 和原始日志只保存在忽略的 `logs/camera-20261114/`，本目录不包含照片、镜像、固件或 EEPROM 标定负载。

## 原厂资料怎样用于实现

公开源码固定到 OnePlusOSS 的 [`877203a7cf9b79973d44a9db716490f95d820110`](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8450/tree/877203a7cf9b79973d44a9db716490f95d820110)。本机 Android 15 / ColorOS `NE2210_15.0.0.401(CN01)` 的 sensormodule 仅作离线交叉检查，不能由版本相近推断全部二进制匹配该提交。

1. 板级引脚、电源、CCI 和 PHY 来自量产项目 `20846` 的 `wly_20846_camera_overlay_common.dtsi`，并与本机保留 DTBO 核对。未混用 EVB / preT0 配置。
2. IMX615 使用公开 `cam_sensor_settings.h` 的 311 条 FTM 写入，拆成 238 条全局初始化、72 条模式配置及单独 STREAMON。238 条全局初始化与本机正常 sensormodule 的初始化逐条一致；正常模式与 FTM 的 PLL/帧长不同，没有拼接两套时序。
3. OV08A10 使用同文件 273 条 FTM 写入。表中先写 3264×2448，末段再改为 **3264×1836**。初版接收端错误地保留 2448 高度，虽然 CSID 收到大量无 CRC/ECC 错误的数据包，VFE 始终不完成缓冲区；修正为末段实际尺寸后收到完整帧。
4. IMX789 使用公开 `cam_sensor_initsettings.h` 的 184 条全局初始化及 `cam_sensor_settings.h` 的 116 条 FTM 写入。它们是工厂测试路径，**并非本机正常 HAL 的完整初始化**；本机正常 sensormodule 的全局初始化有 321 条，已保留差异。
5. 原厂基础 DT 的 CSIPHY 是 v2.1.0。C-PHY 实验移植采用同一公开快照的 `cam_csiphy_2_1_0_hwreg.h`：3×37 条 trio 配置及最低速率档的有效默认写入，使用本模式的 settle count 28、trio mask `0x2a`，向 CSID 680 传递 PHY 类型。只试验了这一低速率模式，其他速率档未移植、未测。
6. C-PHY 模式的 link frequency 候选由 19.2 MHz 及 FTM PLL 推导为 823.2 MHz；初次实机接收无 CRC/ECC 错误。没有据此验证其他帧率、48 MP、HDR 或高分辨率模式。
7. 启动 RUP 顺序参考 Hangxiang Ma 的 [Issue stream-on REG_UPDATE from CSID](https://lkml.iu.edu/2610.1/07408.html)，在 CSID RX 配置后下发初始 RUP。该对照**没有修复硬重启**。

前摄 AVDD 原厂标称 2.9 V，不是当前 PM8010 主线驱动的可选离散档。RAM overlay 选用临近且低于该标称值的 **2.896 V**，实机读 ID 和取帧通过；这不是对所有供电条件和长期稳定性的验证。JN1 继续使用现有主线 24 MHz 时序，另外三颗用 19.2 MHz，没有只改 JN1 时钟而保留原 PLL。

## 稳定性：CSID 修正后通过启停测试（下午）

根因定位在 CSID，而非 DMA 或 VFE：主线 CSID 680 对 lite 实例也写 wrapper 顶层寄存器，偏移恰好落在 CSID0/1 的 dual 配置上；停流因 `need_vc_update` 已清零而从不执行 `configure_stream(0)`，RDI 在 PHY 停止、断电后仍保持使能；传感器开流失败时已启动的 VFE/CSID/PHY 不会回退。修正见 [camss-stream-stop-fix.patch](camss-stream-stop-fix.patch)，叠加在 `camss-experimental.patch` 之上。实机连续 58 次四摄切换、重复启停与 30 帧采集通过，无重启与内核告警；详细序列、一次 CCI 超时及另一会话触发的有序重启见 [相机说明](../../docs/camera.md#启停硬重启修复2026-11-14-下午)。开流失败回退分支、长时间运行及睡眠交叉未测。

以下为修正前的记录：

最初增加日志的 JN1 模块连续三次各 30 帧通过。随后四摄切换测试中，主摄、长焦、前摄各 60 帧通过后，切回 JN1 时再次硬重启。后续电源恢复诊断、跳过版本寄存器读取、按原厂复位序列对照、CSID 停止复位对照、保持全部六组 PHY 时钟的对照均未消除故障，失败后没有把原计划的全部循环算作通过。

外部逐行落盘日志把多次失败缩小到 `v4l2_pipeline_pm_get()` 内，PHY 时钟使能成功返回后的软复位附近；另一次捕获到 `Oops - Undefined instruction`，PC 为 `csid_configure_stream+0x14c`。停止路径可能跳过 CSID stream-off、VFE680 reset 仅模拟完成，是需要修正的真实代码问题，但现有对照不能确认它们就是本机硬重启根因。**DMA 破坏内存、时钟/复位和片上总线故障仍不能区分。**

本轮没有得到完整 panic 栈；pstore 未提供可用转储。A/B 只读检查中 B 槽仍为 Active / Successful / Bootable，未切换或写成功位。源码中的未奏效诊断/停止复位实验只留在 `logs/`，没有冒充正式修复。

## 保存的代码与复现边界

- [camss-experimental.patch](camss-experimental.patch)：对内核 `463023bf84b1a26722c7a03c5f005c85a17a30fe` 的相机实验差异，包括此前 CAMCC/GEN2/连续 DMA 修正、本轮低速 C-PHY、RUP 与可选启动日志；**不含音频工作树修改，也不含失败的复位/停止实验**。
- [camss-stream-stop-fix.patch](camss-stream-stop-fix.patch)：叠加在上一补丁之后的 CSID 顶层配置、停流与开流失败回退修正（`camss-csid-680.c`、`camss-csid.c`、`camss-video.c`），由修改前后的 WSL 工作树文件直接生成；保留一行停流后的 `camtrace` 读回日志。
- [drivers/](drivers/)：IMX615 原型、OV08A10/IMX789 固定模式原型、原厂公开 FTM 寄存器表，以及 RAM overlay 加载器。IMX615 保留所基于的主线 IMX471 驱动作者与许可。`negroni_phy_hold.c` 只作失败对照存档，默认 Makefile 不构建、不启用它。
- [negroni-four-camera-test.dts](negroni-four-camera-test.dts)：本机 RAM overlay，依赖已有 JN1 DT 修正、基树 `__symbols__` 和 `CONFIG_OF_OVERLAY`；不是通用 DT binding 或完整镜像配置。
- [统一采集工具](../../scripts/negroni-camera-multi-capture.sh)：按镜头选定本轮 graph、尺寸和 stride，拒绝覆盖/设备占用，退出恢复临时 CCI PM 与主摄图案参数；不会安装或加载实验驱动。
- [离线 sensormodule 检查器](../../scripts/inspect-camera-sensormodule.py)：只接受本机观察到的 Parser V3.5.1，验证长度、CRC32、描述符和数据池边界；按声明位宽导出寄存器，不把小数值误写成 byte。未知表以未解码状态保留；不执行 I²C、不导出 EEPROM 分区。
- [sources.json](sources.json)：固定源码版本与保存文件 SHA-256。

统一脚本的参数为 `镜头 输出文件 [帧数 [图案]]`，镜头可选 `main`、`ultrawide`、`tele`、`front`。图案 0 为实拍；前摄/超广角 2 为色条，主摄非零值均选择本轮验证的色条；长焦只接受 0。不要循环调用。同日下午，最终模块及统一脚本按主摄→超广角→长焦各完成一次实拍（丢弃四帧、保存一帧），分别核对 15,064,064 / 15,679,488 / 7,490,880 字节及传输 SHA-256。拍摄和卸载恢复期间 boot ID 未改变，未发生重启；这不推翻此前的故障记录。前摄尚未用统一脚本重测。

外部传感器模块的离线构建示例（相机实验内核头文件、配置及 Module.symvers 必须已准备好）：

```sh
make -C /opt/negroni-build/linux/output ARCH=arm64 \
  CROSS_COMPILE=aarch64-linux-gnu- M="$PWD/artifacts/camera-20261114/drivers" modules
```

在本仓库的 WSL 构建树中，`make O=output M=drivers/media/platform/qcom/camss modules` 会把外部模块结果放进**源码的 CAMSS 目录**。此前 `output/drivers/.../qcom-camss.ko` 可以是旧文件，必须核对实际模块路径、字符串和 SHA-256，不能仅看 make 返回成功。

最终整理后的外部模块和 CAMSS 均以 `W=1` 交叉编译通过，overlay 预处理及 `dtc -@` 编译通过；补丁用独立临时 Git index 对上述干净基准执行 `git apply --cached --check` 通过，没有修改真实 index。`bash scripts/check.sh`（含五项合成 sensormodule 测试）、父仓库及内核的 `git diff --check` 均通过。编译和结构测试不能代表硬重启已修复。

结束检查：手机没有运行采集，额外传感器/overlay/PHY hold 模块均未加载，临时 `/lib/firmware/negroni-imx615-test.dtbo` 已清除，没有新增自动加载服务；当前安装的 CAMSS SHA-256 仍为 `0c78430b93a2e20b3fe9d1b0866e61ef214d9d2b07ca5e800b78a947090d3fd4`。CCI、CAMSS、CAMCC 的 `power/control` 均为 `auto`，systemd 状态为 `running`，B 槽 Active / Successful / Bootable 均为 1。手机 `~/camtest` 和电脑忽略的 `logs/` 保留调试材料。

不建议把这些实验模块默认启用或写入正式镜像。当前未完成：稳定启停、可靠帧率、主摄/长焦标准曝光与增益控制、AF/OIS、EEPROM/镜头阴影/色彩标定、自动曝光/白平衡、libcamera/ISP/相机应用、JPEG/录像、多摄同时运行、高分辨率/HDR、温控及全新镜像启动。
