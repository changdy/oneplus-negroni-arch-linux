# 文档索引

首次使用请按“构建 → 核对设备条件 → 刷入”的顺序阅读。所有当前指南中的命令均从项目根目录执行，明确标为“手机上执行”的除外。

## 使用与开发

| 文档 | 内容 |
| --- | --- |
| [构建指南](building.md) | 主机依赖、子模块、rootfs 输入、凭据和续建 |
| [刷机说明](flashing.md) | 固件限制、分区映射、校验、刷入和首次启动 |
| **[USB 调试通道](usb-debug.md)** | **不依赖 Wi-Fi 的 USB 网络 SSH（`ssh oneplus@10.55.0.1`）与 USB 串口；调试首选** |
| [设备状态](status.md) | 已验证功能、已知问题、SSH 和 GPU 配置 |
| [原厂系统与硬件资料](stock-hardware.md) | 本机保留的原厂分区、373 个模块、JN1 调校与 WQHD 面板参数 |
| [启动成功服务](boot-success.md) | A/B 成功标记、设备确认配置及状态检查 |
| [充电限制](charge-limit.md) | 默认行为、启停、阈值配置及验证范围 |
| [屏幕默认设置](screen-defaults.md) | 默认关闭调暗和休眠、5 分钟熄屏及续建更新 |
| [Wi-Fi 默认设置](wifi.md) | 关闭省电、固定本地 MAC、CN 国家域与已知限制 |
| [音频](audio.md) | 扬声器、麦克风、耳机的诊断、拓扑/UCM/DT 修改；扬声器已实机验证，2026-11-14 傍晚内置麦克风 ALSA 录音恢复，内核提交 `67d9e35c9ac0` 尚未重新构建镜像 |
| [基带与 VoLTE](modem.md) | QRTR 看门狗崩溃修复、SIM 选卡与热插、移动数据、VoLTE 拨号与限制 |
| [GPS / GNSS](gnss.md) | 引擎锁、AFW 注册、新 XTRA 辅助接口与真实卫星接收验证边界 |
| [通话语音](call-audio.md) | VoLTE 通话下行、通话录音与向对方放音（实验）、自动开关服务、已知问题与排查方法 |
| [蓝牙](bluetooth.md) | WCN6855 缺少 public address 的修复与验证范围 |
| [NFC](nfc.md) | SN100 重复打开、19.2 MHz 参考时钟与 RF 发现；标签 UID 未测 |
| [振动反馈](haptics.md) | PM8350B 自动加载、标准 FF 接口、feedbackd / Plasma 接入与实机验证边界 |
| [传感器](sensors.md) | SLPI 加速度计驱动自动旋转；X/Y 取反后方向已由用户确认。TCS3701 露出时约 300 lux、FAR，遮严后 0–1 lux、NEAR；共享内存重启后会丢失 |
| [GPU](gpu.md) | Adreno 730 3D/Vulkan 实测、runtime PM 与慢亮屏规避 |
| [相机](camera.md) | 四摄 RAW 与主摄 C-PHY 实验移植；CSID 停流修正后 58 次启停通过，尚未进镜像 |
| [CPU 性能与调度](cpu-performance.md) | Boost / performance 服务、设备树构建、部署验证与恢复 |
| [Docker 内核支持](docker.md) | Docker 安装、网络模块配置、续建和镜像验证 |
| [构建集成说明](build-integration.md) | 各配置如何进入 rootfs，已有镜像如何更新 |
| [贡献指南](../CONTRIBUTING.md) | 开发检查、问题报告与 Pull Request |
| [AI 代理指南](../AGENTS.md) | 给 AI 代理的调试入口、手机操作安全规则与构建环境说明 |
| [来源与许可](licensing.md) | 子模块、补丁及第三方资料的许可边界 |

## 调研与历史记录

| 资料 | 内容 |
| --- | --- |
| [内核分支比较](../analysis/kernel-branches.md) | 7.2、7.3-rc2、master 的源码差异与判断依据 |
| [Docker 固件集成调研](docker-firmware-plan.md) | 实施前的根因和路径比较；已落实为 Docker 内核支持 |
| [实机与实现记录索引](../artifacts/README.md) | 充电、USB2、GPU 唤醒及 CPU 性能与调度实测资料 |
| [2026-09-16 构建记录](archive/build-notes-2026-09-16.md) | 整理前的完整 README，含历史版本、命令和产物哈希 |
| [2026-09-15 键盘修复](archive/keyboard-fix-2026-09-15.md) | SDDM 故障原因、临时修复过程及验证 |
| [2026-09-16 工作区迁移](archive/workspace-migration-2026-09-16.md) | 本地工作区迁移与缓存情况 |
| [内核提交恢复](../patches/linux/README.md) | Git bundle 的前置提交与恢复方法 |

归档按记录日期解释，不代表当前构建结果。历史记录提到的 `logs/`、`images/`、`downloads/`、登录凭据和部分临时修复文件只在原构建环境中存在，以代码路径标注，不提供 GitHub 下载链接。
