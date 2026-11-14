#!/bin/sh
set -eu
echo "=== unload ==="
rmmod nxp_nci_i2c || true
rmmod nxp_nci || true
echo "=== load ==="
insmod /tmp/nxp-nci.ko pll19=1
insmod /tmp/nxp-nci_i2c.ko bbclk2=1
sleep 0.4
dmesg | tail -20
echo "=== sniff cycle ==="
/tmp/nfc-sniff 28 >/tmp/nfc-cycle.log 2>&1 &
sleep 0.3
/tmp/nfc-up up
/tmp/nfc-up down
/tmp/nfc-up up
/tmp/nfc-up poll
/tmp/nfc-up down
wait
echo "===== SNIFF ====="
cat /tmp/nfc-cycle.log
echo "===== DMESG ====="
dmesg | grep -iE 'nxp-nci|pll|txldo|clock|Read failed|LN_BB' | tail -40
