#!/bin/sh
echo NFC-TRY2 > /dev/kmsg
/tmp/nfc-sniff 20 >/tmp/nfc-sniff.out &
SP=$!
sleep 0.2
/tmp/nfc-live 15
wait "$SP" || true
echo '=== sniff ==='
cat /tmp/nfc-sniff.out
echo '=== dmesg ==='
dmesg | awk '/NFC-TRY2/{p=1} p'
