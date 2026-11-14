# 内屏原生分辨率与当前 Linux 模式核查

核查日期：2026-11-12。设备：OnePlus 10 Pro NE2210，运行内核 `7.3.0-sm8450+`。通过 USB SSH 只读检查，未修改手机配置、未刷写、未重启。

## 结论与实机依据

- [OnePlus 官方规格](https://www.oneplus.com/us/10-pro/specs)标注原生分辨率为 3216×1440、宽高比 20.1:9；竖屏写作 1440×3216。
- `modetest -M msm -c` 在 DSI-1 上仅列出 1080×2412 的 120、90、60 Hz 三档。
- 在当前用户 Wayland 会话查询 `kscreen-doctor -o`，选中模式为 `1080x2412@120.00`，无自定义模式；桌面缩放为 2.6，逻辑范围为 416×928。
- `journalctl -k -b` 中反复出现以下错误，与 WSL 内核源码的校验路径一致：

```text
DSI: pic_width 1440 has to be multiple of slice 540
```

原始命令输出保存在本地 `logs/display-resolution-20261112/`，不纳入 Git。当前启动日志中有校时前的历史时间戳；本记录日期按电脑侧核查日期填写。

## 源码依据

源码树为 WSL `NegroniBuild-Ubuntu-26.04` 的 `/opt/negroni-build/linux`。

- `arch/arm64/boot/dts/qcom/sm8450-oneplus-negroni.dts` 的面板 compatible 为 `panel,samsung-amb670yf07-1440-3216-dsc`；启动 simple-framebuffer 为 1080×2412。
- `drivers/gpu/drm/panel/panel-samsung-s6e3hc3.c` 的模式表同时列出 1080×2412 与 1440×3216 各三档刷新率，初始化命令也有两种尺寸的分支。
- 同一面板驱动的 probe 仍将 DSC 参数固定为 `slice_width = 540`、`slice_height = 36`、`slice_count = 1080 / 540`，旁边 TODO 指出应从选中的模式取得宽度。
- `drivers/gpu/drm/msm/dsi/dsi_host.c` 的 `msm_dsi_host_check_dsc()` 检查 `pic_width % dsc->slice_width`；非零时打印上述错误并返回 `MODE_H_ILLEGAL`。1080 可被 540 整除，1440 不可，因此 WQHD+ 模式被拒绝。

## 验证边界

已确认当前模式及 WQHD+ 被过滤的具体校验失败。未验证原生分辨率恢复、动态切换、DSC 参数随模式更新及相关时序/初始化的一致性。不能从模式表已有 WQHD+ 条目推断其已可用，也不能将本次核查视为 4:3 虚拟桌面或串流验证。
