# SN100 读卡与被动监听实验

日期：2026-11-14。当前结论、安装和用法集中在 [NFC](../../docs/nfc.md)。这里保留调试源码和历史实验脚本；原始日志、编译出的 `.ko` 不入库。

| 文件 | 用途与边界 |
| --- | --- |
| `nfc-up.c` | NFC generic netlink 打开/关闭控制器 |
| `nfc-live.c` | 有时限的发现与标签监听；曾读取 Classic 卡 UID，尚无 Classic 扇区认证 |
| `nfc-sniff.c` | 有时限的原始 NCI 监听 |
| `nfc-emulate.c` | 主动请求 NFC-A 被动监听；控制器接受过配置，外部读卡器尚未验证 |
| `install.sh`、`load-test.sh`、`cycle.sh` | 当日模块安装、打开/关闭对照；使用手机上的临时文件，不能替代镜像安装器 |
| `list-clk.sh`、`probe-clk.sh`、`reload-clk.sh`、`show-clk.py` | 参考时钟计数、重载与寄存器对照 |
| `install-nci.sh`、`try-emulate.sh`、`try.sh`、`try2.sh` | 原始监听候选安装与运行顺序，保留当时的 `/tmp` 路径和本机 UID；执行前需核对当前内核、模块、UID 与参数 |

这些脚本没有接入默认构建、开机服务或自动执行。重载实验会打断 NFC，先结束正在进行的读卡/监听；安装前备份对应模块和 modprobe 配置，失败时恢复备份及原参数。不要使用它们重绑 USB 或重启手机。

正式构建由 `configure-nfc.sh` 交叉编译四个工具，安装时钟配置；内核固定点和 bundle 保留驱动。普通读卡按需调用。镜像不预置本机 UID，不自动模拟卡片或持续轮询。新镜像未构建、未刷入，Classic 扇区和门禁识别未测。
