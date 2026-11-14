#!/bin/sh
set -eu
rmmod nxp_nci_i2c
insmod /tmp/nxp-nci_i2c.ko bbclk2=1
dmesg | tail -8
echo "=== before ==="
cat /sys/kernel/debug/clk/ln_bb_clk2/clk_enable_count
/tmp/nfc-up up
echo "=== while up ==="
cat /sys/kernel/debug/clk/ln_bb_clk2/clk_enable_count
/tmp/nfc-up poll
echo "=== pll lines ==="
dmesg | grep -iE 'pll|txldo|ln_bb|nxp-nci' | tail -15
/tmp/nfc-up down
echo "=== after down ==="
cat /sys/kernel/debug/clk/ln_bb_clk2/clk_enable_count
