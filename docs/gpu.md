# GPU（Adreno 730）

状态日期：2026-11-12。

## 3D 加速：可用（2026-11-11 实机）

内核和固件都不需要修改：

- msm / Adreno 730 正常绑定，`a730_sqe.fw`、`gmu_gen70000.bin` 和 zap shader 都能加载。启动 0.8 秒时的 `failed to load a730_sqe.fw` 只是 rootfs 挂载前的第一次尝试，12 秒时会加载成功。
- Mesa 26.2.6：GL ES 3.2，渲染器为 `FD730`。KWin 用 OpenGL ES 合成，Xwayland 的 GLX 是直接渲染。
- `glmark2-es2-wayland --off-screen`（1245×2664，build/texture/phong/refract/terrain）得 900 分。压测中 devfreq 从 220 MHz 升到 818 MHz，没有 GPU fault 或 hangcheck。
- Vulkan：需要 `vulkan-freedreno`（已加入镜像软件清单）。Turnip 报告 Vulkan 1.4，`vkcube` 跑 300 帧正常。
- 未测：游戏、视频硬解、长时间负载下的温控。

## Runtime PM 与慢亮屏

默认启用的 `gpu-runtime-active.service` 把 GPU 的 `power/control` 设为 `on`，阻止 runtime suspend。这是规避措施，可能增加待机耗电。

原问题出现在 7.3-rc2，见 [wake-latency-20260916](../artifacts/wake-latency-20260916/)：GMU suspend 后亮屏时，`a6xx_hfi_set_freq` 发出的 `GX_BW_PERF_VOTE` 在等中断时等满 1 秒超时，随后读到同一 seqnum 的 `Unexpected message id`（GMU 其实已经回复），还伴有 `Timeout waiting for GMU OOB set GPU_SET` 和 hangcheck recover。

2026-11-11 在 7.3 正式版上重测，见 [gpu-runtime-pm-20261111](../artifacts/gpu-runtime-pm-20261111/README.md)：设成 `auto` 后，熄屏期间 GPU、GMU 都处于 `suspended`；2 次亮屏的 panel On 约 0.09 秒，没有复现 1 秒超时。但样本只有 2 次，也没有检查这两次的 dmesg，**所以还不能移除这个服务**。

下一步：

1. 在已登录的 Plasma 会话中（SDDM 登录界面下 kscreen-doctor 无法连接）用 `dpms-cycle.sh auto 10 <秒>` 跑至少 10 轮，同时收集 dmesg 中的 HFI / OOB / hangcheck 记录。
2. 如果仍偶发超时，对比 7.3-rc2 → 7.3 之间 `a6xx_gmu` / `a6xx_hfi` 的变化，再考虑在 resume 时清除残留的 MSGQ 位。
3. 如果稳定，把默认值改为 `auto`（或调大 `autosuspend_delay_ms`），并同步更新 [设备状态](status.md) 和构建脚本。

注意：测试中手机被另一个 SSH 会话的 `systemctl reboot` 重启过。多个会话共用手机时，重启前要先确认没有别人在用。
