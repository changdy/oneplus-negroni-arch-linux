# NFC 和陀螺仪下拉开关实机记录

2026-11-17，NE2210，内核 `7.3.0-sm8450+`，Plasma Mobile `6.8.2-1`。经 USB NCM SSH 手工安装了快捷项、Polkit 策略、受限控制程序、NFC 模块黑名单，并把两项加入 `oneplus` 的 Plasma Mobile 快捷设置列表。没有重启手机或刷写分区。

验证结果：

- QML `qmllint` 无语法错误；在手机 Qt QML 运行环境中，`Plasma5Support.DataSource` 的 `executable` 引擎执行了状态命令，`data["stdout"]` 返回 `on`，`MobileShell.ShellUtil.executeCommand` 执行了测试命令。
- Polkit 识别 `org.negroni.hardware.control`，仅 `active` 本机会话隐式允许；`inactive` 与 `any` 均为 `no`。未在已登录图形会话中实际点击按钮。
- NFC 从 `off → on → off`，驱动绑定时 `/proc/interrupts` 出现 GPIO 46 的 `nxp-nci_i2c` 行，关闭后驱动链接及中断行消失。测试开始时中断计数为 0，本轮未复现先前的中断风暴；打开后的读标签、长时间空闲与功耗未测。
- 陀螺仪从 `off → on → off`，服务状态与开机链接随之变化；最终 `inactive`、`disabled`。没有在本轮核对开启期间的实际角速度样本。
- 最终手机状态为 NFC `off`、陀螺仪 `off`；`/etc/modprobe.d/nxp-nci-off.conf` 已安装。后续整机重启是否保持 NFC 关闭还未验证。

新的完整镜像未构建、未刷入。手机下拉栏的实际显示、触控操作、Polkit 活动会话授权、重启后状态和节电量未测。离线安装与缺件拒绝测试分别由 `tests/test-desktop-image.py`、`tests/test-sensors-image.py` 覆盖。
