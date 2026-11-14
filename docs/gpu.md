# GPU（Adreno 730）

状态日期：2026-11-12。

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

默认启用的 `gpu-runtime-active.service` 把 GPU 的 `power/control` 设为 `on`，阻止 runtime suspend。这是规避措施，可能增加待机耗电。

原问题出现在 7.3-rc2，见 [wake-latency-20260916](../artifacts/wake-latency-20260916/)：GMU suspend 后亮屏时，`a6xx_hfi_set_freq` 发出的 `GX_BW_PERF_VOTE` 在等中断时等满 1 秒超时，随后读到同一 seqnum 的 `Unexpected message id`（GMU 其实已经回复），还伴有 `Timeout waiting for GMU OOB set GPU_SET` 和 hangcheck recover。

2026-11-11 在 7.3 正式版上重测，见 [gpu-runtime-pm-20261111](../artifacts/gpu-runtime-pm-20261111/README.md)：设成 `auto` 后，熄屏期间 GPU、GMU 都处于 `suspended`；2 次亮屏的 panel On 约 0.09 秒，没有复现 1 秒超时。但样本只有 2 次，也没有检查这两次的 dmesg，**所以还不能移除这个服务**。

下一步：

1. 在已登录的 Plasma 会话中（SDDM 登录界面下 kscreen-doctor 无法连接）用 `dpms-cycle.sh auto 10 <秒>` 跑至少 10 轮，同时收集 dmesg 中的 HFI / OOB / hangcheck 记录。
2. 如果仍偶发超时，对比 7.3-rc2 → 7.3 之间 `a6xx_gmu` / `a6xx_hfi` 的变化，再考虑在 resume 时清除残留的 MSGQ 位。
3. 如果稳定，把默认值改为 `auto`（或调大 `autosuspend_delay_ms`），并同步更新 [设备状态](status.md) 和构建脚本。

注意：测试中手机被另一个 SSH 会话的 `systemctl reboot` 重启过。多个会话共用手机时，重启前要先确认没有别人在用。
