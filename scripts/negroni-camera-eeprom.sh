#!/bin/bash
# Dump the ultrawide GT24P128F. The chip answers at 0x50 once CAMSS and the
# sensor are powered. The booted DT still instantiates a non-responding 0x51.
set -euo pipefail

if [[ ${1:-} == --help || $# -ne 1 ]]; then
    echo "Usage: $0 OUTPUT.bin" >&2
    exit 2
fi
output=$1
[[ $EUID -eq 0 ]] || { echo 'Run as root.' >&2; exit 2; }
[[ $output != /dev/null && ! -e $output && ! -L $output ]] || {
    echo "Output already exists: $output" >&2; exit 2;
}
sensor=/sys/bus/i2c/devices/6-0010/power/control
cci=/sys/devices/platform/soc@0/ac15000.cci/power/control
camss=/sys/devices/platform/soc@0/acb7000.camss/power/control
adapter=/sys/bus/i2c/devices/i2c-6
[[ -w $sensor && -w $cci && -w $camss && -w $adapter/new_device ]] || {
    echo 'JN1, CCI, CAMSS, or I2C adapter sysfs is missing.' >&2; exit 1;
}

old_sensor=$(cat "$sensor")
old_cci=$(cat "$cci")
old_camss=$(cat "$camss")
created=0
cleanup() {
    if (( created )); then
        printf '0x50\n' > "$adapter/delete_device" || true
    fi
    printf '%s\n' "$old_sensor" > "$sensor" || true
    printf '%s\n' "$old_cci" > "$cci" || true
    printf '%s\n' "$old_camss" > "$camss" || true
}
trap cleanup EXIT

# Holding only the sensor does not resume it. CAMSS has to be active first,
# the same order the capture pipeline uses. The temporary 24c128 client is
# writable, so it is removed before the rails drop.
echo on > "$camss"
echo on > "$cci"
echo on > "$sensor"
sleep 0.3
[[ $(cat /sys/bus/i2c/devices/6-0010/power/runtime_status) == active ]] || {
    echo 'Ultrawide sensor did not resume, so the EEPROM rail is still off.' >&2
    exit 1
}
if [[ -e /sys/bus/i2c/devices/6-0050 && ! -e /sys/bus/i2c/devices/6-0050/driver ]]; then
    printf '6-0050\n' > /sys/bus/i2c/drivers/at24/bind
elif [[ ! -e /sys/bus/i2c/devices/6-0050 ]]; then
    # Running DT still has the empty 0x51 node. This client has no read-only
    # property, so cleanup removes it.
    printf '24c128 0x50\n' > "$adapter/new_device"
    created=1
fi
nvmem=/sys/bus/i2c/devices/6-0050/eeprom
[[ -r $nvmem ]] || { echo 'GT24P128F at 0x50 did not bind to at24.' >&2; exit 1; }
# One read() of the whole chip comes back short. 128-byte reads cover all 16 KiB.
dd if="$nvmem" of="$output" bs=128 status=none
bytes=$(stat -c %s -- "$output")
[[ $bytes -eq 16384 ]] || { echo "Unexpected EEPROM size: $bytes" >&2; exit 1; }
echo "Read 16384 bytes from GT24P128F 6-0050: $output"
