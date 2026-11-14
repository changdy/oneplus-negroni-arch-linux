# 来源与许可

本仓库尚未为自行编写的构建脚本与文档声明统一许可证。不能仅因仓库公开就假定所有文件使用 MIT、GPL 或其他统一许可；需要复用没有许可声明的文件时，应先与维护者确认。

已有许可声明、版权头和上游来源应随文件保留，各组件分别遵循其许可：

| 内容 | 许可依据与来源 |
| --- | --- |
| Linux 子模块与内核补丁 | [Linux 子模块](../linux)中的 `COPYING`、`LICENSES/` 和每个文件的 SPDX 声明 |
| `patches/linux/local-7.3.bundle`、`local-7.3-rc2.bundle` | 保存内核 Git 提交，导入后保留原有版权和 SPDX 信息；见[提交说明](../patches/linux/README.md) |
| AVB 工具 | [AVB 子模块](../tools/avb)中的 `LICENSE` 和各组件许可声明 |
| 固件加载工具 | [msm-firmware-loader 子模块](../tools/msm-firmware-loader)中的 `LICENSE` |
| 调研目录中的上游源码快照 | 各源文件许可头，以及对应报告和 `sources.json` 的来源记录 |
| [NE2210 原厂模块归档](../downloads/stock-drivers-20261113/README.md) | 从本机 `vendor_dlkm_b` 提取，保留各模块内嵌 license / scmversion、原厂 NOTICE 和逐文件 SHA-256；不另行赋予统一许可证，不包含分区镜像或校准负载 |
| 实验通话图生成器、PCM 测试顺序 | [diting-ubuntu 固定提交](https://github.com/royka1/diting-ubuntu/tree/c68ff47db94792fb5fd608e98d1ae489c2e592b1) 的 GPL-2.0 代码；改动文件保留 SPDX 与来源。原厂 ACDB、提取校准与生成拓扑仅本地使用，不纳入 Git，见[通话语音](call-audio.md) |
| 镜像中的 Arch/XEC 软件与设备固件 | 各软件包自己的许可证和分发条款；不因本仓库的说明而改变 |
| GNSS 用户空间补丁 | libqmi 上游补丁原样保留作者与来源；ModemManager 补丁作用于 GPL-2.0-or-later 的 daemon。版本与分组件许可见 [sources.txt](../config/gnss/sources.txt)，不包含原厂固件 |
| GNSS 已验证运行文件 | [runtime](../config/gnss/runtime/README.md) 保留固定源码/补丁、原始及交付哈希和 GPL/LGPL 许可证副本；仅移除 ELF 调试节，不含原厂固件或设备数据 |
| ADSP F3 诊断源码 | [tools](../artifacts/call-audio-research-20261112/tools/README.md) 中保留 GPL-2.0 来源头、原始对照及 COPYING；固件、日志和生成映射不随工具提交 |
| Sunshine 按需安装 | 固定官方 AppImage 地址和哈希，脚本下载时保留包内许可；本仓库不归档该 AppImage。版本、RUNPATH 改动和使用边界见[可选应用](optional-apps.md) |

添加新文件时应明确来源；修改上游代码时保留其许可。发布镜像时应同时保留对应源码版本、改动和包清单，以便追溯。
