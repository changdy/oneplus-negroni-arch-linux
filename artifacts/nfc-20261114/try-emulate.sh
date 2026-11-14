#!/bin/sh
KVER=$(uname -r)
BASE=/lib/modules/$KVER/kernel/drivers/nfc/nxp-nci
echo NFC-EMULATE > /dev/kmsg
/tmp/nfc-up down >/tmp/nfc-down.out 2>&1 || true
rmmod nxp_nci_i2c 2>/dev/null || true
rmmod nxp_nci 2>/dev/null || true
rmmod nci 2>/dev/null || true
insmod /tmp/nci.ko || exit 1
insmod "$BASE/nxp-nci.ko" pll19=1 || exit 1
insmod "$BASE/nxp-nci_i2c.ko" bbclk2=1 || exit 1
printf '%s\n' cd27fcdb > /sys/module/nci/parameters/emulate_uid || exit 1
echo -n 'uid param: '
cat /sys/module/nci/parameters/emulate_uid
/tmp/nfc-sniff 28 >/tmp/nfc-sniff.out &
SP=$!
sleep 0.3
/tmp/nfc-emulate 20
wait "$SP" || true
echo '=== sniff ==='
cat /tmp/nfc-sniff.out
echo '=== dmesg ==='
dmesg | awk '/NFC-EMULATE/{p=1} p'
