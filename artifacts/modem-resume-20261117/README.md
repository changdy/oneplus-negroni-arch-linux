# 2026-11-17 NE2210 蜂窝开机与唤醒恢复实测

修复后，NE2210 上的中国电信卡在一次新启动和连续两轮 deep 唤醒后均自动恢复注册、移动数据及 IMS 承载。第二轮唤醒后，基带确认 IMS 已在 WWAN 注册。本文先列充电后的验证结果，后附上午故障和修复依据。

## 充电后复测

USB SSH 恢复时，手机已经完成新启动，boot ID 为 `e9660fd2-5d3a-4422-83e3-96082bbaf1da`，电量显示 6%、Charging，ModemManager 与上午部署的文件哈希相符。下表为开机至对应事件的秒数，取自 journal 单调时钟。两次均由 systemd 请求 suspend，内核记录 deep 进入和退出。

| 场景 | LTE home / 分组 attached | 数据承载 connected | IMS 监控确认承载恢复 | 绑定数据接口的验证 |
| --- | --- | --- | --- | --- |
| 本次开机 | 36.96 s | 39.45 s | 68.69 s | `qmapmux0.0`，IPv4 HTTP 204、IPv6 HTTPS 200 |
| 第一次唤醒，192.43 s | 222.05 / 222.03 s | 222.86 s | 264.55 s | `qmapmux1.0`，IPv4 HTTP 204、IPv6 HTTPS 200 |
| 第二次唤醒，281.98 s | 306.03 / 306.02 s | 306.26 s | 341.86 s | `qmapmux2.0`，IPv4 HTTP 204、IPv6 HTTPS 200 |

三个场景均对 IPv4 和 IPv6 各发出两次 ICMP 请求，全部收到应答。HTTP 请求绑定当时已连接的 `ctnet` 接口，Wi-Fi 断开，USB 仅用于 SSH。IPv6 HTTPS 使用指定的 IPv6 地址和证书对应的主机名，域名的 AAAA 解析未纳入该项验证。ModemManager 全程 PID 3133、`NRestarts=0`。NetworkManager 自动激活已有的 `ct-lte` 配置。每轮 IMS 监控连续两次发现缺承载后自动重拉 81voltd，随后确认 IMS 承载连接。

第二轮在同一个 QRTR socket 上先发送 IMSA Bind（binding 0），再读 Get IMS Registration Status 和 Get IMS Services Status。承载恢复前读到未注册、语音服务不可用，之后读到 `registered / WWAN` 和 `available / WWAN`。未绑定的查询返回 `InvalidOperation`。可在手机上复查：[imsa-status.py](imsa-status.py)。

本轮未拨打电话，长期待机、功耗和新完整镜像启动未测。NetworkManager 仍报告设置 MTU 失败，本轮小包和 HTTP 测试未覆盖大包。原始输出在忽略的 `logs/modem-resume-20261117/afternoon-*`。

## 故障与修改

- 起初 `mmcli -L` 无设备，ModemManager 进程仍在、重启计数为 0；QRTR 节点 0 的 NAS、WDS、DMS 服务在线。上次唤醒后日志显示 `qcom-soc` 不被支持，仅重新检查到了 `rmnet_ipa0`。
- ModemManager 1.24.2 普通休眠路径会移除设备；恢复时的 `mm_base_manager_start()` 仅扫描 udev，而 QRTR watcher 没有重新发布仍在线的节点。候选补丁让后续扫描重新发布已就绪的 QRTR 节点，等待中的节点仍由原回调发布；并修正多个设备清理时的循环对象。详见 `config/gnss/modemmanager-qrtr-resume.patch`。
- 初次启动候选版本后一次 SIGSEGV，堆栈在 `netlink_messages_cb`。源码的事务完成路径从哈希表移除并释放事务后，又读取该事务的回调指针；候选补丁先保存指针。不能仅凭这一次堆栈断言此前所有崩溃均为同一原因。
- 随后两次停止旧候选进程时，`mm_iface_modem_count_bearers()` 断言 `max >= count` 导致 SIGABRT。新候选版本在承载多于上报上限时保留实际计数并警告，避免清理路径直接退出；受控休眠时实测计数为 2、上限为 0。
- 手机当前安装的候选 ModemManager（只移除调试节）SHA-256 为 `5cefe7ac92af190c630d46ba932293e363bb49c76fa4382e6b955ddd7e138206`，原程序备份为 `/opt/negroni-gnss/sbin/ModemManager.before-qrtr-resume`。源码补丁、构建脚本和镜像运行文件已更新；**新完整镜像未构建、未刷入**。此前 GNSS 补丁及私有 libqmi 保留，但此候选版本的 GNSS 回归未测。
- 手机已有电信 `ct-lte` 配置原先 `connection.autoconnect=no`；本轮改为 `yes` 并手动启用，以便后续开机及唤醒自动重连。该连接包含运营商和设备相关设置，不作为通用镜像预置；用户关闭移动网络的行为及其他运营商未测。

## 上午故障现场与首次复测

- 休眠前：LTE 注册为 home，分组业务 attached；`ctnet` 数据承载与 IMS 承载均为 connected。绑定蜂窝数据接口 `qmapmux0.0`，对 `223.5.5.5` 两次 ICMP 成功，HTTP 连通性请求返回 204；当时 Wi-Fi 未连接。此次休眠前数据实测仅覆盖 IPv4。
- 第 841 秒 systemd 请求休眠，内核记录 `PM: suspend entry (deep)` 和退出；唤醒后同一 ModemManager PID 7566、重启计数 0，重新探测 `qrtr0` 并以两个端口创建 `qcom-soc`。第 859 秒重新报告 home / attached，NetworkManager 自动激活 `ct-lte`，数据承载连接并配置 IPv4/IPv6。
- 第 871 秒又自动休眠，后续继续反复休眠；多次唤醒均看到了 QRTR 重新探测及部分数据自动连接。定时唤醒设置为 40 秒，但第一次 deep 提前返回；唤醒来源和有效深睡时长未确认。恢复后的绑定接口实际数据连通、IMS 承载、IMS 注册和通话均**未测完**；不能从承载配置推断真实数据收发或 VoLTE 可用。
- 电池上报 0%，曾读到约 3.802 V、Discharging；USB 电源在线。真实剩余电量和该上报的根因未确认。UPower 反复执行低电量休眠，USB SSH 时断时续，妨碍蜂窝恢复与观测。本轮为验证尝试短期 sleep inhibitor，但它没有阻止这些休眠，现已停止该临时服务；未修改永久电源策略。
- 原始故障现场保存在忽略的 `logs/modem-resume-20261117/pre-intervention.txt`。

## 交付检查

在 ModemManager 固定提交上重放 AFW 和三个蜂窝补丁，六个涉及的源码文件与手机编译树逐字节一致。编译产物去除调试节后的哈希与部署程序、入库 ELF 相同。现有 `finalize-rootfs.sh` 通过 `configure-gnss.sh` 安装该 ELF，`configure-volte.sh` 安装 IMS 恢复服务。仓库检查、镜像交付测试夹具及运行文件校验通过。
