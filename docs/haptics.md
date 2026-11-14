# 振动反馈（PM8350B）

状态日期：2026-11-14。设备为 OnePlus 10 Pro NE2210，内核为 `7.3.0-sm8450+`。

当前板级设备树使用 PM8350B 的 `qcom,hv-haptics`，马达类型为 8151、标称周期为 5882 µs、直接播放 VMAX 为 1680 mV。原厂模块归档中的 `aw8697.ko` 等模块属于共用驱动集合，不能据此替换本机实际配置。本次未修改马达电压或设备树。

## 修复内容

- 在 `drivers/input/misc/qcom-hv-haptics.c` 导出 OF 匹配表，使 udev 能按设备的 modalias 自动加载模块。
- 接受标准 `FF_RUMBLE`，并为反馈服务提供 `FF_SINE` 兼容路径，沿用马达的板级谐振载波。保留原有 `FF_CONSTANT` 和厂商自定义效果入口。
- 将可能睡眠的播放操作移到工作队列。短振从实际播放时开始计时；重复播放同一个已上传效果重新计时，停止请求真正关闭播放。
- 使用完整的 0–65535 主增益范围，按上传效果的强度缩放；零增益可静音。直接播放加载失败向用户空间返回错误。
- 结束效果、卸载和挂起前同步清理播放任务与计时任务；卸载时移除厂商测试 proc 节点，避免重载时报重复注册。

标准效果使用同一硬件通道，未实现多客户端效果混音、任意频率或完整的周期波形包络。厂商 RichTap、SoundWire 音频同步及深度睡眠恢复未测。

## Plasma 接入与镜像构建

Plasma Mobile 6.8.2 的 Haptics 插件调用 `org.sigxcpu.Feedback.Haptic.Vibrate`。只有 evdev 设备而没有反馈服务和设备识别规则，不能形成桌面振动链路。

- `feedbackd` 已加入 [常用软件清单](../config/packages/common-tools.txt)，随全新构建安装；已有镜像续建时清单变化会触发补装。
- [72-negroni-haptics.rules](../config/haptics/72-negroni-haptics.rules) 只匹配 `qcom-hv-haptics` 输入设备，设置 `FEEDBACKD_TYPE=vibra` 和 `uaccess`。不要求给其他输入设备扩大权限。
- 规则进入 `runtime_fixes.py` 管理清单和构建源文件指纹，镜像校验同时检查 `feedbackd`、`fbcli` 是否安装。
- 服务由会话 D-Bus 按需启动，无需另外启用系统级守护进程。桌面是否触发振动仍遵循 Plasma 自己的振动设置。

内核修复提交为 `f2fc0916795112d8e10f350bf1b27b053bef069e`，已进入父仓库 gitlink 与恢复 bundle。当前手机采用单独更新模块及用户空间组件的方式验证；全新完整 rootfs 构建和安装验证未测。

实机已验证开机自动加载、同一效果 20 次重复播放、提前停止、Plasma 所用 D-Bus 接口与模块重载，用户确认三次短振清楚。修正版最后一次普通 `systemctl reboot` 顺利完成，开机后模块自动加载，D-Bus 短振再次返回成功，失败系统服务为 0。

## 检查与短振测试

在手机的普通用户桌面会话中执行：

```sh
lsmod | grep qcom_hv_haptics
modinfo -F alias qcom-hv-haptics
grep -A8 'Name="qcom-hv-haptics"' /proc/bus/input/devices
```

仓库提供标准库诊断脚本，按设备名称寻找 event 节点，不依赖固定的 `event6` 编号：

```sh
python3 scripts/negroni-haptics-test.py --info
python3 scripts/negroni-haptics-test.py --type rumble --duration-ms 80 --strength 0.3 --count 3 --auto-stop
```

通过与 Plasma 相同的服务接口发送一次短振：

```sh
gdbus call --session --dest org.sigxcpu.Feedback \
  --object-path /org/sigxcpu/Feedback \
  --method org.sigxcpu.Feedback.Haptic.Vibrate \
  org.negroni.Haptics '[(0.35, uint32 100)]'
```

程序调用成功、寄存器启停和人手触感是不同的验证层次。实测结果、首次实验的锁问题及恢复过程见[本轮记录](../artifacts/haptics-20261114/README.md)。

## 回归检查

```sh
bash scripts/check.sh
python3 -B tests/test-haptics-driver.py /opt/negroni-build/linux
git diff --check
```

`test-haptics-driver.py` 编译真实 FF 回调，覆盖 rumble 两个强度通道、负幅度边界、上传后延迟播放、同一效果重复播放、显式停止、主增益静音以及硬件失败。模拟升压等待函数保留实际的 `play.lock` 获取行为，能够拒绝首次实验的嵌套加锁错误。该检查不能替代实机的锁、时序和触感验证。
