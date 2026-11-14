#!/bin/sh
set -u
echo NFC-TRY-START > /dev/kmsg
if ! mountpoint -q /sys/kernel/debug; then
	mount -t debugfs none /sys/kernel/debug
fi
echo '=== up ==='
/tmp/nfc-up up
echo '=== clk while up ==='
cat /sys/kernel/debug/clk/ln_bb_clk2/clk_enable_count 2>/dev/null || echo 'no ln_bb_clk2'
/tmp/nfc-sniff 18 >/tmp/nfc-sniff.out &
SP=$!
sleep 1
echo '=== poll ==='
/tmp/nfc-up poll
wait "$SP" || true
echo '=== sniff ==='
cat /tmp/nfc-sniff.out
echo '=== down ==='
/tmp/nfc-up down
echo '=== clk after ==='
cat /sys/kernel/debug/clk/ln_bb_clk2/clk_enable_count 2>/dev/null || true
echo '=== dmesg ==='
dmesg | awk '/NFC-TRY-START/{p=1} p'
