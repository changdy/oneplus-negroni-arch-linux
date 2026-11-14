# 内存容量与预留

2026-11-12 通过 USB SSH 对 OnePlus 10 Pro NE2210、运行内核 `7.3.0-sm8450+` 做了只读核查。启动参数 `device_info.ddr_info=1|12` 报告 12GB 版本；当前 `MemTotal` 为 `10802616 kB`，即 **10.3022 GiB**。`free -h` 显示为 `10Gi`，`free -m` 显示为 `10549` MiB。

`free` 的 `total` 来自 `/proc/meminfo` 的 `MemTotal`，表示 Linux 可管理的容量，已经扣除了固件/硬件预留和部分内核开销，不是芯片标称容量，见 [free(1)](https://man7.org/linux/man-pages/man1/free.1.html) 和 [内核内存统计说明](https://docs.kernel.org/filesystems/proc.html)。

## 本机容量核算

按 12 GiB（12288 MiB）计算，运行时设备树和内存统计的差额如下：

| 项目 | 容量（MiB） | 依据 |
| --- | ---: | --- |
| 12 GiB 标称容量 | 12288 | 启动参数报告 12GB 版本 |
| 未列入运行时 `/memory/reg` 的容量 | −219 | `/memory/reg` 的全部区间合计 12069 MiB；这 219 MiB 的具体用途未逐项确认 |
| `/reserved-memory` 固定预留 | −1191.875 | 45 个 `reg` 区间，无重叠，均位于上述内存区间内 |
| 内核常驻、页元数据等其余开销 | −327.6953125 | 按差额归集，未逐项拆分 |
| 当前 `MemTotal` | **10549.4296875** | `10802616 × 1024` 字节，即 **10.3021774291992 GiB** |

固定预留中，较大的区域包括 `mte_mem` 512 MiB、基带 `mpss_mem` 306 MiB、`oem_vm_mem` 80 MiB、`trust_ui_vm_mem` 约 74.95 MiB、ADSP/CDSP/SLPI 合计 98 MiB，以及启动画面 `splash_memory` 43 MiB。这些区域的地址和标签均由运行时设备树确认；标签本身不证明某个区域当前未被固件使用。

因此，`free -h` 的 `10Gi` 符合当前固件和设备树配置。普通程序和文件缓存的占用会反映到 `used`、`free`、`available`，不是这里从 12 GiB 到 `MemTotal` 的固定差额。采集时 `available` 约 7.9 GiB。

## 验证范围

已读取 `free -b/-m/-h`、`/proc/meminfo`、当前启动内核日志，以及 `/sys/firmware/devicetree/base` 中的内存区间、预留区域和符号标签，并对照 WSL 内核树中的 `sm8450.dtsi` 与 `sm8450-oneplus-negroni.dts`。普通用户读取 `/proc/iomem` 时地址被隐藏为零，因此容量核算使用运行时设备树。

本次没有改动手机配置、内核或设备树，没有刷分区或重启。物理内存完整性压测、原厂 Android 的容量对照、任何预留区释放后的运行情况均**未测**；现有证据不能判断哪些预留可以安全回收。

整理后的区间与启动日志依据见 [实机核查记录](../artifacts/memory-20261112/README.md)。原始输出仅保存在本地忽略目录 `logs/memory-20261112/`。
