#!/usr/bin/env bash
# Build the experimental userspace GNSS fix on the aarch64 phone.
set -euo pipefail

repo_dir=$(cd "$(dirname "$0")/.." && pwd)
build_dir=${GNSS_BUILD_DIR:-"$HOME/gnss-build"}
prefix=/opt/negroni-gnss
jobs=${JOBS:-4}

[[ $(uname -m) == aarch64 ]] || {
    printf 'Run this script on the aarch64 phone.\n' >&2
    exit 1
}
for tool in git meson ninja cc pkg-config gdbus-codegen sudo; do
    command -v "$tool" >/dev/null || { printf 'Missing tool: %s\n' "$tool" >&2; exit 1; }
done
mkdir -p "$build_dir"
build_dir=$(cd "$build_dir" && pwd)

prepare_source() {
    local name=$1 tag=$2 commit=$3 patch=$4
    local source_dir="$build_dir/$name"
    if [[ ! -d "$source_dir/.git" ]]; then
        git clone --depth 1 --branch "$tag" \
            "https://github.com/linux-mobile-broadband/$name.git" "$source_dir"
    fi
    [[ $(git -C "$source_dir" rev-parse HEAD) == "$commit" ]] || {
        printf 'Unexpected source revision: %s\n' "$source_dir" >&2
        exit 1
    }
    if ! git -C "$source_dir" apply --reverse --check "$patch" 2>/dev/null; then
        git -C "$source_dir" diff --exit-code
        git -C "$source_dir" apply --check "$patch"
        git -C "$source_dir" apply "$patch"
    fi
}

prepare_source libqmi 1.38.0 e3d79ed3f7fdc6a7fa8b374860b1c23a8f172812 \
    "$repo_dir/config/gnss/libqmi-afw.patch"
prepare_source ModemManager 1.24.2 f2b9ab1ad78d322f32134a444b5b54c6e8160e19 \
    "$repo_dir/config/gnss/modemmanager-afw.patch"

qmi_build="$build_dir/libqmi/build"
setup_args=()
[[ ! -f "$qmi_build/build.ninja" ]] || setup_args+=(--reconfigure)
meson setup "${setup_args[@]}" "$qmi_build" "$build_dir/libqmi" \
    --prefix="$prefix" --libdir=lib \
    -Dintrospection=false -Dman=false -Dgtk_doc=false \
    -Dfirmware_update=false -Dudev=false -Dbash_completion=false -Dmm_runtime_check=false
ninja -C "$qmi_build" -j "$jobs"
meson test -C "$qmi_build" --no-rebuild --print-errorlogs
sudo meson install -C "$qmi_build" --no-rebuild

mm_build="$build_dir/ModemManager/build"
setup_args=()
[[ ! -f "$mm_build/build.ninja" ]] || setup_args+=(--reconfigure)
PKG_CONFIG_PATH="$prefix/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}" \
LD_LIBRARY_PATH="$prefix/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
    meson setup "${setup_args[@]}" "$mm_build" "$build_dir/ModemManager" \
    --prefix=/usr --libdir=lib --libexecdir=lib --sysconfdir=/etc --localstatedir=/var \
    -Dintrospection=false -Dman=false -Dgtk_doc=false \
    -Dbash_completion=false -Dtests=false -Dexamples=false
ninja -C "$mm_build" -j "$jobs" src/ModemManager
sudo install -d "$prefix/sbin"
sudo install -m 0755 "$mm_build/src/ModemManager" "$prefix/sbin/ModemManager.new"
sudo mv -f "$prefix/sbin/ModemManager.new" "$prefix/sbin/ModemManager"
sha256sum "$prefix/sbin/ModemManager" "$prefix/lib/libqmi-glib.so.5.12.0"
printf 'Built in %s. Enable the service override as described in docs/gnss.md.\n' "$prefix"
