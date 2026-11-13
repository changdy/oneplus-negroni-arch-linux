# NE2210 原厂驱动模块参考归档

整理日期：2026-11-13。来自本机 super slot 1 的 vendor_dlkm_b；同槽 my_manifest_b 记录版本 NE2210_15.0.0.401(CN01)。原厂模块面向 Android 5.10 内核，当前手机运行主线 7.3。

- 完整分区文件树：`vendor_dlkm_b/`。
- 驱动模块：`vendor_dlkm_b/lib/modules/`，共 **373 个 .ko**。
- 包含原厂 `modules.load`、`modules.dep`、`modules.alias`、`modules.softdep`、`modules.symbols` 与分区构建属性、NOTICE。
- 共 382 个原厂文件，合计 160,304,370 字节（152.88 MiB）；全部与手机上提取目录逐文件核对大小和 SHA-256，再核对工作区复制结果。
- `inventory.csv` / `inventory.json`：完整路径、大小、SHA-256 与来源记录。
- `SHA256SUMS`：可在本目录执行 `sha256sum -c SHA256SUMS` 核对。

本目录用于离线查符号、反汇编和对照驱动逻辑，没有部署到当前 Linux。Windows 文件树仅用于保留文件内容和路径，不能代替保留 Linux 权限与扩展属性的可刷镜像。

用户于 2026-11-13 明确授权将这批模块纳入 Git 并推送。本目录是 `downloads/` 忽略规则的精确例外；原厂文件树设置为 Git binary 属性，保证检出后仍与 SHA-256 清单逐字节一致。手机和本地日志中的来源文件保持原样，分区镜像、固件和校准负载不包含在本归档中。

来源镜像 `vendor_dlkm_b.img` 的 SHA-256：`7102fd102ac39c470335896185e2d7443e9e2d4bb508887f7f7057bb15abaedb`。这是从 super 提取的逻辑分区镜像，不是整个 super 分区的备份。

已检查的原厂 LPASS 模块 vermagic 为 `5.10.209-gki-gac3f956b8fca`。整机 manifest 版本不能证明所有模块与某个公开源码提交精确一致；本归档未逐一验证硬件功能，也未尝试在主线 7.3 上加载这些模块。

模块内嵌的 license / scmversion 和原厂 `etc/NOTICE.xml.gz` 按原样保留，不能将它们统一改标为仓库其他组件的许可证。
