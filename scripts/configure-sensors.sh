#!/usr/bin/env bash
# Install the accelerometer mount matrix, gyroscope publisher, and SMEM light/proximity publisher.
set -euo pipefail
project_dir=$(cd "$(dirname "$0")/.." && pwd)
target_dir=$(realpath -e -- "${1:?Usage: configure-sensors.sh ROOTFS_DIRECTORY LOG_DIRECTORY}")
log_dir=$(realpath -m -- "${2:?Usage: configure-sensors.sh ROOTFS_DIRECTORY LOG_DIRECTORY}")
[[ $EUID == 0 && $target_dir != / ]] || exit 1
mkdir -p "$log_dir"
if [[ -f "$log_dir/images.complete" ]]; then
    mv "$log_dir/images.complete" "$log_dir/images.complete.before-sensors"
fi
rm -f "$log_dir/sensors-sources.sha256" "$log_dir/sensors-verification.json"
grep -Fxq "sha256 $(sha256sum "$project_dir/config/sensors/smem-sensor.bin" | cut -d' ' -f1)" \
    "$project_dir/config/sensors/smem-sensor.bin.source"
grep -Fxq "sha256 $(sha256sum "$project_dir/config/sensors/iio-sensor-proxy" | cut -d' ' -f1)" \
    "$project_dir/config/sensors/iio-sensor-proxy.source"
if [[ -f $target_dir/usr/lib/iio-sensor-proxy ]]; then
    proxy_dest=$target_dir/usr/lib/iio-sensor-proxy
elif [[ -f $target_dir/usr/libexec/iio-sensor-proxy ]]; then
    proxy_dest=$target_dir/usr/libexec/iio-sensor-proxy
else
    printf 'iio-sensor-proxy is not installed in the rootfs\n' >&2
    exit 1
fi
install -o 0 -g 0 -m 0755 "$project_dir/config/sensors/iio-sensor-proxy" "$proxy_dest"
install -d -o 0 -g 0 -m 0755 \
    "$target_dir/etc/udev/rules.d" \
    "$target_dir/etc/systemd/system" \
    "$target_dir/usr/lib/negroni" \
    "$target_dir/usr/local/sbin" \
    "$target_dir/usr/share/dbus-1/system.d"
install -o 0 -g 0 -m 0644 "$project_dir/config/sensors/81-negroni-ssc.rules" \
    "$target_dir/etc/udev/rules.d/81-negroni-ssc.rules"
install -o 0 -g 0 -m 0644 "$project_dir/config/sensors/smem-sensor.bin" \
    "$target_dir/usr/lib/negroni/smem-sensor.bin"
install -o 0 -g 0 -m 0755 "$project_dir/config/sensors/negroni-smem-sensor" \
    "$target_dir/usr/local/sbin/negroni-smem-sensor"
install -o 0 -g 0 -m 0755 "$project_dir/config/sensors/negroni-gyro" \
    "$target_dir/usr/local/sbin/negroni-gyro"
install -o 0 -g 0 -m 0644 "$project_dir/config/sensors/org.negroni.Gyroscope.conf" \
    "$target_dir/usr/share/dbus-1/system.d/org.negroni.Gyroscope.conf"
install -o 0 -g 0 -m 0644 "$project_dir/config/systemd/negroni-smem-sensor.service" \
    "$target_dir/etc/systemd/system/negroni-smem-sensor.service"
install -o 0 -g 0 -m 0644 "$project_dir/config/systemd/negroni-gyro.service" \
    "$target_dir/etc/systemd/system/negroni-gyro.service"
systemctl --root="$target_dir" enable negroni-smem-sensor.service
systemctl --root="$target_dir" enable negroni-gyro.service
cd "$project_dir"
sha256sum config/sensors/81-negroni-ssc.rules config/sensors/smem-sensor.bin \
    config/sensors/smem-sensor.bin.source config/sensors/make-smem-sensor.c \
    config/sensors/negroni-smem-sensor config/sensors/iio-sensor-proxy \
    config/sensors/iio-sensor-proxy.source config/sensors/iio-sensor-proxy-3.9-negroni.patch \
    config/sensors/negroni-gyro.c config/sensors/negroni-gyro \
    config/sensors/negroni-gyro.source config/sensors/org.negroni.Gyroscope.conf \
    config/systemd/negroni-smem-sensor.service config/systemd/negroni-gyro.service \
    scripts/configure-sensors.sh > "$log_dir/sensors-sources.sha256"
chown "${SUDO_UID:-1000}:${SUDO_GID:-1000}" "$log_dir/sensors-sources.sha256"
