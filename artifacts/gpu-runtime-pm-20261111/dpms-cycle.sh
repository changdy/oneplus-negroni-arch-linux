#!/usr/bin/env bash
# Run as root on the phone: dpms-cycle.sh POLICY CYCLES OFF_SECONDS
# Sets the A730 runtime PM policy, cycles the panel through DPMS off/on via
# KWin and reports GPU/GMU runtime state, wake latency and new GMU errors.
set -u
policy=${1:-auto}
cycles=${2:-3}
off_s=${3:-15}
gpu=/sys/bus/platform/devices/3d00000.gpu
gmu=/sys/bus/platform/devices/3d6a000.gmu
dpms=/sys/class/drm/card0-DSI-1/dpms
sock=$(basename "$(ls /run/user/1000/wayland-[0-9] 2>/dev/null | head -1)")
as_user() {
    runuser -u oneplus -- env XDG_RUNTIME_DIR=/run/user/1000 \
        DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus \
        WAYLAND_DISPLAY="$sock" "$@"
}
now() { date +%s.%N; }
st() { printf 'gpu=%s gmu=%s dpms=%s' "$(cat $gpu/power/runtime_status)" \
    "$(cat $gmu/power/runtime_status)" "$(cat $dpms)"; }

printf %s "$policy" > $gpu/power/control
echo "policy=$(cat $gpu/power/control) autosuspend_ms=$(cat $gpu/power/autosuspend_delay_ms 2>/dev/null) kernel=$(uname -r)"
mark=$(awk '{print $1}' /proc/uptime)
for i in $(seq 1 "$cycles"); do
    as_user kscreen-doctor --dpms off >/dev/null 2>&1
    sleep "$off_s"
    echo "cycle $i before-on: $(st) gpu_suspended_ms=$(cat $gpu/power/runtime_suspended_time)"
    t0=$(now)
    as_user kscreen-doctor --dpms on >/dev/null 2>&1
    t1=$(now)
    # wait until the panel reports On and GPU is active
    for _ in $(seq 1 100); do
        [[ $(cat $dpms) == On ]] && break
        sleep 0.02
    done
    t2=$(now)
    # time a real GPU frame round-trip after wake
    as_user timeout 10 glmark2-es2-wayland --off-screen -b build:duration=0.2 >/dev/null 2>&1
    t3=$(now)
    printf 'cycle %d: kscreen=%.3fs panel_on=%.3fs first_gl=%.3fs after: %s\n' "$i" \
        "$(awk "BEGIN{print $t1-$t0}")" "$(awk "BEGIN{print $t2-$t0}")" "$(awk "BEGIN{print $t3-$t2}")" "$(st)"
    sleep 5
done
echo "--- kernel GMU/GPU messages since start"
dmesg | awk -v m="$mark" -F'[][]' '$2+0>=m' | grep -iE 'gmu|hfi|a6xx|adreno|hangcheck|gpu|recover' || echo none
