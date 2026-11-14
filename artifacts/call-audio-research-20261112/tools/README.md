# 离线 ADSP F3 解码脚本

原始位置是本地 `logs/call-audio-20261112/vcpm-why/`，2026-11-15 从对话与文档引用中提炼。两个脚本只读用户明确给出的日志/固件文件，输出映射或解码文字，不连接手机，不修改 DSP，也不包含固件或日志。

```sh
python -I binhash.py map.json first.log,second.log public-adsp.mbn
python -I dec.py map.json first.log 1 300 'vcpm|SmartSync'
```

`binhash.py` 从输入二进制保留的 `file.c: ADSP: format` 字符串求 legacy QShrink 哈希：MD5 最后四字节、大端，能被 4 整除时加一；只保留日志实际用到的哈希。`dec.py` 按行号区间和可选正则替换整数/指针格式字段，用于核对 VCPM 状态机。它是调试辅助，并未实现完整 printf 格式化或消除哈希碰撞；仅凭替换出的文字不能推断固件版本完全匹配。

此前两份日志的 797 个哈希对上 793 个、VCPM 条目可读，这是原调试记录的结果，本轮没有重新采集。生成的映射、原始日志、固件以及可能出现的通话信息仍放在本地 `logs/`；分享结论前提炼必要片段。当前能力和失败过程见[音频](../../../docs/audio.md)。

`adsp-f3.c` 是当时有界、仅文字的采集变体，保留 GPL-2.0 与来源头；`adsp_diag.c` 是同目录保留的上游对照源码，来自 royka1/diting-ubuntu `c68ff47db94792fb5fd608e98d1ae489c2e592b1` 的 tools/diag/adsp_diag.c，许可证见 [COPYING](COPYING)。采集变体可用 `cc -O2 -Wall -Wextra adsp-f3.c -o adsp-f3` 构建，`--selftest` 只测试解包、不访问硬件；手机上 `--seconds 1..60` 才进行限时采集。程序需要访问 QRTR DIAG，不能与其它 DIAG 会话同时使用，不安装开机服务。本轮只编译与自检，没有启动实机采集。

归档时将 C 源文件换行统一为 LF、移除行尾空白，保留代码与来源声明；没有把原始诊断日志纳入文件。
