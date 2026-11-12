#!/bin/sh
# USB debug gadget: NCM (ssh over usb) + ACM (serial console)
set -e
G=/sys/kernel/config/usb_gadget/negroni
modprobe libcomposite 2>/dev/null || true
case "$1" in
stop) [ -d $G ] && { echo "" > $G/UDC; }; exit 0;;
esac
[ -d $G ] && exit 0
mkdir -p $G; cd $G
echo 0x1d6b > idVendor; echo 0x0104 > idProduct; echo 0x0200 > bcdUSB
mkdir -p strings/0x409
echo negroni > strings/0x409/serialnumber
echo OnePlus > strings/0x409/manufacturer
echo "Negroni Linux Debug" > strings/0x409/product
mkdir -p configs/c.1/strings/0x409
echo "NCM+ACM" > configs/c.1/strings/0x409/configuration
mkdir -p functions/ncm.usb0 functions/acm.GS0
echo 02:11:22:33:44:55 > functions/ncm.usb0/host_addr
echo 02:11:22:33:44:56 > functions/ncm.usb0/dev_addr
ln -s functions/ncm.usb0 configs/c.1/
ln -s functions/acm.GS0 configs/c.1/
echo "$(ls /sys/class/udc | head -1)" > UDC
