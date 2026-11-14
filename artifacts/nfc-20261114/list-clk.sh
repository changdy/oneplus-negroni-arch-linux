#!/bin/sh
if ! mountpoint -q /sys/kernel/debug; then
	mount -t debugfs none /sys/kernel/debug
fi
echo "=== names ==="
find /sys/kernel/debug/clk -maxdepth 1 -printf '%f\n' | grep -i -E 'bb|rf_clk|rfclk|lnb' | sort
echo "=== counts ==="
for d in /sys/kernel/debug/clk/*bb* /sys/kernel/debug/clk/*rf_clk* /sys/kernel/debug/clk/*lnb*; do
	[ -d "$d" ] || continue
	printf '%s enable=%s prepare=%s\n' "$(basename "$d")" "$(cat "$d/clk_enable_count" 2>/dev/null)" "$(cat "$d/clk_prepare_count" 2>/dev/null)"
done
