# 失败的 SDAM 时间偏移设备树实验

基于内核 `b3a55871a46d9148c77a7dbfbefec24138216a5d` 的 Negroni 设备树，在原有 `&pmk8350_rtc` 节点加 offset 引用，并新增以下单元；实验内核提交曾为 `817a039c12864880bc42e9cd98288d6064d17df6`，已从默认分支撤销。

```dts
/* Preserve the PMIC counter shared with firmware; store Unix time as an offset. */
&pmk8350_rtc {
    nvmem-cells = <&rtc_offset>;
    nvmem-cell-names = "offset";
    status = "okay";
};

/* SDAM1 bytes 0x7c-0x7f have no consumer in the NE2210 stock DT. */
&pmk8350_sdam_1 {
    rtc_offset: rtc-offset@7c {
        reg = <0x7c 0x4>;
    };
};
```

实机重启后 RTC 注册、读取和 NTP 均正常，但每次 NTP/内核同步试图写回时，`qcom,spmi-sdam` 对 0x7c 的四字节写返回 `rc=-1`（`EPERM`），RTC 仍为 1970 年。root 从 NVMEM sysfs 向同位置及同块的 0x70、另一未使用 SDAM23 的 0x7c 写回原值也全部得到 `EPERM`。先解绑 `c400000.spmi:pmic@0:rtc@6100` 停止重复报错；经用户同意，随后把刷写前的 `vendor_boot_b` 完整备份写回并重启，RTC 驱动恢复且没有新的 SDAM 写入错误。失败详情与备份哈希见[本次记录](README.md)。
