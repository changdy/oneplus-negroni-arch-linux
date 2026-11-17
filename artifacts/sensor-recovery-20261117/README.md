# 2026-11-17 光线与距离传感器恢复

NE2210，内核 `7.3.0-sm8450+`，USB SSH 实机操作。首次部署与服务链测试阶段的整机 boot ID 为 `057f9772-204a-4df9-ac8d-60323fbe3293`；该阶段只重启 SLPI 和传感器相关服务，没有重启手机、刷写分区或写入原厂 persist 校准。后续经用户明确同意做了一次整机正常重启，结果单列如下。原始日志位于忽略的 `logs/sensor-fix-20261117/`、`logs/sensor-reboot-20261117/`。手机时钟为 1970 年，以下日期使用电脑的北京时间，事件使用 journal monotonic 秒数。

## 原因与交付

此前代理只报告加速度计，光线、距离均为 false。手机缺少 `smem_sensor.ko`、`negroni-smem-sensor.service` 和文件组装服务，仍使用手工部署的 `/usr/share/qcom` 布局。SLPI 缺少 TCS3701 的 SMEM 板级描述，旧代理退出后也不会自动恢复。

本轮安装并启用了仓库已有的传感器文件组装和 SMEM 入口，部署到 `/run/negroni-sensors` 布局。每次启动从本机 persist **读取并复制**注册表到 RAM，在副本中修正 bus / IRQ，不写回原厂分区。补齐并验证：

- SMEM 脚本校验 5140 字节负载，写入后逐字节回读比较，按固件名识别 SLPI，重启后等待 FastRPC 节点。
- 桌面代理和陀螺仪的启动排在 SMEM 服务之后。代理即使以状态 0 报“没有传感器”退出，也每 3 秒自动重试；启动超时放宽到 90 秒。
- SMEM 单元使用 `Wants` 拉起文件服务，不能使用 `Requires`：SLPI 重启必然让文件服务的旧 FastRPC 连接退出，`Requires` 会把正在执行的 SMEM 脚本一并终止。首次部署复现了这个问题，改为 `Wants` 后整条链路复测通过。
- 安装器、来源指纹和离线镜像核对加入代理的 systemd drop-in；缺失该文件的镜像会被拒绝。三个无扩展名的 shell 脚本固定为 LF。

内核驱动已在固定提交 `cba22a622ac0b73d7266aecbf2567273218a81ce` 及恢复 bundle 中，不需新增内核补丁。本机旧构建输出没有启用它，因此用该树及其现有 Kbuild 输出单独编译模块；编译器和 vermagic 与运行内核匹配，没有强制加载。模块 SHA-256 为 `cb8b50f7e001efaff2e916c3953093c8753350f90151f8e08f661d7c38208ed2`，安装于 `/usr/lib/modules/7.3.0-sm8450+/updates/smem_sensor.ko` 并执行 depmod。模块产物保存在忽略的日志目录，不纳入 Git。下次完整构建仍由已有的 `CONFIG_QCOM_OPLUS_SMEM_SENSOR=m` 和标准 Kbuild 安装链路交付。

## 实机结果

1. 首次恢复后，`HasAccelerometer`、`HasAmbientLight`、`HasProximity` 全为 true。SSC 直接采样的光线约 102–111 lux，距离 FAR；加速度计约 Z 9.8 m/s²，陀螺仪持续出数。
2. 用户按提示遮住屏幕顶部约 10 秒后移开。90 秒 SSC 采样收到 438 个光线样本，范围 0–118 lux；距离完整记录 `FAR → NEAR → FAR`。同时通过桌面代理的 `monitor-sensor` 观察到约 103 lux 降至 0–1 lux、near=1，移开后约 109–111 lux、near=0，证明 SSC 与桌面 D-Bus 两层都已恢复。监控进程由预设 timeout 结束。
3. 停止文件组装、文件服务、SMEM、代理和陀螺仪，再仅启动代理与陀螺仪，由依赖自动拉起其余服务，复测启动链路。约 1050 秒 SMEM 初始化完成；代理首次发现尚无传感器而正常退出，1110.7 秒自动重试后成功，三个标志再次为 true，SMEM 回读一致，SSC 再次读到约 105–110 lux / FAR。文件服务一次重启属于 SLPI 连接重建，之后稳定。
4. 陀螺仪在 SLPI 恢复期间仍有三次无样本重试，之后 active 并持续出数；本轮没有宣称修复原有陀螺仪就绪时间和错误处理问题。

## 检查与边界

`systemd-analyze verify`、`bash scripts/check.sh`、`sudo bash scripts/check-image-delivery.sh`、`git diff --check` 通过；离线测试包含缺代理启动配置时拒绝交付。小型 ext4 测试仅验证安装与缺件检查，不代替实机。

手机持久化服务已部署并启用，服务链路重新激活和手遮实测通过；后续正常重启的光线/距离自动恢复通过，但加速度计/陀螺仪未通过。**完全断电冷启动、完整深度睡眠恢复、自动亮度实际调节、通话贴耳熄屏、长时间功耗及新完整镜像未测**；新完整镜像未构建、未刷入。

## 同日整机正常重启验证

用户明确要求重启后，先只读检查主/备 GPT 的 CRC、A/B 属性，并解压两个 boot 分区中的内核，确认当前完整内核版本唯一匹配 `boot_b`。B 槽 `Active=1 / Successful=1 / Bootable=1`，重启前后不变。属性解释对照 [qbootctl 的定义](https://github.com/linux-msm/qbootctl/blob/main/gpt-utils.h)；没有调用 qbootctl、写 GPT、切槽或刷写分区。

执行一次 `systemctl reboot`，新 boot ID 为 `c9635d98-a8d6-4dc9-ac5a-897e0523a88f`。USB SSH 约 44 秒后首次恢复，随后一度断连，用户提示再次检查时已重新连通，仍为同一 boot ID。

- 自动初始化通过：9.784–10.054 秒完成文件组装，10.588 秒模块分配新的 SMEM 项，11.023 秒板级初始化成功；SMEM 回读与负载一致。文件服务因 SLPI 重启自动重建连接一次。
- 光线和距离通过：代理 70.970 秒自动启动成功，`HasAmbientLight=true`、`HasProximity=true`；SSC 实际读到 116–120 lux 和 FAR。此阶段没有手工重启或拉起传感器服务，也没有再次遮挡；遮挡响应依据前一阶段的用户实测。
- **加速度计和陀螺仪未通过**：代理为 `HasAccelerometer=false`，陀螺仪先三次无样本超时，此后反复 SIGSEGV；155 秒时重试计数已到 18。不能沿用重启前“两者仍有读数”的结论，也不能仅因光线/距离恢复就判定整个传感器栈通过。IMU 底层未发布、代理发现时序与已知错误处理缺陷的关系尚未定位；本次只验证，没有修改这些服务。
- 另有 34.013 秒 UPower 请求休眠，日志记录 deep 进入/退出；电池仍 Charging / 0%。ModemManager 为 active 但无设备。不能把休眠、USB 断连和 IMU 故障的先后顺序直接认定为因果，完整睡眠与蜂窝恢复仍未验收。

## 本机恢复资料

部署前的文件与单元保存在手机 root 专用目录 `/var/lib/negroni-sensor-backup-20261117/`，包含 `files-before.tar.gz`、旧文件清单和写入前的 `smem-before.bin`；该备份没有收入 Git。需要回退时先停止代理、陀螺仪、SMEM 和文件服务，按清单删除本轮新增文件、恢复归档，写回 SMEM 备份并仅重启 SLPI，再 reload / 恢复原服务。不要仅恢复旧文件却保留指向新路径的 enabled 单元，也不要为回退而重启整机或刷写分区。
