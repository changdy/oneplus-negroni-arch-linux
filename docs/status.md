# 设备状态与使用说明

源码与实机更新日期：2026-11-12（音频、基带、蓝牙、GPU、USB 调试）；完整 rootfs 构建日期为 2026-11-01，其他历史实机记录日期为 2026-09-16。已记录设备为 OnePlus 10 Pro NE2210，SoC 为 SM8450，GPU 为 Adreno 730。其他 NE221x 变体不视为已验证。

## 源码、镜像和实机

当前内核为 `7.3`，固定到 `ead3411b6e6f62525077342db179e0d29f354555`，包含电池、CPU、触觉驱动、USB/PD 和角色切换修复，历史未合并 `7.3-rc2`。ARM64 内核/模块/DTB 与主机回归通过。手机已通过 Wi-Fi SSH 更新启动内核、设备树、电池模块和 USB 网卡固件并重启验证，根文件系统沿用既有安装；这不代表 2026-11-01 的完整 rootfs 重新刷入。

带 PD 的 Hub 已验证 USB2 接收器、RTL8153 网卡和充电同时工作，重启后可自动枚举。物理热插拔仍出现过 SMMU `IOVA=0x0c` 与 xHCI 挂死，后续成功拔插不能证明故障消除。电脑端 gadget、无外接供电 OTG、其他 Hub、DP 显示与完整系统深度睡眠仍未覆盖。

2026-11-04 追加验证：已复现电源域关闭后恢复时的非法 DMA 和 USB 全部丢失，并在驱动中补齐 DWC3 到 xHCI 的状态丢失通知。相同诊断配置下，关闭通知的对比内核失败，启用通知后连续 3 次 `pm_test=platform` 均恢复接收器与网卡。这是设备/电源域挂起测试，不能代替真正的深度睡眠验证，也不能等同此前 `IOVA=0xc` 热插拔问题已解决。

手机现已切回包含修复的普通版内核 `7.3.0-sm8450+`，重启后接收器与网卡自动枚举，有线通信和启动成功标记通过；自动故障抓取及本次诊断组件已移除。

A 槽曾因缺少成功标记而耗尽重试次数、进入 recovery，现已恢复并验证重启。[启动成功服务](boot-success.md)已接入构建，需为每台设备确认固件历史和 Linux 槽位后配置。

- **源码与本地镜像**：充电限制、常用软件、GPU runtime PM 配置均已集成，完整构建与离线检查通过。
- **最近完整刷入的系统**：包含键盘修复和默认 SSH 的早期 7.3-rc2 镜像；SSH 已由用户确认默认生效。
- **随后单独部署的变更**：电池电流符号修复已通过充放电及拔插验证，GPU runtime PM 规避服务已部署并记录验证。
- **CPU 性能与调度**：2026-09-16 已在手机启用 Boost / performance，并更新 `vendor_boot_a` 的大小核能力及功耗模型。重启后 capacity 为 276 / 849 / 1024，性能服务自启动和负载迁移验证通过；硬件频率限制仍存在。两项现已集成到完整固件默认构建并默认启用，见 [复现指南](cpu-performance.md)和 [CPU 实测记录](../artifacts/cpu-performance-20260916/README.md)。
- **Docker 内核支持**：已补齐 nftables 兼容、NAT 和 IPv4/IPv6 FIB 配置，完成内核及固件重建、模块一致性与自动加载别名检查。手机此前的 IPv4 模块补装已验证 Docker 正常运行；本次新固件尚未刷入，冷启动和 IPv6 容器网络待验证，见 [Docker 说明](docker.md)。
- **尚未完成**：全新完整 rootfs 的安装验证、最新常用软件逐项验证、USB 偶发热插拔故障的根因定位及上述未覆盖的连接场景。

## SSH

> **调试首选 USB 网络 SSH**：手机接电脑 USB3 口，电脑 NCM 网卡设为 `10.55.0.2/24` 后执行 `ssh oneplus@10.55.0.1`，另有 `COM3` 串口救援。该通道已在本机手动安装，尚未进入镜像构建，见 [USB 调试通道](usb-debug.md)。

镜像默认启用 OpenSSH，TCP 端口为 22。手机连接 Wi-Fi 后，在同一局域网电脑执行：

```sh
ssh oneplus@手机IP
```

密码为构建时本地 `image-credentials.json` 中的 `password`；也支持为 `oneplus` 配置 SSH 公钥。root 远程登录和空密码登录被禁用，主机密钥在首次启动时生成。镜像未预置 Wi-Fi 凭据；全新镜像的 USB 数据线也还不会自动提供 SSH 网络，需按 [USB 调试通道](usb-debug.md) 补装。

## 已知问题与配置取舍

| 项目 | 状态与依据 |
| --- | --- |
| 登录虚拟键盘 | 使用 KWin 启动 Plasma Keyboard；7.2 已确认可输入，7.3-rc2 登录操作尚待单独记录，见[修复记录](archive/keyboard-fix-2026-09-15.md) |
| GPU 慢亮屏 | 默认启用 `gpu-runtime-active.service`，将 GPU 的 `power/control` 设为 `on`；这是阻止 GPU runtime suspend 的规避方式，可能增加待机耗电。2026-11-11 在 7.3 上设为 `auto` 的 2 次亮屏未复现 1 s 超时，样本不足，暂不移除，见 [GPU 说明](gpu.md) |
| GPU 3D 加速 | 详见 [GPU 说明](gpu.md)。2026-11-11 实机验证可用，内核与固件无需修改：msm/Adreno 730 绑定，`a730_sqe.fw`、`gmu_gen70000.bin` 和 zap shader 正常加载（0.8 秒时 `failed to load a730_sqe.fw` 仅是 rootfs 挂载前的首次尝试，12 秒时加载成功）。Mesa 26.2.6 的 GL ES 3.2 渲染器为 `FD730`，KWin 使用 OpenGL ES 合成，Xwayland GLX 为直接渲染；`glmark2-es2-wayland --off-screen`（1245×2664，build/texture/phong/refract/terrain）得分 900，压测中 devfreq 由 220 MHz 升至 818 MHz，无 GPU fault 或 hangcheck。Vulkan 需安装 `vulkan-freedreno`（已加入镜像软件清单），Turnip 报告 Vulkan 1.4，`vkcube` 300 帧正常；游戏、视频硬解和长时间负载的温控尚未测试 |
| 触摸 DMA 报错与登录界面消失 | 已修复 I²C 读操作的 TX 环泄漏；实机相同 256 次读取由 8 次 EIO 降为零错误。登录前关闭概览等手势效果；首次界面退出的直接原因仍待进一步定位 |
| 电池状态图标 | 已修正电流符号及 Oplus 充电状态计算；最终模块已实测 5 V Hub 下充电、限充停止与解除恢复，内核与 UPower 状态正确、外设在线，见[充电说明](charge-limit.md) |
| 充电限制 | 镜像默认关闭；本机已启用 75/80%，PD Hub 下 holding/解除与保留外设已验证，启用后阻止挂起/休眠，见[使用说明](charge-limit.md) |
| USB2 / OTG | 已补齐 PHY/时钟、PD、角色切换及失电后的 xHCI 重建；带 PD 的 Hub 可用，偶发热插拔挂死尚未确认解决 |
| A/B 槽启动 | 已修复本机成功位并验证重启；自动标记需设备本地确认固件历史及 Linux 槽位，见[启动成功服务](boot-success.md) |
| 无 SIM 卡启动 | 默认允许无卡使用，SIM 初始化打印“无卡，跳过配置”并成功退出；基带和 QMI 故障仍报告失败，见[构建集成说明](build-integration.md) |
| 基带启动 | 已修复 QRTR 握手竞争导致的约 40 秒看门狗循环崩溃；2026-11-11 实机验证基带不再崩溃，无卡时手动上线可测到 LTE 信号。IMEI 读取为 `unknown` 待查，见 [基带说明](modem.md) |
| SIM、移动数据、VoLTE | 2026-11-12 实机（电信卡）：开机选卡与热插处理、注册、IPv4/IPv6 移动数据可用；VoLTE 拨出可到接通状态但无通话声音，关闭移动数据后 ModemManager 常段错误并约 20 秒自恢复，来电与短信未测，见 [基带说明](modem.md) |
| 蓝牙 | 2026-11-12 实机：自动设置 public address 后适配器开启、扫描正常且 Wi-Fi 稳定；完整重启、配对与 A2DP 未测，见 [蓝牙说明](bluetooth.md) |
| USB 调试 gadget | USB3 口 NCM SSH 与 ACM 串口可用；USB2 口约 3 秒后掉线，LPM 补丁已准备未刷入，见 [USB 调试通道](usb-debug.md) |
| 根分区定位 | 改用文件系统 UUID，实机连续 3 次重启通过；原失败启动的早期日志缺失，UFS 偶发初始化问题仍未排除。单独更新 boot 须使用手机当前根 UUID，见[刷机说明](flashing.md) |
| 音频 | 2026-11-12 实机：刷入路由修正后声卡可用，PipeWire 识别扬声器、耳机、内置/耳机麦克风；扬声器出声已由用户确认，内置麦克风录音已验证，耳机出声与插拔待确认，见[音频说明](audio.md) |
| 相机、GPS | 尚无本机恢复可用的证据。S5KJN1 超广角探测失败（驱动要求 24 MHz MCLK、reset 应为 gpio24 低有效），DT 修正只在 WSL 内核树中，未提交、未验证 |
| 显示、触摸、Wi-Fi | 仍需对当前完整镜像逐项记录，已有桌面或 SSH 使用记录不能替代完整兼容性测试 |

SDDM 默认使用 Plasma Mobile、Wayland 与 Breeze；镜像语言为 `en_US.UTF-8`，时区为 `Asia/Shanghai`。配置来源见 [config/sddm/10-mobile.conf](../config/sddm/10-mobile.conf)、[SSH 配置](../config/ssh/00-negroni.conf)和[软件清单](../config/packages/common-tools.txt)。

报告问题时请附设备型号、固件升级历史、父仓库与内核提交、复现步骤和相关日志，说明运行的是哪次镜像；详见[贡献指南](../CONTRIBUTING.md)。
