# 本机原厂驱动资料核查（2026-11-13）

本轮通过 SSH 只读核查 NE2210 的运行状态和保留分区，未刷写、重启、切槽、修改 USB role 或重绑 UDC。结论、版本边界和后续使用方法见[原厂硬件资料说明](../../docs/stock-hardware.md)。

[evidence.json](evidence.json) 保存去除个人信息后的文件路径、大小和 SHA-256、373 个模块的计数及部分编译元数据、量产 DTBO 选择条件、8 个面板模式和当前设备绑定状态。它不包含原厂固件、模块、tuning、DNG 矩阵或校准负载。

## 提取与交叉检查

1. `lpdump` 分别读取 super 的 slot 0 / 1 元数据。super 大小 11,274,289,152 字节，包含 Virtual A/B COW 条目；本轮没有进行快照合并。
2. 使用 `lpunpack --slot=1 -p vendor_dlkm_b` 等命令提取所选逻辑分区，再用 `debugfs` 读取 ext4、`fsck.erofs --extract` 读取 my_manifest EROFS。手机 lpunpack 的 `-S` 短选项虽然写在帮助中，实际拒绝；长选项成功。debugfs 对 EROFS 会报 bad magic，不能只凭退出码判定解包成功。
3. 对 `dtbo_a`、`vendor_boot_a` 只读取镜像有效长度，按 DT table 和 vendor boot v4 头计算边界；记录的哈希针对提取内容，**不是完整分区的备份哈希**。DTBO 有 12 项，vendor boot 含 4 个基础 DTB；未调用 bootloader，也未改变 A 槽不可启动状态。
4. 本地镜像 SHA-256 与手机提取时记录一致；vendor_dlkm 在手机和电脑分别解包，均为 373 个 `.ko`。JN1 选定文件另核对手机与本地 SHA-256。
5. Python 解析 DTBO 得到面板与相机属性，另以 `dtc -I dtb -O dts` 反编译量产候选 0 / 11，检查宽高、DSC 分块和项目选择条件。`readelf` 读取模块元数据及符号，AArch64 objdump 生成 JN1 传感器库反汇编；这些均为静态分析，未执行原厂二进制。

原始命令、JSON 清单、DTS、ELF 分析和二进制来源存于忽略的 `logs/stock-hardware-20261113/`。除下述用户明确授权的模块副本外，只复制整理后的依据，不将镜像、设备校准或私人场景 RAW 纳入 Git。

用户随后要求将全部模块集中放到工作区，并明确授权纳入 Git、commit 和 push。归档为 `downloads/stock-drivers-20261113/vendor_dlkm_b/`：373 个 `.ko`，含配套清单与元数据共 382 个文件、152.88 MiB。所有文件均与手机提取目录逐个核对大小和 SHA-256，另附 CSV / JSON 清单与 `SHA256SUMS`。此归档是下载忽略规则的精确例外，原厂文件以 binary 属性保留；来源文件保持原样。

## 主要新增依据

- `my_manifest_b/build.prop` 明确记录 `NE2210_15.0.0.401(CN01)`，避免被 vendor 的 Android 12 平台字段误导。
- 原厂 JN1 的 sensormodule、tuning、传感器 ELF 和两份 DNG ColorMatrix 均存在；格式/方向、完整调校结构与当前模式适用性尚未全部解码或验证。
- 原厂量产面板的 WQHD 模式使用 720×24 DSC slice，FHD 使用 540×36；两组均保留 60 / 90 / 120 Hz 条目。
- LPASS 模块保留共享 DMIC 时钟使能函数符号及 TX macro 引用，可继续对照当前无麦克风时钟的问题。

原厂 Android 启动、各镜头功能、颜色准确度、WQHD 切换及麦克风修复均**未测**。本轮发现不能作为完整 Android 恢复包或硬件自检通过的证明。

验证：6 个相机文件与 5 个提取镜像的手机/本地 SHA-256 一致；两端模块计数一致；文档相对链接、`bash scripts/check.sh` 和 `git diff --check` 通过。没有改动主线驱动或部署新镜像。
