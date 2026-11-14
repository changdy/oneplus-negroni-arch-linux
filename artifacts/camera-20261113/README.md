# S5KJN1 实机依据（2026-11-13）

结论：NE2210 超广角已经取得并解码真实场景 RAW；重复 STREAMON 仍会导致整机硬重启，未达到日常使用条件。详见 [相机说明](../../docs/camera.md)。

## 源码与部署

- 内核基准：`ead3411b6e6f62525077342db179e0d29f354555`，WSL `/opt/negroni-build/linux`。
- [camera-bringup.patch](camera-bringup.patch)：相机 DT、SM8450 gen2 PHY、CAMCC 状态保持与 RCG、连续 DMA 修改；未包含音频 hunk。尚未提交到内核，gitlink / bundle 尚未更新。
- 运行内核：`7.3.0-sm8450+ #3`，构建时间 2026-11-13 09:32:43 CST。
- 测试 boot：`8030cb0e2fc81c01a3dbeaf1f7f6d200b2ec4f9c2563a0503b9765435cd87f4b`。
- 最初 gen2 模块：`5daf7b1756806ecaac2a57fd126b775da2d99db2b6f7bd65de51e19c166253fa`。
- 最后部署的连续 DMA 模块：`0c78430b93a2e20b3fe9d1b0866e61ef214d9d2b07ca5e800b78a947090d3fd4`；已确认依赖 `videobuf2-dma-contig`。
- 保留手机当前 initramfs 和启动参数；本轮没有更新 `vendor_boot_b`。实际 DT 中 MCLK 为 `0x16e3600`（24 MHz），reset 为 GPIO `0x18`、低有效。

上游来源保留原作者和许可：Sushmit Singh Rathore 的 [GDSC 补丁](https://lore.landau.one/lkml/20261020142157.1749-3-sushmit718@gmail.com/)、[RCG 补丁](https://lore.landau.one/lkml/20261020142157.1749-4-sushmit718@gmail.com/)；Loic Poulain 的 [连续 DMA 补丁](https://lore.landau.one/lkml/20261111135338.27008-2-allan@fatecpompeia.edu.br/)（由 Allan Siriani 发送）。DMA 补丁的 Kconfig 上下文与本树不同，仅手工替换同一条 `select`，其余 hunk 原样应用。

## 可复核结果

| 项目 | 整理结果 |
| --- | --- |
| 原版 CAMSS | STREAMON 返回成功，8 秒无帧，输出 0 字节 |
| gen2 PHY + 新 CAMCC | 色条和实拍均有完整帧，约 30 fps |
| 格式 | 4080×3072，`pgAA` / `SGRBG10_1X10`，stride 5104，单帧 15,679,488 字节 |
| 测试色条 | 两帧，0–1023，均值 511.5，标准差 511.5；解码为标准八色竖条 |
| 镜头无遮挡实拍 | 三帧；第一帧均值 76.187、标准差 78.972、最大 1023；能辨认天花板与灯具 |
| 调整曝光/增益 | 曝光 3840、增益 16 的三帧；第一帧均值 125.345、标准差 109.713，场景细节增多 |
| 重开 | 两轮各 180 帧通过；后续启动硬重启 |
| 保持电源/阻止睡眠对照 | 两轮各 60 帧通过，下一轮仍硬重启 |
| 连续 DMA 对照 | 两轮各 30 帧通过，下一轮仍硬重启；并未证实 DMA 分段是根因 |
| 通用采集脚本 | 已在真机保存一帧，并核对长度；连续 DMA 下前两轮各 30 帧通过 |

原始记录保存在未跟踪的 `logs/camera-20261113/`：`capture-baseline.txt`、`capture-bars-newboot.txt`、`capture-real-bright.txt`、`capture-real-exposed.txt`、`reload-test.txt`、`normal-reopen.txt`、`powerheld-test.txt`、`contig-reopen.txt`、`kmsg-live.txt`、`build.json`。时钟在手机启动后曾从 1970 年校正到当前日期，排查顺序同时依据 boot ID 与 V4L2 单调时间戳。

实拍含私人环境，只保留在本地，不随本目录提交。这里的统计按 RAW10 解包后计算；预览采用 GRBG 每 2×2 像素合成 RGB、黑电平 64、gamma 2.2，没有执行白平衡和标定。

## 离线检查与未测范围

ARM64 `Image.gz`、CAMSS 模块、Negroni DTB 编译通过；重封装 boot 后核对 initramfs 完全一致，header 除 kernel size 外一致，内核与当前根 UUID 正确。最后的 DMA 模块由内核配置作为外部模块编译，已确认正确符号依赖并成功加载。`bash scripts/check.sh` 通过；父仓库和 WSL 内核 `git diff --check` 通过。

50 MP 模式、相机应用、ISP、自动曝光/白平衡、其他镜头和长时间稳定性未测。重复开启已实测失败，不能用这些离线检查代替稳定性结论。
