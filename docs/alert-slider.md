# 三段拨杆

2026-11-17，OnePlus 10 Pro NE2210，运行内核 `7.3.0-sm8450+`。靠机顶为静音，中间为振动，靠机底为响铃。手机已安装内核模块和 udev 规则，登录会话使用发行版 feedbackd 自带的 `fbd-alert-slider`。

| 实际档位 | 下霍尔 / 上霍尔的代表读数 | Linux 输入事件 `ABS_SND_PROFILE` | feedbackd 模式 |
| --- | --- | --- | --- |
| 上 | −59 / −126 | 0 | `silent` |
| 中 | −95 / −91 | 1 | `quiet` |
| 下 | −134 / −52 | 2 | `full` |

## 实机验证

两颗 MXM1120 在 I²C 地址 `0x0c` 和 `0x0d` 均返回芯片 ID `0x9c`。第一轮由用户按上、中、下停留，表中读数取自各稳定区间。驱动沿用原厂启动判档的 30 计数差值，三档均有余量。镜像使用通用判档逻辑，无需写入这台手机的采样或校准文件。

第二轮从下档开始，用户拨到中、上、中、下，Linux 输入事件和反馈模式四次均相符。空闲观察中 I²C 控制器保持运行时挂起。模块在最后一个输入客户端关闭时停止测量并释放电源引用。[档位采样、中断和重载记录](../artifacts/alert-slider-20261117/README.md)

最终模块已安装到运行内核的 `updates/` 目录。移除已加载模块并重新发送下霍尔的 I²C 添加事件后，设备别名自动加载模块，两颗器件均绑定，用户服务也自动恢复并读回下档 `full`。本轮全程使用 USB SSH。整机重启、深度睡眠恢复、长期功耗和外磁干扰未测。Plasma Dialer 通过 KNotifications 请求来电铃声；本轮验证到 feedbackd 档位，实际来电听感和各应用的通知行为未测。

## 在手机上查看

```sh
grep -A7 'Name="Alert slider"' /proc/bus/input/devices
systemctl --user status fbd-alert-slider.service
gsettings monitor org.sigxcpu.feedbackd profile
```

## 镜像交付

内核提交 `b3a55871a46d` 构建 `mxm1120-slider.ko`。新建和续建均要求 `CONFIG_INPUT_MXM1120_SLIDER=m`。udev 按驱动创建 `/dev/input/negronislider`。图形会话通过 systemd 的路径单元等待这个设备，出现后启动反馈处理程序，设备移除时停止服务。规则、会话单元及模块都进入打包检查。新完整镜像未构建、未刷入。[内核恢复说明](../patches/linux/README.md)
