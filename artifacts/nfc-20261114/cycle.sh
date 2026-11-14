#!/bin/sh
set -eu
/tmp/nfc-sniff 25 >/tmp/nfc-cycle.log 2>&1 &
sleep 0.4
echo 1-0028 >/sys/bus/i2c/drivers/nxp-nci_i2c/unbind
sleep 0.3
echo 1-0028 >/sys/bus/i2c/drivers/nxp-nci_i2c/bind
sleep 0.4
/tmp/nfc-up up
/tmp/nfc-up poll
/tmp/nfc-up down
sleep 0.5
echo "===== SNIFF ====="
cat /tmp/nfc-cycle.log
echo "===== DMESG ====="
dmesg | grep -iE 'nxp-nci|pll|txldo|Read failed' | tail -20
