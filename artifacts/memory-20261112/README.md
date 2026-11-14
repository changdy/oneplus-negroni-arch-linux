# 2026-11-12 内存容量只读核查

设备：OnePlus 10 Pro NE2210；内核：`7.3.0-sm8450+`；通道：USB 网络 SSH。用途：解释 12GB 机型为何 `free -h` 的 `total` 显示 `10Gi`。

以下是从实机输出整理的容量依据，不包含完整启动参数、设备序列号或网络信息。原始日志在本地忽略目录 `logs/memory-20261112/`。

## 当前统计

```text
device_info.ddr_info=1|12
MemTotal:       10802616 kB
CmaTotal:          32768 kB
free -b: total 11061878784 bytes
free -m: total 10549 MiB
free -h: total 10Gi
```

## 运行时内存区间

读取 `/sys/firmware/devicetree/base/memory@a0000000/reg`，按根节点的 2 个地址单元和 2 个长度单元解码。下表按起始地址排序，末地址为包含端点。

| 起始地址 | 末地址 | 容量（MiB） |
| --- | --- | ---: |
| `0x80000000` | `0xe9ffffff` | 1696 |
| `0xf1400000` | `0xffffffff` | 236 |
| `0x800000000` | `0x8398fffff` | 921 |
| `0x840000000` | `0x8ffffffff` | 3072 |
| `0x900000000` | `0xa7fffffff` | 6144 |
| 合计 | | **12069** |

12 GiB 减去这些区间合计为 219 MiB。未由本次核查确定这部分容量的具体固件用途。

## 主要固定预留

解析运行时 `/reserved-memory/*/reg`，再用运行时 `__symbols__` 解析标签。45 个区间共 1249771520 字节（1191.875 MiB），无重叠，全部位于上述内存区间内；均未标记 `reusable`，除 32 KiB 的 `bootloader_log_mem` 外均有 `no-map`。

| 标签 | 起始地址 | 容量（MiB） |
| --- | --- | ---: |
| `mte_mem` | `0xc0000000` | 512 |
| `mpss_mem` | `0x8bc00000` | 306 |
| `oem_vm_mem` | `0xbb000000` | 80 |
| `trust_ui_vm_mem` | `0xe0b00000` | 74.94921875 |
| `splash_memory` | `0xb8000000` | 43 |
| `adsp_mem` | `0x85700000` | 40 |
| `cdsp_mem` | `0x89900000` | 32 |
| `slpi_mem` | `0x87f00000` | 26 |
| `tags_mem` | `0xe8900000` | 18 |
| 其他固定预留 | 多个区间 | 59.92578125 |

源码交叉核对位置：WSL `/opt/negroni-build/linux/arch/arm64/boot/dts/qcom/sm8450.dtsi` 和同目录 `sm8450-oneplus-negroni.dts`。内存节点的源码占位大小由 bootloader 填充，因此总容量以运行时 `reg` 为准。`adsp_region@85e00000` 等节点名称未必等于真实地址，计算使用 `reg`。

## 当前启动的日志依据

```text
cma: Reserved 32 MiB at 0x00000000fe000000
Memory: 10743512K/12358656K available (14912K kernel code, 1806K rwdata, 6784K rodata, 1600K init, 529K bss, 1575688K reserved, 32768K cma-reserved)
Freeing initrd memory: 17988K
Freeing unused kernel memory: 1600K
```

启动时 `Memory:` 的分母 `12358656K` 等于运行时内存区间合计 12069 MiB；启动时可用量与当前 `MemTotal` 不是同一采样阶段，不能直接当作当前总量。当前其余开销以 `12069 − 1191.875 − 10549.4296875 = 327.6953125 MiB` 归集，不宣称已逐项归因。

验证范围和结论见 [内存说明](../../docs/memory.md)。物理内存压测、原厂系统对照以及预留区回收均未测。
