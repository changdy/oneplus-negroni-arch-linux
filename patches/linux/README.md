# 7.3 设备修复与源码恢复

当前 `linux` 子模块固定到 `7.3` 修复提交 `d1ca2f4d48c2e6928bfe5c6da358615e879785bf`。修复从重新同步的上游 `476a4a8984395a77b6b6508f849dfb7b786d86b3` 直接修改，新增提交均只有一个父提交；没有 merge 或 cherry-pick `7.3-rc2`。之前的本地合并版本不再作为固定内核。

新增提交为 `835c18d2739`（电池驱动及限充）、`3ca85b51d20`（CPU 参数）和 `1eaec99b04a`（补齐触觉驱动 trace 头文件）。

USB/PD 修复包含 `f4f7868ffd28`（USB2 门控、参考时钟恢复、PHY 掩码与板级参数）、`439ec8c36683`（DP C/E 保留 USB2）和 `0354cd55ba6a`（OTG GPIO、PD/USB 充电）。

角色切换修复包含 `b75515b1a61`（按目标角色设置 QSCRATCH，处理 NONE）和 `fc09f1b2e7e`（注册 xHCI 前完成 PHY 模式设置并处理失败）。当前实机限制见[设备状态](../../docs/status.md)。恢复 bundle 包含上述修复及原有电池/CPU 修复和独立 rc2 引用，仍使用下述两个已发布的前置提交。

充电状态修复 `0466d55fd348` 为 Negroni 按当前输入、电池电流和已确认限充状态计算最终状态，修正固件直接报告放电、实际却在充电的问题；读取失败或固件重连时拒绝旧数据。源码与使用行为见[充电说明](../../docs/charge-limit.md)。

USB 失电恢复修复 `23a6b6d834e` 在完整关闭 DWC3 时通知 xHCI 重建，覆盖 HOST 与原生 OTG 主机分支，并在每轮 PM prepare 清除旧标志；本机受控对比中，缺失通知时出现非法 DMA、外设全部丢失，修复后连续 3 次相同测试通过。此前热插拔的 `IOVA=0xc` 故障仍未确认消除，见[设备状态](../../docs/status.md)。

触摸 I²C 修复 `6732cbb2b0b` 在 RX 完成时回收对应的 linked TX GO 描述符与环槽位，仅由 RX 通知客户端一次完成，并按实际 TX TRE 数量检查容量。原实现只有 RX 完成通知，TX 环逐渐耗尽；实机相同 256 次读取由 8 次 EIO 降为零错误。源码恢复 bundle 已包含该提交。

QRTR 握手修复 `984f1b07caa` 解决基带启动约 40 秒后 `DOG detects stalled initialization` 的循环崩溃。上游 `544d85de4dc2` 之后，内核自己的 HELLO 发出前会以 `-EAGAIN` 拒绝其他包；基带的 HELLO 先到时，名称服务回复的 NEW_SERVER 通告被拒且不再重发，基带因此找不到 rmtfs。修复记录远端已发过 HELLO，待本端 HELLO 发出后把它重新交给名称服务再通告一次，并在通告失败时打印目标与错误码。2026-11-11 实机验证：启动时基带（节点 0）与 WCN6855（节点 7）仍会触发该竞争，重放后均恢复，基带不再崩溃；日志中的 `failed to announce new service ... -11` 属预期。该实现按上游未合入补丁的思路自行编写，上游合入正式修复后应替换。源码恢复 bundle 已包含该提交。

音频设备树修复 `ead3411b6e6` 修正声卡始终不生成的问题：`audio-routing` 引用了主线 LPASS 宏与 WCD938x 驱动中不存在的 widget（如 `VA AMIC1`、`Digital Mic0`、`WCD_TX_OUTPUT`），路由失败会使 ASoC 放弃整张卡且只在 debug 级别记录，现改用 `sm8450-hdk` 的路由（去掉 WSA 扬声器项）。TFA9874 扬声器链路由 `TERTIARY_TDM_RX_0` 改为 `TERTIARY_MI2S_RX`（同一组 mi2s2 引脚，16 bit 立体声 I²S）并投票 Tertiary MI2S 位时钟，因为 7.3 的 q6apm TDM 端口需要 SM8450 ADSP 不具备的 AUDIO_IF 模块。还需配套的 AudioReach 拓扑与 UCM，见[音频说明](../../docs/audio.md)。2026-11-12 实机验证扬声器出声；早期内置麦克风的非零样本后来确认只是启动瞬态，2026-11-13 原厂路由与门控对照后稳定段仍全零，麦克风不可用，见[调试记录](../../artifacts/mic-clock-20261113/README.md)。源码恢复 bundle 已包含该提交。

USB2 gadget 修复 `f8350cc1e221` 释放 HS PHY 的充电检测 datapath override，并在控制器仍为 device 时重新设置 USB2 PHY 模式，补上重复 DEVICE 请求被提前跳过的恢复路径。2026-11-13 已刷入 b 槽并重启：USB2 随启动、连续 3 次同口拔插、USB3→USB2 换口均自动恢复，USB2 双向各 64 MiB SHA-256 一致，无需用户空间恢复脚本。实机保留既有 LPM 实验属性；完全断电启动、去掉 LPM 属性及 OTG / PD Hub / 挂起回归未测，见 [USB 调试记录](../../docs/usb-debug.md)。bundle 保留原两个前置提交及历史 rc2 引用。浅克隆重建时可用临时 bare 仓库共享对象，`GIT_SHALLOW_FILE` 指向只包含两个前置提交的边界文件，生成并验证 bundle；不要修改工作树的 shallow 边界。

LPASS 录音状态修复 `463023bf84b1` 改为按 TX/VA 通道 mask 的实际 bit 判断 mixer 是否变化，避免双路关闭遗漏与重复写导致的计数失真，并对全部已选 TX 通道执行数字静音。2026-11-14 两模块独立构建、安装并重启，运行模块 build-id 与文件匹配，真实 UCM 双路启停/还原通过；原 TX/VA 的真实回调均不能通过新增回归。内置麦克风 UCM 同时改为原厂 DMIC3/4。2026-11-14 傍晚另一次只改 DTB 的 `vendor_boot_b`（SHA-256 `2714b634cc0fadbc96378c9c71f92851c41357a92ed4635476389e3b65473703`）去掉 `audio-codec` 的 `sleep` 引脚状态并重启，ALSA 直接录音录到 1 kHz 测试音；该改动随后由内核提交 `67d9e35c9ac0` 保存，只含这个引脚状态。手机验证用的是同一改动的 `vendor_boot` 字节补丁，不是用该提交重新构建的镜像；三次短振后的 10 秒录音已从喇叭外放，用户听过。VA CPU DAI/DMIC4 DT 候选同样只部署到测试分区，尚未应用到内核源码；其他未提交相机、语音图和 DT 改动没有混入此提交。恢复 bundle 已更新，见[实机记录](../../artifacts/mic-clock-20261113/README.md)。同一提交已包含在下面的相机固定点里，2026-11-14 的镜像封装带上了这个设备树。

相机 CSID 修复 `a7d9e945d961` 让 lite CSID 不再写顶层寄存器，停流时恢复完整 CSID 的顶层复位值并真正关掉 RDI，开流失败时停掉已经启动的实体。2026-11-14 用含同一改动的模块在 NE2210 上连续 58 次四摄切换和重复启停通过，没有硬重启。同日用该提交重新封装 `/opt/negroni-build/images/7.3`，`boot.img` SHA-256 `3fb7199a69055b9d17c4bed80f1760f48fb27c72b1df6f1657d4ec9449392d98`，构建时没有本地未提交差异。2026-11-14 17:03 只写 `boot_b` 并安装对应模块后重启，内核为 `#5`，B 槽仍成功。17:10 这份模块不认识 C-PHY，四摄 overlay 无法探测；超广角随后因 `titan_top_gdsc` 卡在 off 而无法再次上电。

相机 C-PHY 与 GDSC 修复 `d1ca2f4d48c2` 让 SM8450 接受 C-PHY 端点并按原厂 2.1.0 寄存器打开 trio，PHY 走 gen2 路径，CAMCC 使用 shared RCG 且 GDSC 保留触发器状态。连续 DMA 与 CSID 初始 RUP 一并纳入，因为通过 58 次启停的模块就是这套组合。构建镜像 `boot.img` SHA-256 `070cef14d8078fa09f0281a3cb1ddb4d7b2c2f8cb899c8fff9fd234185369d93`。17:34 写入 `boot_b` 并重启为内核 `#6`，17:35 四轮四摄启停 16/16 出帧，没有硬重启。只提交 CAMCC 和 CAMSS，音频与未提交设备树没有混入。bundle 保留原两个前置提交与历史 rc2 引用，见[相机说明](../../docs/camera.md)。

## 重做范围

振动反馈修复 `f2fc09167951` 导出 OF 匹配表，使 PM8350B 模块按设备别名自动加载；接受 feedbackd 使用的标准 rumble / sine 兼容效果，将播放 I/O 移出输入事件自旋锁，按播放时刻重置停止计时器，落实停止和 16 bit 主增益，并补齐卸载清理。升压等待函数在内部获取 `play.lock`，工作任务必须在锁外调用它；首次实验的嵌套锁问题已被回归捕获并修正。2026-11-14 独立模块编译、开机自动加载、重复短振、提前停止、桌面 D-Bus、模块卸载重载均通过，用户确认触感。只提交振动驱动，其他相机、设备树和 AudioReach 未提交改动没有混入。bundle 保留原两个前置提交与历史 rc2 引用，见[振动反馈说明](../../docs/haptics.md)和[实机记录](../../artifacts/haptics-20261114/README.md)。

| rc2 原始修复 | 7.3 实现 |
| --- | --- |
| `593ad628e5b838457d6a316cc08ba5dcc924a01f`：Negroni 电池电流极性 | 在当前 `oplus_battmgr` 的电池属性出口转换符号，仅适用于 `oplus,negroni` |
| `2c092365fd5c72efcedc29a578601b0a41ce45c4`：可选充电限制 | 重新接入新驱动的请求、通知、初始化与恢复路径；默认关闭，75/80% 滞回，停充保留 USB 输入，提供 sysfs 控制、失败重试及挂起限制 |
| `05e876f60a304a400bc1b44da2de3b155c2bc829`：CPU 能力与功耗 | 在当前 `sm8450.dtsi` 补齐 8 核的 16 个参数，沿用一加公开 waipio 设备树的实测值 |

7.3 的 Negroni 已切换到 `oplus_battmgr`。适配同时修正充电开关与 USB 查询的 opcode、SM8450 USB 属性编号及电池温度的重复缩放；将等待回复的通知处理放到工作队列，统一在固件请求锁下管理充电状态和许可回复。限充期间的 VOOC 通知和错误恢复不能关闭 USB 输入；被拦截的 VoocPHY 启用请求在放行后补发；电量计初始化失败每 5 秒重试，连接代次变化、固件掉线或停止时不误报成功。

未修改的上游 Oplus 驱动对象编译失败，包含不存在的厂商结构成员和函数、指针成员访问错误以及未定义的 `chip`。本次移除未调用且缺少依赖的厂商辅助函数，并修正有效调用点。`sm8450.config` 启用 Oplus 驱动及共享 Qualcomm 模块。触觉驱动补齐下述 trace 头文件；其余 7.3 GPU、haptics/PBS 驱动、Negroni 设备树及 Kconfig/Makefile 沿用当前上游。

## 恢复与历史复现

`local-7.3.bundle` 提供两个独立引用：

- `refs/heads/7.3`：当前线性修复；前置提交为 `476a4a8984395a77b6b6508f849dfb7b786d86b3`。
- `refs/heads/7.3-rc2`：保留上述三个历史提交的原 ID，仅供原始修复与 CPU 对比复现；前置提交为 `e8291a2765b80f94c047d28ca514465c7716c374`。此引用不属于新 `7.3` 的祖先历史。

首次克隆运行 `bash scripts/init-submodules.sh`。脚本获取 bundle 的已发布前置提交、验证 bundle、导入两个分支到 `refs/remotes/migration/`，然后恢复父仓库固定的内核提交。即使当前固定提交已经存在，也会补齐缺失的历史引用所需对象。内核新提交通过父仓库的 bundle 分发，无需依赖它已推送到内核远端。

已有 `linux/` 若存在未提交修改，初始化脚本会停止。已有本地 `7.3` 仅在可快进时更新；旧合并分支若与新提交分叉则保留，固定源码检出为 detached HEAD。之后可不带分支参数执行 `./build.sh`，或先自行保存并调整本地分支；`./build.sh 7.3` 会拒绝缺少当前固定修复的旧分支。

`local-7.3-rc2.bundle` 继续保留原始恢复副本。`sm8450-cpu-capacity.patch` 基于旧 `2c092365fd5c`，参数来源、实测范围及恢复步骤见 [CPU 性能与调度指南](../../docs/cpu-performance.md)。`python3 scripts/build-cpu-performance-dtb.py` 使用独立的历史对象，在临时目录应用补丁生成对比 DTB / vendor_boot，不改变当前内核工作树。

## 验证与 code review（2026-10-24）

修改完成后复核了协议映射、限充边界、固件许可、重连代次、请求锁、工作项生命周期及恢复脚本。Review 发现退出过程中回调仍可能提交任务，以及恢复任务可能在限充任务取消后重新排队；现以事件自旋锁串行化回调排队和停止标记，等待所有生产者退出后最后取消限充任务，同时保留命令回复以完成正在等待的请求。新增退出回归覆盖生产者完成时再次排队和停止后的通知/回复处理及阈值写入拒绝。复核后未发现阻塞提交的问题。

已通过：

- `bash scripts/check.sh --with-kernel`：8 项服务测试、4 项子模块恢复测试、阈值策略、7 组真实驱动函数回归、3 项全新/续建 Docker 配置测试。
- ARM64 的 Qualcomm/Oplus 电池驱动对象编译和 Negroni DTB 编译；核对全部 8 核参数。Oplus 驱动仍有未使用函数和缺少原型的上游警告。
- 新增遥测回归验证电流极性、温度单位、USB 查询 opcode、停充状态与离线阈值读取；分别回退前三项修复均触发断言失败。回退任务取消顺序也会触发退出回归失败。
- 历史 CPU DTB / vendor_boot 对比构建；恢复 bundle 的独立前置提交导入和初始化脚本验证。
- 父仓库与内核 `git diff --check`；新内核提交区间无 merge，rc2 头不是新 7.3 的祖先。

截至 2026-10-24，尚未构建完整新固件或进行真机验证；历史实测仍对应 `7.3-rc2`。

## 完整构建修复与验证（2026-11-01）

完整编译发现 `qcom-hv-haptics.c` 引用的 `include/trace/events/qcom_haptics.h` 缺失。`1eaec99b04a` 从[一加公开 SM8450 内核的固定提交](https://github.com/OnePlusOSS/android_kernel_oneplus_sm8450/blob/449760504b3a75728eb60479f5b34dc51cb263ce/include/trace/events/qcom_haptics.h) 补齐四个 trace 事件，保留版权与 GPL-2.0-only 声明，并将 `__assign_str()` 适配为当前内核的单参数形式。恢复 bundle 已包含此提交。

构建脚本同时补齐未跟踪头文件的本地补丁记录，并按 `CONFIG_PHY_QCOM_QMP_UFS` 区分内置与模块配置：内置驱动不要求 initramfs 再包含 `.ko`，模块配置仍强制检查对应文件。

包含上述修复的 `7.3.0-sm8450+` 完整内核、设备树、模块及 641 包 rootfs 已构建完成；Docker、CPU、屏幕默认值、充电限制、ext4、sparse 往返、启动镜像内容和 SHA-256 离线校验通过，`bash scripts/check.sh --with-kernel` 也通过。该次镜像在提交前构建，报告保留 `3ca85b51d20` 与本地头文件补丁的真实记录。镜像尚未刷入，真机启动待验证。
