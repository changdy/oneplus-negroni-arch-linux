#!/bin/sh
set -eu
if ! mountpoint -q /sys/kernel/debug; then
	mount -t debugfs none /sys/kernel/debug
fi
echo "=== clk names ==="
find /sys/kernel/debug/clk -maxdepth 1 -iname '*bb*' -o -iname '*rf_clk*' -o -iname '*ln_bb*' | sort
echo "=== summary ==="
grep -i -E 'bb_clk|rf_clk|ln_bb' /sys/kernel/debug/clk/clk_summary || true
echo "=== parts ==="
ls /dev/disk/by-partlabel 2>/dev/null | grep -i -E 'dtbo|boot' || true
ls /dev/block/by-name 2>/dev/null | grep -i -E 'dtbo|boot' || true
