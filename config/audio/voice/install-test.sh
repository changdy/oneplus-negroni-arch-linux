#!/usr/bin/env bash
# Install/restore an explicitly staged experimental audio package. Never reboots.
set -euo pipefail
[[ $EUID == 0 ]] || { echo 'Run with sudo' >&2; exit 1; }
cd "$(dirname "$0")"
package=$PWD
release=$(uname -r)
[[ $release == '7.3.0-sm8450+' ]] || { echo "Unexpected kernel: $release" >&2; exit 1; }
module_dir=/usr/lib/modules/$release/kernel/sound/soc/qcom/qdsp6
topology=/usr/lib/firmware/qcom/sm8450/OnePlus-10-Pro-tplg.bin
modules=(snd-q6apm.ko q6apm-dai.ko q6apm-lpass-dais.ko)
backup=$package/original

replace_file() {
    local source=$1 destination=$2
    install -m 644 "$source" "$destination.negroni-voice-tmp"
    sync -f "$destination.negroni-voice-tmp"
    cmp -s "$source" "$destination.negroni-voice-tmp"
    mv -T -- "$destination.negroni-voice-tmp" "$destination"
    sync -f "$(dirname "$destination")"
    cmp -s "$source" "$destination"
}

restore() {
    (cd "$backup" && sha256sum -c SHA256SUMS)
    for module in "${modules[@]}"; do
        replace_file "$backup/$module" "$module_dir/$module"
    done
    replace_file "$backup/OnePlus-10-Pro-tplg.bin" "$topology"
    depmod -a "$release"
    sync -f "$module_dir"
    echo 'Original files restored. Running drivers unchanged; reboot separately with permission.'
}

case "${1:-}" in
    restore) restore; exit ;;
    install) ;;
    *) echo "Usage: $0 install|restore" >&2; exit 2 ;;
esac
sha256sum -c SHA256SUMS
for module in "${modules[@]}"; do
    [[ -f $module_dir/$module && -f $package/$module ]]
    reference=$module_dir/$module
    [[ ! -e $backup ]] || reference=$backup/$module
    [[ $(modinfo -F vermagic "$package/$module") == $(modinfo -F vermagic "$reference") ]] || {
        echo "Module ABI mismatch: $module" >&2; exit 1;
    }
done
if [[ ! -e $backup ]]; then
    mkdir -m 700 "$backup"
    for module in "${modules[@]}"; do
        cp -p "$module_dir/$module" "$backup/"
    done
    cp -p "$topology" "$backup/"
    (cd "$backup" && sha256sum "${modules[@]}" OnePlus-10-Pro-tplg.bin > SHA256SUMS)
    sync -f "$backup"
fi
(cd "$backup" && sha256sum -c SHA256SUMS)
trap 'status=$?; trap - ERR; echo "Install failed; restoring originals" >&2; restore; exit "$status"' ERR
for module in "${modules[@]}"; do
    replace_file "$package/$module" "$module_dir/$module"
done
replace_file "$package/OnePlus-10-Pro-voice-tplg.bin" "$topology"
depmod -a "$release"
sync -f "$module_dir"
trap - ERR
echo 'Test files installed and originals verified. No driver reload or reboot performed.'
