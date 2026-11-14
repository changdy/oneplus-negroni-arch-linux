#!/usr/bin/env bash
# Cross-build the three experimental camera modules and their overlay, then
# install them into a mounted rootfs. Nothing here is loaded at boot.
set -euo pipefail
project_dir=$(cd "$(dirname "$0")/.." && pwd)
target_dir=$(realpath -e -- "${1:?Usage: build-extra-camera-modules.sh ROOTFS_DIRECTORY}")
[[ $EUID == 0 && $target_dir != / ]] || exit 1
kernel_dir=${KERNEL_DIR:-$project_dir/linux}
drivers=$project_dir/artifacts/camera-20261114/drivers
overlay=$project_dir/artifacts/camera-20261114/negroni-four-camera-test.dts
[[ -f $kernel_dir/output/.config && -f $drivers/Makefile && -f $overlay ]]
command -v dtc >/dev/null

work=$(mktemp -d /tmp/negroni-extra-camera.XXXXXX)
cleanup() { rm -rf "$work"; }
trap cleanup EXIT
cp -a "$drivers"/. "$work/drivers/"
find "$work/drivers" -mindepth 1 \( -name '*.o' -o -name '*.ko' -o -name '*.mod' -o -name '*.mod.c' \
    -o -name 'Module.symvers' -o -name 'modules.order' -o -name '.*' \) -delete
make -C "$kernel_dir" O=output ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
    M="$work/drivers" modules
cpp -nostdinc -I "$kernel_dir/include" -I "$kernel_dir/arch/arm64/boot/dts" \
    -undef -x assembler-with-cpp "$overlay" > "$work/overlay.dts"
dtc -@ -I dts -O dtb -o "$work/negroni-four-camera-test.dtbo" "$work/overlay.dts"

dest=$target_dir/usr/lib/negroni/camera
install -d -o 0 -g 0 -m 0755 "$dest" "$target_dir/usr/local/bin" \
    "$target_dir/etc/udev/rules.d"
for module in imx615.ko negroni_extra_sensors.ko negroni_camera_overlay.ko; do
    install -o 0 -g 0 -m 0644 "$work/drivers/$module" "$dest/$module"
done
install -o 0 -g 0 -m 0644 "$work/negroni-four-camera-test.dtbo" \
    "$dest/negroni-four-camera-test.dtbo"
install -d -o 0 -g 0 -m 0755 "$target_dir/usr/lib/firmware/negroni"
install -o 0 -g 0 -m 0644 "$work/negroni-four-camera-test.dtbo" \
    "$target_dir/usr/lib/firmware/negroni/negroni-four-camera-test.dtbo"
install -o 0 -g 0 -m 0644 "$project_dir/config/camera/70-negroni-dma-heap.rules" \
    "$target_dir/etc/udev/rules.d/70-negroni-dma-heap.rules"
for tool in negroni-camera-capture.sh negroni-camera-eeprom.sh negroni-camera-still.sh \
    negroni-camera-multi-capture.sh negroni-camera-meter.py negroni-camera-raw-preview.py \
    negroni-camera-idle.sh negroni-camera-extra.sh; do
    install -o 0 -g 0 -m 0755 "$project_dir/scripts/$tool" "$target_dir/usr/local/bin/$tool"
done
install -d -o 0 -g 0 -m 0755 "$target_dir/etc/wireplumber/wireplumber.conf.d"
install -o 0 -g 0 -m 0644 "$project_dir/config/camera/50-negroni-camera.conf" \
    "$target_dir/etc/wireplumber/wireplumber.conf.d/50-negroni-camera.conf"
python3 "$project_dir/scripts/camera_manifest.py" "$dest" "$kernel_dir" "$project_dir"
# No modules-load.d entry. The board DTB already probes JN1; the other three
# cameras stay unloaded until someone loads this overlay.
