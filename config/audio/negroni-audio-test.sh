#!/usr/bin/env bash
# On-device audio bring-up for OnePlus 10 Pro (negroni). Run as: sudo bash negroni-audio-test.sh STAGE
#   install  - install topology + UCM, reload the sound card, print diagnostics (no partition writes)
#   probe    - only print diagnostics
#   flash-dt SLOT - back up vendor_boot_SLOT, write vendor_boot-audio-test.img (speaker DT); SLOT = a|b,
#     the slot Linux boots from (Linux cannot read it; check with fastboot getvar current-slot)
#   restore SLOT  - write the backup taken by flash-dt back
#   tone     - play a test tone on headphones (hw:0) and speakers (hw:1), record 3 s from hw:2
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
[[ $EUID == 0 ]] || { echo "run with sudo" >&2; exit 1; }
stage=${1:?stage: install|probe|flash-dt|restore|tone}
fw=/usr/lib/firmware/qcom/sm8450/OnePlus-10-Pro-tplg.bin
ucm=/usr/share/alsa/ucm2
log=$here/audio-test-$(date +%Y%m%d-%H%M%S).log

diag() {
    {
 echo "== kernel $(uname -r)"
        cat /proc/asound/cards
        ls -l /dev/snd
        aplay -l 2>&1 || true
        arecord -l 2>&1 || true
 journalctl -k -b --no-pager | grep -iE "snd|asoc|q6apm|apm|tplg|tfa98|wcd938|soundwire|mi2s|lpass|gpr" | tail -80
        command -v alsaucm >/dev/null && alsaucm -c "$(sed -n 's/^ *\([0-9]\+\) .*/\1/p' /proc/asound/cards | head -1)" list _verbs 2>&1 || true
    } 2>&1 | tee -a "$log"
}

reload_card() {
    # The card needs the topology at probe time; rebinding the APM service re-runs it.
    modprobe -r snd_soc_sc8280xp 2>/dev/null || true
    apm=/sys/bus/aprbus/drivers/qcom-apm
    if [[ -e $apm/gprsvc:service:2:1 ]]; then
        echo gprsvc:service:2:1 > "$apm/unbind" || true
    fi
    sleep 1
    echo gprsvc:service:2:1 > "$apm/bind" 2>/dev/null || true
    modprobe snd_soc_sc8280xp || true
    sleep 3
}

slot_part() {
    local s=${1:-}
    [[ $s == a || $s == b ]] || { echo "give the boot slot explicitly: a or b" >&2; exit 1; }
    readlink -f "/dev/disk/by-partlabel/vendor_boot_$s"
}

case $stage in
install)
    pacman -Q alsa-utils >/dev/null 2>&1 || pacman -S --noconfirm --needed alsa-utils
    install -D -m 0644 "$here/OnePlus-10-Pro-tplg.bin" "$fw"
    install -D -m 0644 "$here/ucm2/conf.d/sm8450/OnePlus-10-Pro.conf" "$ucm/conf.d/sm8450/OnePlus-10-Pro.conf"
    install -D -m 0644 "$here/ucm2/OnePlus/negroni/HiFi.conf" "$ucm/OnePlus/negroni/HiFi.conf"
    reload_card
    diag
    echo "If no card appears, reboot once (topology is read at card probe) and run: sudo bash $0 probe"
    ;;
probe)
    diag
    ;;
flash-dt)
    part=$(slot_part "${2:-}")
    img=$here/vendor_boot-audio-test.img
    sha256sum -c "$here/SHA256SUMS" --ignore-missing
    bak=$here/vendor_boot-backup-$(basename "$part").img
    [[ -e $bak ]] || dd if="$part" of="$bak" bs=1M status=none
    echo "backup: $bak ($(sha256sum "$bak" | cut -c1-16))"
    size=$(stat -c %s "$img")
    dd if="$img" of="$part" bs=4096 status=none conv=fsync
    cmp -n "$size" "$img" "$part" && echo "vendor_boot written to $part; reboot to load the speaker DT"
    ;;
restore)
    part=$(slot_part "${2:-}")
    bak=$here/vendor_boot-backup-$(basename "$part").img
    [[ -s $bak ]] || { echo "no backup $bak" >&2; exit 1; }
    dd if="$bak" of="$part" bs=1M status=none conv=fsync
    cmp "$bak" "$part" && echo "restored $part"
    ;;
tone)
    card=$(sed -n 's/^ *\([0-9]\+\) .*/\1/p' /proc/asound/cards | head -1)
    alsaucm -c "$card" set _verb HiFi set _enadev Headphones 2>&1 | tee -a "$log" || true
    speaker-test -D "hw:$card,0" -c 2 -r 48000 -F S16_LE -t sine -l 1 2>&1 | tee -a "$log" || true
    alsaucm -c "$card" set _verb HiFi set _disdev Headphones set _enadev Speaker 2>&1 | tee -a "$log" || true
    speaker-test -D "hw:$card,1" -c 2 -r 48000 -F S16_LE -t sine -l 1 2>&1 | tee -a "$log" || true
    alsaucm -c "$card" set _verb HiFi set _enadev Mic1 2>&1 | tee -a "$log" || true
    arecord -D "hw:$card,2" -c 1 -r 48000 -f S16_LE -d 3 "$here/mic-test.wav" 2>&1 | tee -a "$log" || true
    ls -l "$here/mic-test.wav" 2>/dev/null | tee -a "$log" || true
    diag
    ;;
*)
    echo "unknown stage $stage" >&2; exit 2;;
esac
echo "log: $log"
