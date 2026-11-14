# USB SSH 意外断连只读排查（2026-11-13）

设备：OnePlus 10 Pro NE2210，`7.3.0-sm8450+ #4`（2026-11-13 21:54:31 构建）。所有时间为北京时间。整理后的机器可读结果见 [evidence.json](evidence.json)。

## 结论

**确认曾有一次 SCP/TCP 会话中断及随后 USB SSH 超时；未定位根因，也未复现。** 现有记录更符合 USB 网络数据路径或 TCP 会话的瞬时异常，没有发现手机重启、服务重启、USB 重新枚举、切换到 host 或 PHY override 再次占用的证据。故障当时没有同步抓包或 USB 请求跟踪，因此不能排除未被现有日志记录的主机 NCM、过滤/路由、设备 NCM/DWC3 短暂异常。

不能把本次故障直接归为用户拔线，也不能据此宣布 USB 长时间稳定性已经验证。

## 原始事件和事后证据

| 时间 | 记录与含义 |
| --- | --- |
| 22:02:48 | Windows composite、NCM、COM3 的 `LastArrivalDate`；22:39–22:41 采集时仍为该值，ProblemCode 为 0，没有故障时段的重新到达记录 |
| 22:02:49.466 | 截至 22:45:34 采集，手机本次启动的最后一条内核日志；之后没有 USB reset、OTG、PHY 恢复、panic、watchdog 或挂起日志 |
| 22:34:38.531 | 手机接受原 SCP 连接：本地 22、对端 4930；用户报告未移动 USB，客户端稍后报 `reset by peer`，随后两次连接超时 |
| 约 22:35:08 | 由 22:40–22:41 的 `ss -ti` 中 `lastack` 反推旧连接最后收到 ACK 的时间；这是推算值，不能代替当时抓包 |
| 22:35:57 | Windows Hyper-V 为 NCM 对应 GUID 建立 FSE Switch 虚拟端口并调整 RSC；晚于上述 ACK 时间约 49 秒，只能证明并行虚拟网络活动，不能证明因果 |
| 22:36:53.167 | 手机再次接受 USB SSH，连接已自动恢复；没有重启手机或恢复 gadget 服务 |
| 22:40:25–22:41:25 | 旧 SCP 在手机上仍为 `ESTAB`、Send-Q=1716、`rto=120000`、重传退避持续增加；手机尚未将该连接正常关闭。客户端文字不能证明手机 SSH 主动发送 RST |

手机 `usb-gadget`、NetworkManager、sshd 的启动记录均属于本次开机，`NRestarts=0`，故障时段没有对应停止/启动记录；无 failed units。开机时曾校时，服务属性中的 1970 年绝对时间不能直接作为真实启动时间。`usb0` 的最后一次 carrier connected 日志为 22:02:48.263，未发现故障时段 carrier 变化。

只读寄存器/电源快照（22:41:25）：DWC3 `mode=device`、`link_state=On`、`DCFG=0x00a0080c`；HS PHY `PHY_CFG0=0x00000000`，datapath override bit 0 为 0。DWC3 与 PHY runtime status 均为 active、runtime suspended time 为 0。这只能说明采集当时正常，不能反推故障瞬间的寄存器值。

Windows 的 USBXHCI、UCMUCSICX、NetworkProfile、Kernel-PnP 三个已启用日志、WFP 日志在 22:25 至采集时没有新事件；这些通道不是完整 USB/网络跟踪。NDIS/TCPIP 详细通道未启用，本次没有为了排查改动它们。Windows 静态地址仍为 `10.55.0.2/24`，NCM 收发错误和丢包统计均为 0。未发现另一会话在故障窗口内重启手机相关服务或操作角色/UDC 的记录；没有进程级全量审计，不能宣称排除了所有并行操作。

## 有限复现

2026-11-13 22:42:15–22:45:14，同时保持 USB SSH 与 Wi-Fi SSH，各每秒采样一次，共各 180 条；通过 Wi-Fi 另运行 180 秒 `ip monitor link address route`。

- 两路 SSH 全程完成；全部样本均为 `configured / high-speed / device / carrier=1`。
- `carrier_changes` 始终为 14，收发错误始终为 0，TX dropped 始终为原有的 3；netlink 无事件。
- USB 上下行各两次、每次 256 MiB，共各 512 MiB，全部退出 0、SHA-256 一致。采用未压缩的 SSH 零字节流；手机不保存上传内容，不能替代非零数据或文件系统测试。
- 随后使用 SCP 下载原分析目录的 `vendor_dlkm_b.img`：158,666,752 字节、9.490 秒，SHA-256 为 `7102fd102ac39c470335896185e2d7443e9e2d4bb508887f7f7057bb15abaedb`，与手机文件一致。
- 22:42:50 的 FSE 虚拟端口删除发生在测试期间，已有 SSH 观测及传输均继续完成；这次活动没有复现原故障，也不能排除其他虚拟网络活动。

手机到电脑的 175 次 ICMP echo 全部无响应，但同期 SSH 双向大流量成功；Windows NCM 网络为 Public，所检查的三个入站 ICMP echo 允许规则均未启用。因此本次反向 ping 不能用来判定 USB 是否断开；没有修改防火墙。

另测 Windows 到手机 20 次 ping，全部收到，RTT 为 1–2 ms、平均 1 ms。

22:50 追加只读复核：22:47:19–22:47:21 新出现 Type-C 状态工作及充电类型 17 日志，但没有新增 USB/PHY 恢复或 carrier 事件；`carrier_changes` 仍为 14，`configured / high-speed / device`，USB 与 Wi-Fi SSH 都成功，无 failed units。这段后续日志不能用来解释 22:34–22:36 的故障，也说明仅出现 Type-C 工作日志不能认定发生了断连。

## 范围与下一步

本轮没有重启、刷分区、写寄存器、切换 USB role、重绑 UDC、安装服务、修改网络/防火墙或调整相机、音频、基带。手机侧仅启动有限时间的采样、netlink、ping 和 SSH 数据流进程，结束后自动退出。

原始输出及临时脚本独立保存在忽略的 `logs/usb-disconnect-20261113/`，未改动原分析会话的 `logs/stock-hardware-20261113/`。本目录只含整理结果及原始证据文件的 SHA-256，不含镜像、凭据和原始日志。

若再次出现，保留 Wi-Fi 连接，同时采集手机 `tcpdump -i usb0`、UDC/carrier/netlink，以及 Windows NCM/USB/网络跟踪，核对 SYN、ACK、RST 到达哪一端。缺少当时的双端包或 USB 请求证据，尚不能把问题定位到某个驱动；本轮没有进行禁用过滤器/虚拟网络的配置对照，也没有验证数小时稳定性、挂起恢复、OTG 或 PD Hub。

## 仓库检查

`bash scripts/check.sh` 在 WSL `NegroniBuild-Ubuntu-26.04` 中全部通过，`git diff --check` 通过。此前在 Windows Git Bash 中执行时，前序检查通过，但子模块恢复测试的四个用例均因临时 `.gitmodules` 中直接写入 Windows 路径、Git 报 `bad config line 3` 而失败；未修改无关测试。上述离线检查不代表实机稳定性验证。
