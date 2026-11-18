# 构建集成

当前交付范围（2026-11-15）：内核、用户空间、首次安装、已有镜像续建与打包检查都按[项目记录](project-records.md)核对。代码和离线检查通过不等于新完整镜像已构建或刷入。

| 功能 | 首次安装 | 已有镜像更新 | 打包检查 |
| --- | --- | --- | --- |
| 相机与应用配置 | `configure-camera.sh` | `update-feature-image.sh camera`，源文件和内核 ABI 指纹 | `verify-camera-image.py` |
| NFC 工具及参考时钟 | `configure-nfc.sh` | `update-feature-image.sh nfc`，源码指纹 | `verify-nfc-image.py` |
| GNSS AFW 修复 | `configure-gnss.sh` | `update-feature-image.sh gnss`，运行文件与来源指纹 | `verify-gnss-image.py` |
| 基础应用、中文与旋转 | `configure-desktop.sh` + 默认软件安装 | 默认清单变化更新软件；`update-feature-image.sh desktop` 更新配置 | `verify-desktop-image.py` |
| 全部 Kbuild 模块和索引 | `finalize-rootfs.sh` | `update-kernel-image.sh` | `verify-kernel-modules-image.py`，逐文件对比当前构建输出 |

`update-feature-image.sh` 用私有挂载命名空间更新 root.img，先使旧封装标记失效，成功安装才写源指纹，卸载后再检查。它不会连接或刷写手机。旧镜像缺少 hexagonrpc、qrtr 等运行依赖时需先补齐或重建 rootfs；没有静默跳过依赖。默认软件安装仍沿用已有签名验证，旧软件仓库快照遇到 404 时应有计划地更新/重建，不能靠关闭签名或仅刷新数据库混装解决。

相机模块额外交付固件搜索路径中的 DTBO 与手动加载入口。默认启用已验证且无明显稳定性/耗电问题的功能，另三摄的开机/睡眠/功耗尚未验证，保留按需入口；NFC 不持续轮询或开机模拟，GNSS 不开机持续搜星。浏览器、Snapshot 与成像依赖默认安装，串流及专门调试工具见[可选应用](optional-apps.md)。新完整镜像尚未构建、未刷入。

## 已有集成与历史验证记录


首次构建请先读[构建指南](building.md)。下文解释脚本接入方式；带日期的实机与镜像结果为历史记录，本地 `logs/` 不随 Git 分发。

根文件系统自动扩容默认接入全新 rootfs 和已有镜像续建：`configure-grow-rootfs.sh` 安装脚本、启用 `negroni-grow-rootfs.service`，清除镜像内的完成标记；构建镜像仍为 5 GiB，不在构建机执行扩容。`build.sh` 根据内容指纹调用 `update-grow-rootfs-image.sh`，封装前核对文件、依赖、权限、开机链接及首次启动待执行状态，结果进入构建报告。

首次启动时，服务在本地文件系统就绪后、显示管理器之前，通过当前 `/` 的挂载源识别可写 ext4 和 userdata 分区，不依赖固定设备名。服务调用 `resize2fs` 在线扩容，确认容量及 UUID 后写入 `/var/lib/negroni-grow-rootfs/done.json`；后续启动跳过，失败时保留日志并在下次启动重试。它不调整分区表、不格式化、不改变 UUID 或保留块比例。手机上可用 `df -h /` 和 `journalctl -u negroni-grow-rootfs.service -b --no-pager` 检查结果。

已有完整 root.img 可单独补装并重新封装，无需重编内核：

```sh
sudo env IMAGE_DIR=images/7.3 LOG_DIR=logs/7.3 bash scripts/update-grow-rootfs-image.sh
IMAGE_DIR=images/7.3 LOG_DIR=logs/7.3 bash scripts/pack-images.sh
```

A/B 启动成功标记已接入全新 rootfs 和内核更新。单独修改服务时，`build.sh` 通过内容指纹调用 `update-boot-success-image.sh` 补装并使封装失效。服务启用但要求设备本地确认配置；镜像不预设任何设备的固件历史和 Linux 槽位，见[启动成功服务](boot-success.md)。

每次构建先补齐 `config/kernel/negroni.config` 中的 Oplus 电池模块和 ath11k 用户国家域支持，覆盖全新配置和旧配置续建，并检查 Kconfig 接受全部必需项。

Wi-Fi 默认关闭省电、采用设备和连接固定的本地 MAC，国家域按当前部署地点设为 CN。新 rootfs 与旧镜像续建均安装 `iw`、`wireless-regdb` 和签名；配置内容变更触发镜像更新，封装前检查依赖和配置一致性，见 [Wi-Fi 默认设置](wifi.md)。

音频：新 rootfs 由 `configure-audio.sh` 安装 AudioReach 拓扑 `/usr/lib/firmware/qcom/sm8450/OnePlus-10-Pro-tplg.bin`、ALSA UCM（`conf.d/sm8450/OnePlus-10-Pro.conf`、`OnePlus/negroni/HiFi.conf`），以及开机启用的 `negroni-call-audio.service`。随仓库提供的拓扑是 2026-11-14 实机用的通话语音 + 录音 + 放音文件（SHA-256 `5fb6fba6…`），不是 `scripts/build-audio-topology.sh` 单独生成的桌面拓扑。已有镜像在 `audio-sources.sha256` 失效时由 `update-audio-image.sh` 补装。封装前 `verify-audio-image.py` 核对文件与源码一致、服务已启用，以及 UCM 引用的 `alsa-ucm-conf` 共用片段存在；`check.sh` 只做源码一致性检查。声卡还需要内核 `ead3411b6e6` 的设备树和 `81637d2a07f3` 的语音图，见[音频说明](audio.md)和[通话语音](audio.md#通话语音)。这次只接入打包路径，新镜像未构建、未刷入。

传感器：`prepare-rootfs.sh` 保留 `iio-sensor-proxy`，并用 [PKGBUILD](../config/packages/hexagonrpc/PKGBUILD) 校验、重新打包 `xec` 的 ARM64 `hexagonrpc` 0.5.0-1。镜像安装本地修订版 `0.5.0-1.1`，手册页位于 `/usr/local/man`，`/usr/local/share/man` 符号链接由 `filesystem` 管理。全新 rootfs 由 `configure-sensors.sh` 安装 65 份原厂传感器 JSON、`sns_reg.conf`、开机从 persist 组装注册表和 `socinfo` 的 `negroni-sensor-files.service`、开机启用的 `hexagonrpcd-sdsp.service`、加速度计安装矩阵、手机上验证过的代理程序、开机写入 SMEM 项 130 并重启 SLPI 的 `negroni-smem-sensor.service`，以及陀螺仪发布程序 `negroni-gyro` 和开机启用的 `negroni-gyro.service`。已有镜像在 `sensors-sources.sha256` 失效时由 `update-sensors-image.sh` 补装，已有镜像缺 `hexagonrpc` 软件包时脚本停止。封装前 `verify-sensors-image.py` 核对 `hexagonrpc` 文件、原厂 JSON、陀螺仪程序、D-Bus 策略、单元和启用链接。注册表是工厂校准，只在开机时从本机 persist 拷贝。内核需要 `CONFIG_QCOM_OPLUS_SMEM_SENSOR=m`。见[传感器说明](sensors.md)。

USB 调试通道：`prepare-rootfs.sh` 安装 `dnsmasq`（NetworkManager 的 shared 模式要用）。全新 rootfs 由 `configure-usb-debug.sh` 安装 `usb-gadget.sh`、`usb-gadget.service`、让 NetworkManager 接管 `usb0` 的 udev 规则和 `usb-debug` 连接（`10.55.0.1/24`，权限 0600），并启用 `usb-gadget.service` 与 `serial-getty@ttyGS0.service`。已有镜像在 `usb-debug-sources.sha256` 失效时由 `update-usb-debug-image.sh` 补装，缺 `dnsmasq` 时脚本停止。封装前 `verify-usb-debug-image.py` 核对文件、权限和启用链接。gadget 依赖内核内建的 configfs NCM/ACM。见 [USB 调试](usb-debug.md)。

固件加载器、Plasma 快捷设置和电话/portal 元数据修复通过 `configure-runtime-fixes.sh` 接入全新 rootfs；已有镜像由 `build.sh` 根据源文件指纹触发增量更新，封装前校验文件、权限、运行依赖和安装清单。加载器修正 A/B 蓝牙路径、固件分组与目录链接；快捷设置修正尺寸未就绪时的分页计算，并移除模块的 qrc 优先声明，使修复后的 QML 实际生效。电话组件的三个真实总线名与 autostart 共用一个 systemd 用户服务；四个后台组件的隐藏应用描述安装到 `/usr/local/share/applications`，供 portal 识别。

安装前校验原版或已记录管理版本的内容，拒绝覆盖未知软件包版本和未记录的本地修改；被替换原件保存在 `/var/lib/negroni-runtime-fixes/backups/<内容哈希>/`，当前内容记录在 `installed-files.json`。软件包升级可能覆盖加载器、QML、qmldir 或 modem autostart，需要重新核验。已有镜像可单独更新并重新封装，无需重编内核，也不会自动刷机：

```sh
sudo env IMAGE_DIR=images/7.3 LOG_DIR=logs/7.3 bash scripts/update-runtime-fixes-image.sh
IMAGE_DIR=images/7.3 LOG_DIR=logs/7.3 bash scripts/pack-images.sh
```

蓝牙缺少 public address 的修复（`config/bluetooth/`，见[蓝牙说明](bluetooth.md)）也由同一机制安装。修复范围限于固件加载路径、蓝牙地址、快捷设置启动布局和桌面元数据；上游 C++ PaginateModel 清空末页时的边界缺陷仍需另行处理；不放宽 polkit 的进程保护，不修改 portal 对重复注册的身份校验，也不删除上游 Notifications 等待服务。

SIM 初始化默认允许无卡使用：`configure-modem-uim.sh` 将软件包脚本的无卡分支改为打印“无卡，跳过配置”并成功退出，基带和 QMI 错误仍按原逻辑报错。修复覆盖全新 rootfs 和已有镜像续建，源文件指纹触发更新，封装前校验脚本内容和权限；未知脚本版本拒绝自动修改。设备上单独升级 `msm-modem-uim-selection` 软件包可能覆盖此修改，需要重新应用修复。

开机后热插 SIM 卡由 `negroni-uim-hotplug.service` 处理：软件包脚本只在开机时运行一次，而基带不会自动为后插入的卡建立 provisioning session（卡停在 `detected`，ModemManager 报 `sim-missing`）。该服务每 5 秒查询一次卡状态，发现有卡但没有 Primary GW session 时重新运行选卡脚本，并在 ModemManager 没有可用 modem 时重启它。同一个 `configure-modem-uim.sh` 负责安装并启用，封装前校验文件内容、权限和启用状态。

VoLTE 由 `configure-volte.sh` 安装:电信在 LTE 上没有电路域语音,基带注册 IMS 时会向主机请求一条 `IMS` APN 的数据连接(QMI IMS 数据服务),没人应答时拨号直接返回 `InvalidArgument`。镜像带上 postmarketOS 的 81voltd 来应答,以 `negroni-81voltd.service` 随 ModemManager 启停。81voltd 是在手机上编译的预编译二进制,来源、补丁和校验和记录在 `config/volte/81voltd.source`;补丁做两件事:基带会连续请求两次,避免对同一承载并发连接(ModemManager 1.24.2 会因此段错误);承载被外部断开时退出,由 systemd 重启后让基带重新请求。另装一条 polkit 规则禁止 `spacebar-daemon` 控制承载:Spacebar 6.3.x 在每次新增承载时会删除其它所有承载,导致数据和 IMS 互相挤掉。

IMS 承载自动恢复由同一个脚本安装:`config/volte/negroni-ims-recovery.py` 到 `/usr/local/libexec/`、配置到 `/etc/negroni-ims-recovery.conf`、`negroni-ims-recovery.service` 到 systemd 并随 ModemManager 启用。该服务只查询 ModemManager 的承载状态,不改 81voltd 二进制;连续丢失 IMS 承载时先重启 81voltd,仍失败且数据承载在线时才有上限地重启 ModemManager,细节与限制见[基带说明](modem.md#ims-承载自动恢复2026-11-13)。源文件指纹与上述文件一起记录,`verify-volte-image.py` 封装前核对内容、权限和两个启用链接。全新 rootfs 由 `finalize-rootfs.sh` 调用 `configure-volte.sh` 安装;`build.sh` 以 `volte-sources.sha256` 指纹在已有镜像续建时触发 `update-volte-image.sh`,之后重新封装。恢复服务已在手机上部署,两级动作、开机自愈与拨号均完成实机验证(见[基带说明](modem.md#ims-承载自动恢复2026-11-13));全新完整镜像仍未重建。

VoLTE 已知限制:2026-11-12 只验证过拨出电话能到达振铃/接通状态，当时通话音频没有接通。2026-11-14 语音图已经由对端听过，并已接入 `configure-audio.sh`，见[通话语音](audio.md#通话语音)。来电和短信未测试。关闭移动数据时 NetworkManager 会断开所有承载,此后 ModemManager 1.24.2 在重新连接时大概率段错误(4 轮开关崩溃 4 次),随后自动重启并在约 20 秒内恢复数据和 IMS;根因在 ModemManager 的复用链路处理,尚未定位。

Docker 内核支持已接入每次构建：`configure-docker-kernel.sh` 在基础配置上合并 `config/kernel/docker.config`，随后运行 `olddefconfig` 和必需项检查。已有 `.config` 同样会更新。正常 Kbuild 生成的 nftables 兼容、IPv4/IPv6 FIB 和 NAT 模块通过内核产物指纹进入 rootfs；打包前核对镜像内核、模块哈希、依赖索引和自动加载别名，结果写入构建报告。镜像中的 Docker 软件按需安装，见[Docker 内核支持](docker.md)。

CPU 调度已默认集成：固定内核补齐 8 核能力和功耗模型；全新 rootfs 通过 `configure-cpu-performance.sh` 安装均衡和性能服务，默认启用 schedutil / 无 Boost 的均衡服务。已有 rootfs 通过源文件指纹触发 `update-cpu-performance-image.sh`，更新服务并重新打包。构建及封装阶段分别检查 DTB 参数、镜像文件和开机链接，构建报告记录结果。详见 [CPU 默认构建与恢复](cpu-performance.md#默认固件构建与续建)。

屏幕默认设置已接入全新 rootfs 与已有镜像续建：桌面降低亮度时间关闭、关闭屏幕时间 5 分钟、休眠时间关闭，三种供电模式一致；SDDM 登录前单独运行 PowerDevil，空闲 2 分钟熄屏、电源键切换亮灭屏。`finalize-rootfs.sh` 安装 `/etc/xdg/powerdevilrc`、SDDM 启动脚本和独立配置、logind 短按不关机配置；`build.sh` 根据配置及脚本的内容指纹调用 `update-screen-defaults-image.sh`，更新后重新打包。`pack-images.sh` 强制检查镜像内配置与源文件一致、权限正确、运行依赖可执行，并把配置值写入构建报告。桌面用户已有设置优先；锁屏后的独立熄屏计时沿用上游默认值。配置键、验证范围与单独更新命令见[屏幕默认设置](screen-defaults.md)。

充电限制已同时接入全新 rootfs 与已有镜像续建：`prepare-rootfs.sh` 显式安装 Python，`finalize-rootfs.sh` 安装服务与默认配置；`build.sh` 每次运行增量 Kbuild，并用内核产物指纹、服务源文件校验值判断是否调用 `update-kernel-image.sh`。更新会复制模块、内核并重建 initramfs，再使旧的封装完成标记失效。每次构建安装后服务均为 `disabled`，默认开始 75%、停止 80%。

2026-09-16 的产物统一在 `images/7.3-rc2/`，日志在 `logs/7.3-rc2/`，未刷入手机。`pack-images.sh` 会检查镜像中的驱动、配置、服务内容与默认关闭状态；构建报告记录内核提交及充电配置。内核改动已提交到本地 `7.3-rc2` 分支的 `2c092365fd5c`；配套服务、配置、构建脚本和文档已纳入本父仓库，`linux/` 作为固定提交的子模块，未推送提交另有 [Git bundle](../patches/linux/README.md) 备份。使用方式、实现边界和迁移源码说明见 [充电限制说明](charge-limit.md)。

`build.sh` 支持把内核分支和镜像产物隔离到对应目录。构建 `7.3`：

```sh
./build.sh 7.3
```

产物写入 `images/7.3/`，日志和校验记录写入 `logs/7.3/`。脚本通过 `IMAGE_DIR`、`LOG_DIR` 传递目录给各阶段；未指定分支时保留原来的 `images/`、`logs/` 默认路径。

最终 rootfs 的 `/etc/sddm.conf.d/10-mobile.conf` 从 [config/sddm/10-mobile.conf](../config/sddm/10-mobile.conf) 安装，清空 `InputMethod`，设置 `GreeterEnvironment=QT_WAYLAND_SHELL_INTEGRATION=layer-shell`，通过 `negroni-sddm-compositor` 向 KWin 传入 `--inputmethod /usr/bin/plasma-keyboard`。配置及启动脚本均纳入屏幕默认值指纹，已有 `rootfs.complete` 的镜像续建时也会更新。

新镜像默认安装 OpenSSH 并启用 `sshd.service`，监听 TCP 22。使用现有 `oneplus` 账号和图形登录密码连接，也支持该账号的 SSH 公钥；禁用 root 远程登录和空密码。配置源文件为 `config/ssh/00-negroni.conf`，构建时安装到 `/etc/ssh/sshd_config.d/00-negroni.conf`。

手机连接 Wi-Fi 后，在同一局域网的电脑上执行：

```sh
ssh oneplus@手机IP
```

手机 IP 可在网络设置或路由器的 DHCP 列表中查询，也可在手机终端执行 `ip -4 addr`。SSH 随系统启动，不需要先登录图形桌面，但镜像没有预置 Wi-Fi 凭据，首次仍需连接网络。此配置使用局域网，不会把 USB 数据线自动变成 SSH 网络连接。

镜像不包含 SSH 主机私钥；首次启动由 Arch 的 `sshdgenkeys.service` 生成本机密钥，再启动 sshd。`scripts/configure-ssh.sh` 检查最终生效配置、账号、自启状态和镜像中不存在共享主机密钥。`scripts/verify-ssh-image.py` 还可在隔离网络中测试 ARM sshd；早期 QEMU 测试因不支持该版本 sshd 的 seccomp 沙箱，仅通过配置、监听和现有密码哈希检查。该限制保留在模拟测试记录中，镜像沙箱设置未因此修改；最近刷入版本的默认 SSH 已由用户在真机上确认生效。

对已有完整镜像，`build.sh` 检测到缺少 `ssh.complete` 时会调用 `scripts/enable-ssh-image.sh` 补装 OpenSSH，再重新封装镜像、生成 sparse 和 SHA256SUMS，无需重新编译内核。提权时显式传递 `IMAGE_DIR`、`LOG_DIR`，确保处理对应分支目录。也可以手动运行：

```sh
sudo env IMAGE_DIR=images/7.3 LOG_DIR=logs/7.3 bash scripts/enable-ssh-image.sh
IMAGE_DIR=images/7.3 LOG_DIR=logs/7.3 bash scripts/pack-images.sh
```

2026-09-15 22:33，已将包含键盘修复和默认 SSH 的镜像重新刷入手机并执行重启，见 `logs/flash-7.3-rc2-ssh-2026-09-15-2228/result.json`（本地文件）。用户随后确认“ssh默认生效”，见 `logs/flash-7.3-rc2-ssh-2026-09-15-2228/ssh-hardware-verification.json`（本地文件）。该确认对应添加常用软件前的 617 包镜像。对于其他尚未启用 SSH 的旧系统，也可在手机联网后直接安装并启动 SSH：

```sh
sudo pacman -S --needed openssh
sudo systemctl enable --now sshd
```

以上两条命令使用 Arch 的默认 SSH 配置，已支持普通账号密码登录；完整镜像另外限定为 `oneplus` 账号并禁用 root 登录。

常用软件统一维护在 [config/packages/common-tools.txt](../config/packages/common-tools.txt)：`nano`、`zip`、`unzip`、`curl`、`wget`、`htop`、`rsync`、`git`、`less`、`file`、`tree`、`jq`、`tmux`、`ripgrep`、`fd`、`bash-completion`、`lsof`、`strace`、`which`。`build.sh` 在 SSH 配置之后、打包之前调用 [scripts/install-common-tools-image.sh](../scripts/install-common-tools-image.sh)，为最终 rootfs 安装软件并执行 ARM64/QEMU 检查。

2026-11-17 将 `dolphin`、`kclock`、`kalk`、`koko`、`kdeconnect` 加入同一默认清单。安装阶段核对五个应用的入口程序，封装前 `verify-desktop-image.py` 核对软件包数据库。手机已通过 USB SSH 安装并用 `pacman -Q` 确认五包存在；图形启动、触屏操作、KDE Connect 配对和闹钟唤醒尚未实测。新完整镜像尚未构建、刷入。

2026-11-18 将 `krdp` 加入默认软件清单。新建和续建均由 `configure-desktop.sh` 安装下拉项、systemd 用户服务的会话与 TLS 配置，以及认证默认值。监听地址沿用 KRDP 的默认行为，续建会移除旧的 Negroni USB 监听覆盖。封装前核对软件包、启动程序、配置、下拉项和禁用自启状态。证书与私钥由用户首次开启服务时生成。离线交付检查通过；旧 rootfs 副本的包下载超时，两处镜像站对该副本索引中的 KRDP 6.8.2 包均返回 404。新完整镜像未构建、未刷入。[下拉快捷开关](quick-settings.md)

系统初始语言由 [config/locale/locale.conf](../config/locale/locale.conf) 指定为 `zh_CN.UTF-8`。全新 rootfs 在 `finalize-rootfs.sh` 中生成中英文 locale；已有镜像的源码指纹变化触发 `update-locale-image.sh`，重新生成 locale 并使封装标记失效。`pack-images.sh` 检查 `/etc/locale.conf`、`locale.gen` 和生成的中文 locale。2026-11-17 手机已生成 `zh_CN.utf8` 并将系统默认值改为简体中文；`oneplus` 账号原有的 Plasma 中文设置保持。当前已运行服务不会自动切换语言，下一次正常启动后生效；SDDM 与完整新镜像的中文显示未测。

完成后将清单写入 `logs/7.3/common-tools.list`；它与配置清单一致时续建跳过该阶段，清单改变时重新安装、验证并打包。从清单删除条目不会自动卸载软件。脚本使用现有仓库数据库执行 `pacman -S --needed`，不执行整套系统升级。构建环境和最终镜像均使用 [config/pacman/mirrorlist](../config/pacman/mirrorlist)，优先选择 `de3.mirror.archlinuxarm.org`，加拿大镜像站为备用，保留 TLS 和包签名校验。

2026-11-12 将 `noto-fonts-cjk` 加入同一清单，补齐中文等 CJK 字形；普通 `noto-fonts` 不包含这部分。全新构建会安装，已有镜像续建会因清单变化重新运行安装阶段。本机已通过 USB SSH 补装并验证 Qt/Pango 中文渲染，新完整镜像未构建，详见 [字体说明](fonts.md)。

已有镜像可手动更新：

```sh
sudo env IMAGE_DIR=images/7.3 LOG_DIR=logs/7.3 bash scripts/install-common-tools-image.sh
IMAGE_DIR=images/7.3 LOG_DIR=logs/7.3 bash scripts/pack-images.sh
```

2026-09-15 22:46，包含常用软件的本地镜像已重新打包至 `images/7.3-rc2/`，rootfs 共 639 个包。19 项常用软件全部存在，ZIP 压缩解压、rsync 复制、JSON 处理、文件搜索和 Git 初始化通过，见 `logs/7.3-rc2/common-tools-verification.json`（本地文件） 和 `logs/7.3-rc2/build-result.json`（本地文件）。本次新增 16 个工具包及 6 个依赖，已有包版本保持不变，只有 `root.img` 和 `sparse_root.img` 的哈希改变。**该软件更新尚未刷入手机，手机仍运行前述已确认 SSH 生效的版本。**
