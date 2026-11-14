# 实现与实机记录

这里保留已归档的调研和验证依据；可刷镜像与常规构建日志分别生成到本地 `images/` 和 `logs/`，不随 Git 分发。

| 目录 | 内容 |
| --- | --- |
| [haptics-20261114](haptics-20261114/README.md) | PM8350B 振动自动加载、标准反馈接口、首次锁问题修正及桌面接入验证 |
| [mic-clock-20261113](mic-clock-20261113/README.md) | 原厂 DMIC3/4 路由、共享时钟反汇编、VA/双通道状态修正与重启实测；麦克风仍无信号 |
| [charging-status-20260915](charging-status-20260915/README.md) | 电流符号修复及实机拔插验证 |
| [charge-limit-research-20260916](charge-limit-research-20260916/README.md) | 充电阈值方案、原厂源码与 ABI 依据 |
| [charge-limit-implementation](charge-limit-implementation/README.md) | 实现补丁、源码归档与本地验证说明 |
| [usb2-diagnosis-20260916-030952](usb2-diagnosis-20260916-030952/README.md) | USB2 Hub 断连、绑定关系与寄存器诊断 |
| [wake-latency-20260916](wake-latency-20260916/) | GPU 唤醒超时和 runtime PM 规避的采集记录 |
| [gpu-runtime-pm-20261111](gpu-runtime-pm-20261111/README.md) | 7.3 上 GPU runtime suspend / 亮屏重测，结论为样本不足、暂保留规避服务 |
| [cpu-performance-20260916](cpu-performance-20260916/README.md) | CPU Boost / 性能模式实测、硬件限频边界与已重启验证的大小核调度修复 |

这些文件反映采集时刻的设备状态，不能直接作为其他设备的配置。当前使用入口见[文档索引](../docs/README.md)。新增常规诊断输出应先放在 `logs/`，整理并去除个人信息后再考虑归档。
