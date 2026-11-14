# 传感器（加速度、陀螺仪、磁力、光线、距离）

状态日期：2026-11-14。设备为 OnePlus 10 Pro NE2210（项目 20846，SM8450）。传感器不在应用处理器的 I²C 上，而在 SLPI（`remoteproc0`，固件 `slpi.mdt`，QRTR 节点 9）。Snapdragon Sensor Core 是 QMI 服务 400。本次没有刷写分区，也没有整机重启；只重启过 SLPI。

原厂校准和 ODM `sensor_config.json` 对应的器件是：加速度计 / 陀螺仪 ICM-4x6xx（SPI，bus instance 3），磁力计 MMC56x3x（I²C instance 2，地址 0x30），前向光线 + 距离 TCS3701（通用 `sns_alsps`，I²C instance 5，`slave_config` 70，中断 89，电源 `sensor_vdd` 与 `sensor_vddio`）。后置色温传感器是 TCS3408，不是这次的前向光线传感器。

## 已在手机上接通的部分

udev 规则、SMEM 描述和换过的 `iio-sensor-proxy` 已接入镜像打包。`prepare-rootfs.sh` 安装发行版 `iio-sensor-proxy`，`configure-sensors.sh` 再换成手机上这份（SHA-256 `babc9af3…`），对应补丁是 [iio-sensor-proxy-3.9-negroni.patch](../config/sensors/iio-sensor-proxy-3.9-negroni.patch)。`hexagonrpc` 0.5.0 和传感器文件也已接入：`prepare-rootfs.sh` 从 `xec` 源安装 `hexagonrpc`；`configure-sensors.sh` 安装 65 份原厂传感器 JSON 和改过的 `sns_reg.conf`（[来源与改动](../config/sensors/qcom.source)），以及开机启用的 `hexagonrpcd-sdsp.service`。注册表是工厂校准，不进 Git。开机时 `negroni-sensor-files.service` 从 `msm-firmware-loader` 挂载的本机 persist 拷贝注册表，把 alsps 的总线和中断改成 2 / 14，补上 `socinfo`，组装到 `/run/negroni-sensors` 再交给 `hexagonrpcd`。2026-11-14 23 时在手机上把这个脚本指向 `/tmp` 试跑，生成的配置、`sns_reg.conf`、329 个注册表文件和 `socinfo` 与手机正在服务的 `/usr/share/qcom` 一致（alsps 只有 JSON 空白不同）。`hexagonrpcd` 改服务 `/run/negroni-sensors` 之后的实机启动未测。桌面 `autoRotation=Always` 写在用户自己的 `kwinoutputconfig.json` 里，仍只在本机。打包路径已接入，新镜像未构建、未刷入。

- 安装了 `hexagonrpc` 0.5.0，并用 `hexagonrpcd-sdsp.service` 向 `/dev/fastrpc-sdsp` 提供传感器文件。虚拟文件系统只映射 `/vendor/etc/sensors/config`、`/persist/sensors/registry/registry` 和 `/sys/devices/soc0`，没有 `/odm`。因此把原厂 `sns_reg_config` 的配置目录改成 `/vendor/etc/sensors/config`，并把 ODM 的 `waipio_qrd_*.json` 放进 `/usr/share/qcom/sensors/config`。`socinfo` 写成 `hw_platform=QRD`、`soc_id=457`。
- SLPI 重启后会打开 `waipio_qrd_alsps.json`、`alsps_platform.config`、`icm4x6xx_0_platform.config` 和 `mmc56x3x_0_platform.config`。注册表写入被只读文件系统拒绝，已有校准文件仍可读。
- `ssccli` 能读到加速度计和磁力计。手机平放、屏幕朝上时加速度约 X 0.06、Y 0.08、Z 9.82 m/s²；磁力计约 X −188、Y −9、Z 143 µT。固件给出的安装矩阵全是 0，`libssc` 退回单位矩阵。芯片的 +X/+Y 和面板相反，+Z 与屏幕一致。
- `iio-sensor-proxy` 3.9 已安装。发行版 udev 只给 SSC 登记光线和磁力计，本机另加 `/etc/udev/rules.d/81-negroni-ssc.rules`（仓库副本 [81-negroni-ssc.rules](../config/sensors/81-negroni-ssc.rules)），把 `ssc-accel` 和 `ssc-proximity` 加到 `fastrpc-sdsp*`，并把 `ACCEL_MOUNT_MATRIX` 设为 `-1, 0, 0; 0, -1, 0; 0, 0, 1`。系统总线上 `HasAccelerometer=true`。`configure-sensors.sh` 会安装这条规则。
- 从 SDDM 图形会话的 cgroup 里认领加速度计成功。平放时 `AccelerometerOrientation` 为 `undefined`，这是倾斜不够时的正常结果，不是认领失败。SSH 会话没有 seat，polkit 会拒绝认领。
- `~/.config/kwinoutputconfig.json` 里 DSI-1 的 `autoRotation` 已从 `InTabletMode` 改为 `Always`。2026-11-14 18:16 登录后的 KWin 已认领加速度计，`kscreen-doctor` 报告 `Auto Rotate Policy: always`。手机平放朝上，方向保持 `undefined`，屏幕保持横向 965×432。
- 竖持时加速度约为 X 1.3、Y 9.5、Z 2.2 m/s²，但 `AccelerometerOrientation` 仍停在 `undefined`，画面不转。原因是 `iio-sensor-proxy` 在 KWin 认领加速度计时还没打开采样，认领被记下后没有人再调用 `driver_set_polling`。本机已换上自行编译的 3.9（`/usr/lib/iio-sensor-proxy`，原文件备份为 `iio-sensor-proxy.stock`）：传感器在拥有 D-Bus 名之前打开，已有认领会补上采样。发行版软件包和镜像都还是原版。修好后同一时刻的读数能对上方向。单位矩阵下 X 8.49、Y 0.01、Z 4.59 m/s² 被报成 `left-up`。
- KWin 在输出 DPMS 不是 On 时直接停用自动旋转。18:57 内核 `card0-DSI-1` 的 dpms 为 `Off`，策略虽然显示 `always`，方向变化也不会改画面。打开 DPMS 后，`left-up` 被应用到旋转 2（横向 965×432）。当时背光只有 1/4095，已调到约 30%（1229/4095），否则画面几乎是黑的。
- 19:01 用户确认会跟着转，但上下左右都反了。当时屏幕后倾，左边框在下、右边框在上，原始读数仍是 X 约 +8.49，方向 `left-up`、旋转 2。这是绕屏幕法线差了 180°。加上上述安装矩阵并重启代理后，同一姿势变为 `right-up`，`kscreen-doctor` 旋转值从 2 变为 8，几何尺寸仍是横向 965×432。20:20 用户确认修正后的画面方向正确。

## 光线和距离

原厂 `dtbo` 的 `oplus,sensor-devinfo` 把光线和距离标成 TCS3701（`sensor-name = 2`）、总线 2、中断 14，`als-type = 4`。`oplus_sensor.ko` 把这组数据写进 SMEM 项 130（`SMEM_SENSOR`，5140 字节）；总线、方向、中断为 `0xff` 才表示退回注册表。注册表里的总线 5、中断 89 是 QRD 模板。2026-11-14 18:21 只改注册表并重启 SLPI 时，加速度计仍在，光线和距离没有发布。

2026-11-14 22:21 用临时模块分配了这项共享内存。布局与原厂模块的 5140 字节一致：12 个物理传感器、每个 2 路、8 个虚拟算法。只填写光线（类型 3）和距离（类型 4）；其余传感器的 `sensor_name` 保持 0，总线、方向、中断写成 `0xff`。写入后核对与文件一致，然后只重启 SLPI，整机 boot id 未变。

22:22 `ssccli` 读到光线约 291–304 lux，距离为 `FAR`。22:27 用户盖住手机后，光线降到约 42–43 lux，距离变为 `NEAR`。22:28 进一步遮严后，光线在 0 和 1 lux 之间，距离仍是 `NEAR`。加速度计仍约 Z 9.82 m/s²，磁力计仍约 X −194、Y −16、Z 152 µT，安装矩阵仍是全 0。SLPI 停止时 `iio-sensor-proxy` 失败退出，手动拉起后 `HasAccelerometer`、`HasAmbientLight`、`HasProximity` 都是 true。SSH 没有 seat，polkit 拒绝认领，所以总线上的 `LightLevel` 仍是 0；这不是传感器没出数。

这项共享内存在内存里，重启手机会丢掉。内核 `472db17c1a3b` 提供 `smem_sensor`，镜像用 `negroni-smem-sensor.service` 在开机时写入 5140 字节并按固件名 `slpi.mdt` 重启 SLPI。SSH 没有 seat，总线上的 `LightLevel` 仍会是 0。新镜像未构建、未刷入。

## 还没对上的部分

桌面自动旋转策略是 `always`。平放朝上时方向是 `undefined`，KWin 保留手动变换。DPMS 关闭时也不会跟着转。2026-11-14 19:01 安装矩阵取反 X/Y 后，右边框在上的姿势从 `left-up`（旋转 2）改为 `right-up`（旋转 8）。20:20 用户确认这个方向正确。登录界面那次 KWin 启动较早，当时仍显示 `incapable`；登录后的会话已经认领到加速度计。

磁力计有读数，桌面罗盘和安装方向尚未对照实机方位。

## 陀螺仪

ICM-4x6xx 的角速度和加速度计走同一条 SLPI 通道。2026-11-14 22:51 手机静止时，`negroni-gyro` 读到屏幕坐标下大约 X −0.009、Y 0.003、Z 0.013 rad/s。`libssc` 命令行把单位印成 m/s，那是加速度计文案；静止时大约 0.01 的量级是 rad/s 零偏。

程序按加速度计已经确认的方向把芯片坐标换成屏幕坐标：X、Y 取反，Z 保持。源码是 [negroni-gyro.c](../config/sensors/negroni-gyro.c)，手机上编译的二进制和校验记在 [negroni-gyro.source](../config/sensors/negroni-gyro.source)。`configure-sensors.sh` 把它装到 `/usr/local/sbin/negroni-gyro`，并启用 `negroni-gyro.service`。

普通用户可以读 `/run/negroni/gyro`，一行三个数，单位 rad/s。系统总线 `org.negroni.Gyroscope` 的 `GetAngularVelocity` 返回同样三个数。22:52 这台手机上文件和 D-Bus 都能读到，加速度计同时仍约 Z 9.80 m/s²。用手转动来核对三个轴的方向还没有做。

全新 rootfs 和已有镜像的下一次构建都会装上这个程序并启用服务，`hexagonrpc` 和开机组装的注册表也随同一脚本进镜像。已有镜像里没有 `hexagonrpc` 软件包时，`configure-sensors.sh` 会报错停止。新镜像未构建、未刷入。
