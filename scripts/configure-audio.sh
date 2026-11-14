#!/usr/bin/env bash
# Install the Negroni AudioReach topology and ALSA UCM into a mounted rootfs.
set -euo pipefail
project_dir=$(cd "$(dirname "$0")/.." && pwd)
target_dir=$(realpath -e -- "${1:?Usage: configure-audio.sh ROOTFS_DIRECTORY LOG_DIRECTORY}")
log_dir=$(realpath -m -- "${2:?Usage: configure-audio.sh ROOTFS_DIRECTORY LOG_DIRECTORY}")
[[ $EUID == 0 && $target_dir != / ]] || exit 1
# The Negroni UCM includes shared wcd938x and qcom-lpass fragments from alsa-ucm-conf.
test -s "$target_dir/usr/share/alsa/ucm2/codecs/wcd938x/init.conf"
test -s "$target_dir/usr/share/alsa/ucm2/codecs/qcom-lpass/rx-macro/init.conf"

mkdir -p "$log_dir"
if [[ -f "$log_dir/images.complete" ]]; then
    mv "$log_dir/images.complete" "$log_dir/images.complete.before-audio"
fi
rm -f "$log_dir/audio-sources.sha256" "$log_dir/audio-verification.json"
fw_dir="$target_dir/usr/lib/firmware/qcom/sm8450"
ucm_dir="$target_dir/usr/share/alsa/ucm2"
install -d -o 0 -g 0 -m 0755 "$fw_dir" "$ucm_dir/conf.d/sm8450" "$ucm_dir/OnePlus/negroni"
install -o 0 -g 0 -m 0644 "$project_dir/config/audio/firmware/OnePlus-10-Pro-tplg.bin" \
    "$fw_dir/OnePlus-10-Pro-tplg.bin"
install -o 0 -g 0 -m 0644 "$project_dir/config/audio/ucm2/conf.d/sm8450/OnePlus-10-Pro.conf" \
    "$ucm_dir/conf.d/sm8450/OnePlus-10-Pro.conf"
install -o 0 -g 0 -m 0644 "$project_dir/config/audio/ucm2/OnePlus/negroni/HiFi.conf" \
    "$ucm_dir/OnePlus/negroni/HiFi.conf"
voice_dir="$target_dir/usr/local/libexec/negroni-voice"
install -d -o 0 -g 0 -m 0755 "$voice_dir" "$target_dir/etc/systemd/system"
install -o 0 -g 0 -m 0644 "$project_dir/config/audio/voice/negroni-call-audio.py" \
    "$voice_dir/negroni-call-audio.py"
install -o 0 -g 0 -m 0644 "$project_dir/config/audio/voice/negroni-voice-test.py" \
    "$voice_dir/negroni-voice-test.py"
install -o 0 -g 0 -m 0644 "$project_dir/config/audio/voice/negroni-call-audio.service" \
    "$target_dir/etc/systemd/system/negroni-call-audio.service"
systemctl --root="$target_dir" enable negroni-call-audio.service
cd "$project_dir"
sha256sum config/audio/firmware/OnePlus-10-Pro-tplg.bin \
    config/audio/firmware/OnePlus-10-Pro-tplg.source \
    config/audio/ucm2/conf.d/sm8450/OnePlus-10-Pro.conf \
    config/audio/ucm2/OnePlus/negroni/HiFi.conf \
    config/audio/voice/negroni-call-audio.py \
    config/audio/voice/negroni-voice-test.py \
    config/audio/voice/negroni-call-audio.service \
    scripts/configure-audio.sh scripts/update-audio-image.sh \
    scripts/verify-audio-image.py > "$log_dir/audio-sources.sha256"
chown "${SUDO_UID:-1000}:${SUDO_GID:-1000}" "$log_dir/audio-sources.sha256"
