# A730 GPU runtime PM 重测（2026-11-11，内核 7.3.0-sm8450+）

目标：评估能否去掉 `gpu-runtime-active.service`（`power/control=on`），让 GPU 在熄屏时 runtime suspend，同时不回到 2026-09-16 记录的慢亮屏。

## 原问题（7.3-rc2，见 ../wake-latency-20260916/）

GPU/GMU runtime suspend 后亮屏，`a6xx_gmu_resume -> a6xx_gmu_set_initial_freq -> a6xx_hfi_set_freq` 发送 `HFI_H2F_MSG_GX_BW_PERF_VOTE`，在 `a6xx_hfi_wait_for_msg_interrupt` 中等满 1 s 超时；下一条消息随后读到 `Unexpected message id <同一 seqnum>`，说明 GMU 已回复，只是主机没在 1 s 内看到 MSGQ 中断位。另有 `Timeout waiting for GMU OOB set GPU_SET` 与 hangcheck recover。

## 本次结果

`dpms-cycle.sh auto CYCLES OFF_SECONDS`：设 `power/control=auto`（autosuspend 66 ms），通过 KWin `kscreen-doctor --dpms` 熄屏 / 亮屏，记录 runtime 状态、亮屏时间和首帧 GL 时间。

| 运行 | 结果 |
| --- | --- |
| [run-auto-1.txt](run-auto-1.txt) | Plasma 会话内有效。熄屏期间 GPU、GMU 均为 `suspended`；2 次亮屏 panel On 约 0.09 s，唤醒后首个 glmark2 进程约 0.6 s（含进程启动）。第 3 次循环中手机被另一 SSH 会话的 `systemctl reboot` 重启（4002 s，见 [prev-boot-kernel.txt](prev-boot-kernel.txt)），与 GPU 无关 |
| [run-auto-2.txt](run-auto-2.txt) | **无效**：重启后停在 SDDM，没有用户 Wayland 会话，kscreen-doctor / glmark2 无法连接（首帧 0.02 s 即失败）。运行中手机再次断开，之后网络不可达，原因未查明 |

初步结论：7.3 正式版上 runtime suspend → resume 两次未复现 1 s HFI 超时，但样本只有 2 次，且未检查这两次的 dmesg。**尚不能移除 `gpu-runtime-active.service`。**

## 待做

1. 手机恢复后，在已登录的 Plasma 会话中重跑 ≥10 次循环，同时收集 dmesg 中的 HFI / OOB / hangcheck 记录。
2. 若仍偶发超时：检查 7.3-rc2 → 7.3 之间 a6xx_gmu/a6xx_hfi 的变化，再考虑内核修复（如 resume 时清除残留 MSGQ 位或 HFI 队列）。
3. 若稳定：将服务改为默认 `auto`（或适当提高 autosuspend_delay_ms），并更新 docs/status.md 与构建脚本。
