# 已验证的 GNSS 用户空间运行文件

2026-11-17：`ModemManager` 已在手机重编译，加入 QRTR 唤醒重枚举、netlink 事务生命周期与承载计数修复。当前文件及补丁见 [sources.txt](../sources.txt) 和 [SHA256SUMS](SHA256SUMS)；下方原始哈希仅描述此前版本。新完整镜像尚未构建或刷入。

2026-11-15 通过 USB SSH 只读取回 NE2210 正在使用的 ModemManager 和 libqmi。原文件 SHA-256 与 [sources.txt](../sources.txt) 的 2026-11-12 部署记录一致；没有重新编译、改手机配置或启动新的定位会话。

| 文件 | 原始部署 SHA-256 |
| --- | --- |
| ModemManager | `e3904776942e8a18a4dbd1ecc8f4934369d2d2c44d5a0e96423b0fafc704a149` |
| libqmi-glib.so.5.12.0 | `408dc26901dac775e866d27c687c8029a461aa4ca5e009b5b20fc2d723d6a355` |

入库前仅用 `aarch64-linux-gnu-strip --strip-debug` 移除调试节，保留 ARM64 运行代码与动态链接信息；文件合计约 7.8 MiB。入库版本、许可证副本的校验值在 [SHA256SUMS](SHA256SUMS)。运行文件不含 SIM 数据、位置、凭据、设备校准或原厂固件。

对应源码固定为 libqmi `e3d79ed3f7fdc6a7fa8b374860b1c23a8f172812`、ModemManager `f2b9ab1ad78d322f32134a444b5b54c6e8160e19`，补丁和本机构建方法在 [GNSS 配置目录](../sources.txt)及 [build-gnss-stack.sh](../../../scripts/build-gnss-stack.sh)。许可证从同一构建目录复制：ModemManager 为 GPL-2.0-or-later，libqmi library 为 LGPL-2.1-or-later；保留 [COPYING](COPYING) 与 [COPYING.LIB](COPYING.LIB)。重建后应重新核对 ABI、更新清单与来源记录。

镜像安装在 `/opt/negroni-gnss`，发行版的程序和库保留，只有 ModemManager 服务通过 drop-in 使用这份修复。清引擎锁随服务启动，搜星和辅助数据下载均按需。停用 drop-in 和 unlock 服务后可恢复发行版路径，详见 [GNSS](../../../docs/gnss.md)。引擎能启停与收到卫星不代表已获得坐标；新完整镜像启动与定位均未测。
