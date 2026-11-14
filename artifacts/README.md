# 实现与实机记录

这里保留已归档的调研和验证依据；可刷镜像与常规构建日志分别生成到本地 `images/` 和 `logs/`，不随 Git 分发。

| 目录 | 内容 |
| --- | --- |
| [camera-20261114](camera-20261114/README.md) | 四摄 RAW、C-PHY、CSID 停流修复与有限次数启停验证；长期与功耗仍未测 |
| [haptics-20261114](haptics-20261114/README.md) | PM8350B 振动自动加载、标准反馈接口、首次锁问题修正及桌面接入验证 |
| [mic-clock-20261113](mic-clock-20261113/README.md) | 原厂 DMIC3/4 路由、共享时钟反汇编、VA/双通道状态修正；2026-11-14 傍晚去掉复位脚 sleep 状态后 ALSA 录音恢复，内核提交 `67d9e35c9ac0` |
| [stock-hardware-20261113](stock-hardware-20261113/README.md) | 本机原厂版本、驱动模块与相机/音频/显示资料的只读核查 |
| [charging-status-20260915](charging-status-20260915/README.md) | 电流符号修复及实机拔插验证 |
| [charge-limit-research-20260916](charge-limit-research-20260916/README.md) | 充电阈值方案、原厂源码与 ABI 依据 |
| [charge-limit-implementation](charge-limit-implementation/README.md) | 实现补丁、源码归档与本地验证说明 |
| [usb2-diagnosis-20260916-030952](usb2-diagnosis-20260916-030952/README.md) | USB2 Hub 断连、绑定关系与寄存器诊断 |
| [wake-latency-20260916](wake-latency-20260916/) | GPU 唤醒超时和 runtime PM 规避的采集记录 |
| [gpu-runtime-pm-20261111](gpu-runtime-pm-20261111/README.md) | 7.3 上 GPU runtime suspend / 亮屏重测，结论为样本不足、暂保留规避服务 |
| [cpu-performance-20260916](cpu-performance-20260916/README.md) | CPU Boost / 性能模式实测、硬件限频边界与已重启验证的大小核调度修复 |

## 其它已保留资料

| 目录 | 内容 |
| --- | --- |
| [browser-20261112](browser-20261112/README.md) | Angelfish 安装与验证记录 |
| [call-audio-research-20261112](call-audio-research-20261112/README.md) | OnePlus Negroni 通话音频研究依据（2026-11-12） |
| [camera-20261113](camera-20261113/README.md) | S5KJN1 实机依据（2026-11-13） |
| [camera-colour-20261113](camera-colour-20261113/README.md) | 相机预览偏色核查（2026-11-13） |
| [camera-source-20261113](camera-source-20261113/README.md) | 一加官方相机源码核查（2026-11-13） |
| [display-resolution-20261112](display-resolution-20261112/README.md) | 内屏原生分辨率与当前 Linux 模式核查 |
| [fonts-20261112](fonts-20261112/) | 整理后的验证与参考资料；当前结论见对应硬件文档 |
| [gnss-20261112](gnss-20261112/README.md) | NE2210 GNSS：2026-11-12 |
| [gnss-20261113](gnss-20261113/README.md) | NE2210 GNSS：卫星接收与 XTRA 辅助 |
| [memory-20261112](memory-20261112/README.md) | 2026-11-12 内存容量只读核查 |
| [nfc-20261114](nfc-20261114/README.md) | SN100 读卡与被动监听实验 |
| [project-audit-20261115](project-audit-20261115/README.md) | 跨对话成果核对 |
| [stock-driver-diff-20261113](stock-driver-diff-20261113/README.md) | 原厂驱动归档 vs 当前项目驱动：逐子系统差异核对 |
| [usb-disconnect-20261113](usb-disconnect-20261113/README.md) | USB SSH 意外断连只读排查（2026-11-13） |
| [usb2-gadget-20261113](usb2-gadget-20261113/README.md) | USB2 gadget：充电检测 datapath override 残留 |

这些文件反映采集时刻的设备状态，不能直接作为其他设备的配置。当前使用入口见[文档索引](../docs/README.md)。新增常规诊断输出应先放在 `logs/`，整理并去除个人信息后再考虑归档。
