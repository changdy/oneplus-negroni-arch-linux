# GPU（Adreno 730）

状态日期：2026-11-17。

## 3D 加速：可用（2026-11-11 实机）

内核和固件都不需要修改：

- msm / Adreno 730 正常绑定，`a730_sqe.fw`、`gmu_gen70000.bin` 和 zap shader 都能加载。启动 0.8 秒时的 `failed to load a730_sqe.fw` 只是 rootfs 挂载前的第一次尝试，12 秒时会加载成功。
- Mesa 26.2.6：GL ES 3.2，渲染器为 `FD730`。KWin 用 OpenGL ES 合成，Xwayland 的 GLX 是直接渲染。
- `glmark2-es2-wayland --off-screen`（1245×2664，build/texture/phong/refract/terrain）得 900 分。压测中 devfreq 从 220 MHz 升到 818 MHz，没有 GPU fault 或 hangcheck。
- Vulkan：需要 `vulkan-freedreno`（已加入镜像软件清单）。Turnip 报告 Vulkan 1.4，`vkcube` 跑 300 帧正常。
- 未测：游戏、视频硬解、长时间负载下的温控。

## 内屏分辨率：当前使用 FHD+（2026-11-12 实机核查）

OnePlus 10 Pro 的屏幕原生分辨率为 **1440×3216**（官方横屏写法为 3216×1440），不是 1080×2412。当前手机的 DRM/KWin 仅提供 **1080×2412 @ 60/90/120 Hz**，实际选择 120 Hz；这是当前 Linux 驱动可用的输入模式，不能作为面板原生像素数。

面板驱动 `panel-samsung-s6e3hc3.c` 已列出 FHD+ 和 WQHD+ 两组模式，但 probe 中的 DSC 配置仍固定为 `slice_width = 540`、`slice_height = 36`、`slice_count = 1080 / 540`。DSI 模式校验要求画面宽高能分别被分块宽高整除，1440 无法被 540 整除；实机当前启动日志反复出现 `DSI: pic_width 1440 has to be multiple of slice 540`，因此 WQHD+ 模式未进入可选列表。详见[核查依据](../artifacts/display-resolution-20261112/README.md)。

本次通过 USB SSH 只读核查模式、日志及 WSL 源码，没有修改驱动、切换显示模式或重启。**原生 1440×3216 的完整适配与显示效果未测**；不能仅修改模式尺寸或 DSC 分块宽度就视为修复。未来 4:3 掌机串流的渲染/采集分辨率可与内屏预览模式分开设计，虚拟显示、拉伸预览和串流均未测。

2026-11-13 原厂资料补充：本机 `dtbo_a` 的量产面板配置明确区分 FHD 的 **540×36** 与 WQHD 的 **720×24** DSC slice，两组均保留 60 / 90 / 120 Hz 条目，DSC 1.2、8 bpp、每包 2 个 slice。后续可据此对照 PPS、切换命令、DSI 时序与带宽；本轮仅静态分析，没有改驱动或切换分辨率，见[原厂面板资料](stock-hardware.md#原生屏幕分辨率)。

## Runtime PM 与慢亮屏

2026-11-17 已部署 **GPU 自动省电 + 1000 ms 自动挂起延时**，并回移恢复死锁修复 `e0f04ee5b6`。手机运行修复内核 `#8`；`gpu-runtime-pm.service` enabled / active，旧保活服务 disabled / inactive。内核、父仓库固定点、恢复 bundle、新建/续建与打包检查均已接通，新完整 rootfs 镜像未构建、未刷入。

新内核上，锁屏后 **20 轮混合测试全部通过**（熄屏 2/5/15/60 秒各 5 次）：每轮 DPMS Off、GPU/GMU suspended、挂起计时增长，亮屏后 FD730 GL 渲染成功，无新增 HFI/OOB/hangcheck/GPU fault/DRM 错误。DRM On 状态耗时 0.085–0.175 秒，中位数 0.124 秒，**不是光学亮屏延迟**。启用最终服务后再测 1 轮通过；保活切换及返回自动策略也已实机验证。1 秒延时减少空闲间隙的频繁掉电，不修改 GMU 握手超时；持续渲染时 active 是正常行为。

原默认保活的原因仍有完整记录：7.3-rc2 在 GMU suspend 后出现 HFI 等满 1 秒、OOB 超时及 hangcheck，见 [wake-latency-20260916](../artifacts/wake-latency-20260916/)。2026-11-11 的 2 次 `auto` 亮屏样本不足，见[前次重测](../artifacts/gpu-runtime-pm-20261111/README.md)。本轮旧内核、66 ms 延时下，20 次短测通过后，60 秒熄屏中的 `kscreenlocker_greet` 渲染仍触发 OOB GPU_SET 超时、CP 空地址故障及 watchdog；GPU 恢复线程持 `gpu->lock` 等待转储，SMMU 转储线程又等待该锁，KWin 与关机均被阻住。详见[本轮证据](../artifacts/gpu-runtime-pm-20261117/README.md)。

恢复修复来自[上游补丁](https://lists.openwall.net/linux-kernel/2026/11/01/730)：恢复持锁期间不等待故障转储，故障处理也跳过恢复期间的转储。真实 OOB/HFI 函数的 10 个交错场景、ARM64 DRM/MSM 编译及完整 Image.gz 链接通过，原代码在同一回归中确定性失败。经用户同意，完整备份并核对 SHA-256 后仅刷 `boot_b`；回读匹配，原 ramdisk 和 vendor_boot 保持不变，B 槽成功、可启动标记均为 1。

验证边界：最初 GMU 固件超时的根因尚未确定，**不能承诺已彻底消除所有 OOB 超时**；新内核没有再次触发实际 GPU fault，故障后的恢复与关机尚未实测。整机深睡、长期稳定性、实际节电瓦数，以及最终自动服务的再次整机重启未测。先前故障后恢复保活配置、由用户强制关机重开；随后修复内核通过正常重启启动。新内核 66 ms 长测中有一轮 DPMS 被改变，不计作熄屏验收；一次 1000 ms 初测因取样时仍有 GPU 活动停止，未出现内核错误，之后加入最多 3 秒的有界收敛检查重测。最终 20 轮未实际用到额外等待（最大约 0.4 ms 的采样开销）。

镜像新建默认启用自动策略、禁用保活；续建通过 `gpu-runtime-pm-sources.sha256` 自动迁移旧配置并使旧打包标记失效，手动入口为 `sudo bash scripts/update-gpu-runtime-pm-image.sh`。打包前核对两份 unit、内容、权限、shell 与启用链接，拒绝残留的默认保活。自动策略应与含本次恢复修复的内核配套，旧内核不要只补 unit 就启用 `auto`。

手动恢复持久保活：

```sh
sudo systemctl disable --now gpu-runtime-pm.service
sudo systemctl enable --now gpu-runtime-active.service
```

在修复内核上返回自动省电：

```sh
sudo systemctl disable --now gpu-runtime-active.service
sudo systemctl enable --now gpu-runtime-pm.service
```

## 物理绿线与诊断显示（2026-11-14）

用户报告面板多条绿线。对话曾显示全屏黑色供人眼判断，但没有后续观察结论：如果黑画面下绿线仍亮，渲染黑色像素不能修复面板驱动电路；当前未实现逐列屏蔽，也未证明软件可以去除绿线。面板故障与 DSC 参数挡住原生分辨率是两个问题。System Monitor 的 GPU 温度面板配置归入[可选调试应用](optional-apps.md)，不代表新增 GPU 利用率驱动。
