#!/bin/sh
KVER=$(uname -r)
DIR=/lib/modules/$KVER/kernel/net/nfc/nci
mkdir -p /root/nfc-module-prev "$DIR" /usr/local/bin
if [ -f "$DIR/nci.ko" ]; then
	cp -a "$DIR/nci.ko" /root/nfc-module-prev/nci.ko
fi
cp -f /tmp/nci.ko "$DIR/nci.ko"
cp -f /tmp/nfc-emulate /usr/local/bin/nfc-emulate
chmod 755 /usr/local/bin/nfc-emulate
cat >/etc/modprobe.d/nci.conf <<'EOF'
options nci emulate_uid=cd27fcdb
EOF
depmod -a "$KVER"
echo installed
ls -l "$DIR/nci.ko" /usr/local/bin/nfc-emulate
cat /etc/modprobe.d/nci.conf
