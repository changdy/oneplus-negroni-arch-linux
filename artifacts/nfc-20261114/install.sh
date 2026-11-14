#!/bin/sh
set -eu
KVER=$(uname -r)
DIR=/lib/modules/$KVER/kernel/drivers/nfc/nxp-nci
mkdir -p /root/nfc-module-prev
cp -a "$DIR/nxp-nci.ko" "$DIR/nxp-nci_i2c.ko" /root/nfc-module-prev/
cp -f /tmp/nxp-nci.ko /tmp/nxp-nci_i2c.ko "$DIR/"
cat >/etc/modprobe.d/nxp-nci.conf <<'EOF'
options nxp_nci pll19=1
options nxp_nci_i2c bbclk2=1
EOF
depmod -a "$KVER"
echo installed
ls -l "$DIR"
cat /etc/modprobe.d/nxp-nci.conf
