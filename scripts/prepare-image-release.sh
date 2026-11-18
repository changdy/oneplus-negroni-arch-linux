#!/usr/bin/env bash
# Collect the files needed to distribute a verified image as a GitHub Release.
set -euo pipefail
[[ $# == 3 ]] || { echo 'Usage: prepare-image-release.sh IMAGE_DIR LOG_DIR RELEASE_DIR' >&2; exit 2; }
image_dir=$1
log_dir=$2
release_dir=$3
boot_files=(boot.img vendor_boot.img recovery.img vbmeta.img)
mkdir -p "$release_dir"
for file in "${boot_files[@]}"; do
    install -m 0644 "$image_dir/$file" "$release_dir/$file"
done
install -m 0644 "$log_dir/build-result.json" "$release_dir/build-result.json"
zstd -q -3 -T2 -o "$release_dir/sparse_root.img.zst" "$image_dir/sparse_root.img"
(
    cd "$release_dir"
    files=("${boot_files[@]}" sparse_root.img.zst build-result.json)
    for file in "${files[@]}"; do
        if (( $(stat -c %s "$file") >= 2 * 1024 * 1024 * 1024 )); then
            printf '%s must be under 2 GiB to upload as a release asset.\n' "$file" >&2
            exit 1
        fi
    done
    sha256sum "${files[@]}" > SHA256SUMS
    sha256sum -c SHA256SUMS
)
