# A730 自动省电与亮屏恢复（2026-11-17）

## 当前结论

已部署恢复死锁保护及 `auto` / **1000 ms** 自动挂起。修复内核 `#8` 的锁屏混合复测 20/20 通过，包含五次 60 秒熄屏；最终服务再测 1 轮及手动保活往返通过，journal 无新增 GPU/显示错误。原内核 66 ms 的短测通过但长测失败保留如下，不能混作新方案结果。

已回移恢复死锁补丁 `e0f04ee5b6752bcc21a7d4aad1aeeb0bc30d92a3`，完成 ARM64 DRM/MSM 编译、完整 Image.gz 链接和真实等待函数回归。经用户同意，完整备份并校验后只刷 `boot_b`，候选前缀回读 SHA-256 一致；新内核 `#8 SMP PREEMPT Tue Nov 17 23:19:14 CST 2026` 已启动，USB SSH、DRM DPMS On、保活服务及 B 槽标记正常。新内核的 60/120 秒记录与主动锁屏触发未新增 GPU 错误，一轮 DPMS 被改变，不计作熄屏验收。后续 1000 ms / 20 轮严格复测全部通过。补丁只针对恢复死锁，最初的 OOB 超时根因仍未确定；新内核实际 fault 后的恢复尚未观察到。

## 实机结果

| 测试 | 结果 |
| --- | --- |
| 原策略 `on`，3 轮，熄屏 2/5/15 秒 | GPU/GMU 始终 active，GPU 挂起计时 0；亮屏及 FD730 GL 成功，无新增 GPU 内核错误 |
| 原内核 `auto`，20 轮，熄屏 2/5/15 秒 | GPU/GMU 每轮均 suspended，挂起计时增长；20 次亮屏及 GL 成功，journal 无新增 GPU 错误 |
| 临时启用自动服务后，0.2/1 秒两轮 | 亮屏及 GL 成功 |
| 随后熄屏 60 秒 | 23:07:25 OOB GPU_SET 超时；随后 CP 空地址故障、hangcheck recover、GMU watchdog；GPU 卡在 suspending，KWin 无法亮屏 |
| 修复内核，1000 ms，20 轮 2/5/15/60 秒混合 | 20/20 挂起、亮屏、GL 成功；五次 60 秒熄屏；无新增 GPU/显示内核错误 |
| 最终自动服务及保活往返 | 自动服务 enabled / active，保活 disabled / inactive；往返和另 1 轮熄屏恢复通过 |

原内核 `auto` 的 DRM On 状态耗时 0.078–0.176 秒，中位数 0.149 秒；保活基线 0.117–0.154 秒。GL 进程耗时包含启动及 0.2 秒负载，不是光学首帧时间。这些短测结果不能覆盖失败的长熄屏场景。

最终方案 DRM On 状态耗时 0.085–0.175 秒，中位数 0.124 秒；GL 进程 0.565–0.685 秒（含 0.2 秒负载）。一次前置 1000 ms 取样因 GPU 仍 active 停止，无内核错误；之后加入最多 3 秒的额外收敛检查。最终 20 轮未用到额外等待，最大约 0.4 ms 为采样开销。

整理后的 [evidence.json](evidence.json) 保存计时与状态摘要，[build.json](build.json) 保存候选和完整分区备份的 SHA-256。原始输出、完整 GPU 转储与分区文件只留在忽略的 `logs/gpu-runtime-pm-20261117/`，不纳入 Git；转储读取曾被同一锁阻塞，没有取得有效内容。

## 死锁依据与修复范围

- `gpu-worker`：`recover_worker` 持有 `gpu->lock`，经 `a6xx_recover → a6xx_gmu_pm_suspend → a6xx_gmu_set_oob` 等待 `fault_coredump_done`。
- SMMU 故障线程：`adreno_fault_handler → msm_gpu_fault_crashstate_capture` 等待 `gpu->lock`，无法完成上述 completion。
- KWin 和写 `power/control=on` 的恢复进程都等在 runtime resume；切回 `on` 不能解除已经形成的死锁。

来源为 Nico Angelo Dela Cruz 的[上游恢复锁修复](https://lore.kernel.org/all/20261101175553.53746-2-nicoangelodelacruz@gmail.com/)（[可读归档](https://lists.openwall.net/linux-kernel/2026/11/01/730)）。本机调用栈与其描述的锁依赖一致。回移增加 `recovery_in_progress`，在恢复持锁期间跳过故障转储，并让 OOB/HFI 等待返回正常超时，避免等待无法完成的转储。

`tests/test-gpu-recovery.py` 提取实际驱动的两个等待函数，验证正常应答、真实超时、转储完成后重试、恢复持锁时不等待、恢复期间正常应答，共 10 个交错场景。原代码会在模拟互等处确定性失败，新代码通过；同时完成真实 ARM64 编译。该测试不能证明 GMU 固件握手已修复。

## 恢复与镜像交付

失败后先恢复保活开机自启、禁用自动服务。正常重启被死锁阻住；经用户同意，由用户强制关机重开后恢复。另一次获准的操作仅刷 `boot_b` 并正常重启至补丁内核，`vendor_boot_b` 保持原样。全过程没有写 USB role、重绑 UDC 或重绑音频。

新建、续建均默认启用 `gpu-runtime-pm.service`，先写 1000 ms 延时、再写 `auto`；旧保活服务默认禁用，保留手动恢复入口。来源指纹使旧打包标记失效；打包前检查两份 unit 的内容、权限、shell 与启用链接，拒绝任意 target 下残留的保活启用项。两份策略互斥。

WSL `NegroniBuild-Ubuntu-26.04` 中，完整主机检查和 `sudo bash scripts/check-image-delivery.sh` 通过；后者包含 5 项 GPU ext4 安装、迁移、幂等及错误配置拒绝测试。内核提交、父仓库固定点及恢复 bundle 已配套。新完整 rootfs 镜像未构建、未刷入；节电瓦数、整机深睡、长期稳定性、实际 fault 后的恢复与关机，以及最终自动服务的再次整机重启未测。旧内核不要单独补 unit 开启自动挂起。

## 复测入口

[dpms-cycle.py](dpms-cycle.py) 使用 oneplus Plasma 会话、KWin DPMS、GPU/GMU runtime 计时及真实 FD730 GL。测试用 sleep inhibitor 隔离整机睡眠，核查 kernel journal 增量。检查还要求熄屏取样时 DPMS 保持 Off；允许最多 3 秒的后台渲染收敛并单独记录。普通失败退出会恢复原策略并亮屏；内核已经死锁时，恢复写入也可能阻塞。

```sh
sudo systemd-inhibit --what=sleep --why=GPU-runtime-PM-validation \
    python3 /tmp/negroni-gpu-dpms-cycle.py auto 3 --off-seconds 60 60 120
```
