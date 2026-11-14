# 一加 10T / 10 Pro 原厂 DT 对照（USB2 口 OTG 问题）

日期：2026-11-13。只读源码调研，未修改手机。

> **21 时实机补充：下文结论 3–5 是早前的候选推断，已被新的对照实验修正。** USB2 在全程 device、UDC 仍绑定且没有 OTG host 切换时同样失败；只清除 HS PHY 充电检测 datapath override 即恢复 high-speed、USB SSH 和双向传输，同口拔插会复发。实际驱动为 `oplus_battmgr`，不能把 OTG 通知归给公共层 `qcom_battmgr`，也不能把缺少 `otg_scheme` 认定为本轮根因。自动重启 gadget 的 workaround 未经实测，不应当作已验证方案；本轮可复现的恢复命令与驱动候选见 [新实验记录](../usb2-gadget-20261113/README.md)。

## 来源

| 机型 | 仓库 | 分支 | 文件 |
| --- | --- | --- | --- |
| 10T（ovaltine / anorak） | `OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8475` | `oneplus/sm8475_v_15.0.0_oneplus_10t` | `kernel_platform/qcom/proprietary/devicetree/qcom/anorak-usb.dtsi` |
| 10T 充电 | 同上 | 同上 | `.../devicetree/oplus/oplus_chg/oplus-chg-21841.dtsi` |
| 10 Pro（negroni） | `OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8450` | `oneplus/sm8450_v_15.0.0_oneplus_10_pro` | `.../devicetree/oplus/oplus_chg/oplus-chg-20845.dtsi` |

## 10T `dwc3@a600000` 的关键属性

```dts
snps,has-lpm-erratum;
snps,hird-threshold = /bits/ 8 <0x0>;
snps,is-utmi-l1-suspend;
snps,dis-u1-entry-quirk;
snps,dis-u2-entry-quirk;
snps,dis_u2_susphy_quirk;
snps,dis_u3_susphy_quirk;
tx-fifo-resize;
dr_mode = "otg";
maximum-speed = "super-speed-plus";
usb-role-switch;
```

**没有 `snps,usb2-gadget-lpm-disable`。** 10T 用的是 `has-lpm-erratum` + `hird-threshold = 0` + `is-utmi-l1-suspend` 这一组 LPM 配置，而不是单加 disable 属性。

10T 的 USB2 PHY 是 **eUSB2 + NXP repeater**（`&eusb2_phy0 { usb-repeater = <&nxp_eusb2_repeater_oplus>; }`），10 Pro 是普通 HS PHY（`hsphy@88e3000`，`qcom,usb-snps-hs-7nm-phy`）。**两者 USB2 硬件方案不同，DT 不能直接照搬。**

## 10 Pro 充电 DT 的 OTG 配置

```dts
qcom,otg_scheme = <0>;                 // 0: cid
qcom,dischg-gpio = <&pm8350c_gpios 9 0x00>;
qcom,otg-booster-en-gpio = <&tlmm 64 0x00>;
qcom,otg-ovp-en-gpio = <&tlmm 57 0x00>;
/* pinctrl: otg_booster_en_active/sleep (gpio64), otg_ovp_en_active/sleep (gpio57) */
```

## 我们手机 DT 的现状（`/sys/firmware/devicetree/base`）

`/soc@0/usb@a600000` 有：

```
maximum-speed
snps,dis-u1-entry-quirk
snps,dis-u2-entry-quirk
snps,dis_enblslpm_quirk
snps,dis_u2_susphy_quirk
snps,dis_u3_susphy_quirk
snps,usb2-gadget-lpm-disable   ← 2026-11-13 实验补丁加的
usb-role-switch
```

`/battery` 节点**没有任何 otg / cid / typec 属性**；`/soc@0/phy@88e3000` 的 `clock-names` 是 `ref`、`ref_gate`（10T 是 `ref_clk_src`、`ref_clk`，对应不同 PHY 驱动）。

## 差异与判断

| 项 | 10T | 我们 | 判断 |
| --- | --- | --- | --- |
| `usb2-gadget-lpm-disable` | 无 | 有（实验） | 方向错误，实测无效 |
| `has-lpm-erratum` / `hird-threshold=0` / `is-utmi-l1-suspend` | 有 | 无 | 10T 的 LPM 方案，但 PHY 不同，不能直接套 |
| `dr_mode` | `"otg"` | 未写（主线默认 OTG） | 可能无影响 |
| `usb-role-switch` | 有 | 有 | 一致 |
| `maximum-speed` | `super-speed-plus` | `super-speed` | 可能影响 SS 能力，不是 USB2 掉线主因 |
| 充电 OTG DT | `otg_scheme=0`（CID）+ boost/OVP GPIO | `/battery` 无 | **移植缺口**，但我们的 `qcom_battmgr.c` 根本不解析 `qcom,otg_scheme`，补了也无效 |
| USB2 PHY | eUSB2 + NXP repeater | 普通 HS PHY | 硬件不同，不可照搬 |

## 结论

1. **LPM 补丁方向确认错误**：10T 原厂没用 `snps,usb2-gadget-lpm-disable`，实机也证明 DCFG LPMCap 清零后 USB2 口照旧失败。
2. **10T 的 DT 不能直接搬**：它的 USB2 走 eUSB2 repeater，和 10 Pro 的 HS PHY 不是一套硬件。
3. **真正的差异在驱动层**：10 Pro/10T 原厂用 `oplus_battery_sm8450/sm8475.c`，有完整的 CID/OTG 状态机；我们的主线 `qcom_battmgr.c` 只实现了最小 OTG 通知（开 GPIO + `power_supply_changed`），并且开机无条件发 `USB_OTG_AP_ENABLE=true`，把 OTG 交给充电 IC，USB2 口插入时充电 IC 误触发 `BC_OTG_ENABLE`，PMIC/Type-C 把 DWC3 切成 host。
4. **可修方向**（都需要改内核或 UCSI 角色策略，本机 WSL 被安全策略禁用，暂时不能编）：补全 `qcom_battmgr` 的 CID 判定 / 不让 `BC_OTG_ENABLE` 直接触发角色切换；或在 `dwc3-qcom` 的 host→device 切换时重新注册 gadget。
5. **免内核 workaround**：监测 `udc state`，USB2 插入后变 `not attached` 时自动重启 `usb-gadget.service` 重绑 UDC；能恢复 gadget，但每次插 USB2 都要重绑。
