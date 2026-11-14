# 传感器（加速度、磁力、光线、距离）

状态日期：2026-11-14。设备为 OnePlus 10 Pro NE2210（项目 20846，SM8450）。传感器不在应用处理器的 I²C 上，而在 SLPI（`remoteproc0`，固件 `slpi.mdt`，QRTR 节点 9）。Snapdragon Sensor Core 是 QMI 服务 400。本次没有刷写分区，也没有整机重启；只重启过 SLPI。

原厂校准和 ODM `sensor_config.json` 对应的器件是：加速度计 / 陀螺仪 ICM-4x6xx（SPI，bus instance 3），磁力计 MMC56x3x（I²C instance 2，地址 0x30），前向光线 + 距离 TCS3701（通用 `sns_alsps`，I²C instance 5，`slave_config` 70，中断 89，电源 `sensor_vdd` 与 `sensor_vddio`）。后置色温传感器是 TCS3408，不是这次的前向光线传感器。

## 已在手机上接通的部分

udev 规则已纳入仓库。镜像构建还没有安装它，hexagonrpc、注册表和换过的 `iio-sensor-proxy` 也仍只在本机。

- 安装了 `hexagonrpc` 0.5.0，并用 `hexagonrpcd-sdsp.service` 向 `/dev/fastrpc-sdsp` 提供传感器文件。虚拟文件系统只映射 `/vendor/etc/sensors/config`、`/persist/sensors/registry/registry` 和 `/sys/devices/soc0`，没有 `/odm`。因此把原厂 `sns_reg_config` 的配置目录改成 `/vendor/etc/sensors/config`，并把 ODM 的 `waipio_qrd_*.json` 放进 `/usr/share/qcom/sensors/config`。`socinfo` 写成 `hw_platform=QRD`、`soc_id=457`。
- SLPI 重启后会打开 `waipio_qrd_alsps.json`、`alsps_platform.config`、`icm4x6xx_0_platform.config` 和 `mmc56x3x_0_platform.config`。注册表写入被只读文件系统拒绝，已有校准文件仍可读。
- `ssccli` 能读到加速度计和磁力计。手机平放、屏幕朝上时加速度约 X 0.06、Y 0.08、Z 9.82 m/s²；磁力计约 X −188、Y −9、Z 143 µT。固件给出的安装矩阵全是 0，`libssc` 退回单位矩阵。芯片的 +X/+Y 和面板相反，+Z 与屏幕一致。
- `iio-sensor-proxy` 3.9 已安装。发行版 udev 只给 SSC 登记光线和磁力计，本机另加 `/etc/udev/rules.d/81-negroni-ssc.rules`（仓库副本 [81-negroni-ssc.rules](../config/sensors/81-negroni-ssc.rules)），把 `ssc-accel` 和 `ssc-proximity` 加到 `fastrpc-sdsp*`，并把 `ACCEL_MOUNT_MATRIX` 设为 `-1, 0, 0; 0, -1, 0; 0, 0, 1`。系统总线上 `HasAccelerometer=true`。镜像构建还没有安装这条规则。
- 从 SDDM 图形会话的 cgroup 里认领加速度计成功。平放时 `AccelerometerOrientation` 为 `undefined`，这是倾斜不够时的正常结果，不是认领失败。SSH 会话没有 seat，polkit 会拒绝认领。
- `~/.config/kwinoutputconfig.json` 里 DSI-1 的 `autoRotation` 已从 `InTabletMode` 改为 `Always`。2026-11-14 18:16 登录后的 KWin 已认领加速度计，`kscreen-doctor` 报告 `Auto Rotate Policy: always`。手机平放朝上，方向保持 `undefined`，屏幕保持横向 965×432。
- 竖持时加速度约为 X 1.3、Y 9.5、Z 2.2 m/s²，但 `AccelerometerOrientation` 仍停在 `undefined`，画面不转。原因是 `iio-sensor-proxy` 在 KWin 认领加速度计时还没打开采样，认领被记下后没有人再调用 `driver_set_polling`。本机已换上自行编译的 3.9（`/usr/lib/iio-sensor-proxy`，原文件备份为 `iio-sensor-proxy.stock`）：传感器在拥有 D-Bus 名之前打开，已有认领会补上采样。发行版软件包和镜像都还是原版。修好后同一时刻的读数能对上方向。单位矩阵下 X 8.49、Y 0.01、Z 4.59 m/s² 被报成 `left-up`。
- KWin 在输出 DPMS 不是 On 时直接停用自动旋转。18:57 内核 `card0-DSI-1` 的 dpms 为 `Off`，策略虽然显示 `always`，方向变化也不会改画面。打开 DPMS 后，`left-up` 被应用到旋转 2（横向 965×432）。当时背光只有 1/4095，已调到约 30%（1229/4095），否则画面几乎是黑的。
- 19:01 用户确认会跟着转，但上下左右都反了。当时屏幕后倾，左边框在下、右边框在上，原始读数仍是 X 约 +8.49，方向 `left-up`、旋转 2。这是绕屏幕法线差了 180°。加上上述安装矩阵并重启代理后，同一姿势变为 `right-up`，`kscreen-doctor` 旋转值从 2 变为 8，几何尺寸仍是横向 965×432。20:20 用户确认修正后的画面方向正确。

## 还没有接通的部分

`ambient_light` 和 `proximity` 没有出现在 SEE 的 SUID 列表里，总线上 `HasAmbientLight=false`、`HasProximity=false`。SLPI 固件里有 TCS3701 / `sns_alsps` 驱动，字符串包含 “fail to probe any devices” 和 “HW absent”。同一路 `sensor_vdd` / `sensor_vddio` 上的加速度计，以及另一条 I²C 上的磁力计都能读数，所以不像是整组传感器电源没起来。主线内核没有 SLPI trace 缓冲，探测失败的 I²C 返回值还没拿到。

原厂 `dtbo` 的 `oplus,sensor-devinfo` 把光线和距离标成 TCS3701（`sensor-name = 2`）、总线 2、中断 14，`als-type = 4`。`oplus_sensor.ko` 把这组数据写进 SMEM 项 130（`SMEM_SENSOR`，5140 字节）；字段值 `0xff` 才表示退回注册表。注册表里的总线 5、中断 89 是 QRD 模板。2026-11-14 18:21 已把本机注册表改成总线 2、中断 14 并只重启 SLPI，加速度计仍在，光线和距离仍未发布。主线没有这个 SMEM 项，芯片类型和 `als-type` 还没送进 SLPI。不能先分配一块全 0 的 SMEM，否则总线 0 会盖掉现在可用的加速度计。

桌面自动旋转策略是 `always`。平放朝上时方向是 `undefined`，KWin 保留手动变换。DPMS 关闭时也不会跟着转。2026-11-14 19:01 安装矩阵取反 X/Y 后，右边框在上的姿势从 `left-up`（旋转 2）改为 `right-up`（旋转 8）。20:20 用户确认这个方向正确。登录界面那次 KWin 启动较早，当时仍显示 `incapable`；登录后的会话已经认领到加速度计。

磁力计有读数，桌面罗盘和安装方向尚未对照实机方位。陀螺仪没有单独取样。
