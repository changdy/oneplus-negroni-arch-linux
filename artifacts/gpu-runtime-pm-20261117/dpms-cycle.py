#!/usr/bin/env python3
"""Phone/root: verify DPMS wake, runtime suspend and a rendered GL benchmark.

Run under systemd-inhibit --what=sleep to isolate runtime PM from system sleep.
Always restore the original power/control and turn the panel on on exit.
"""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

GPU = Path('/sys/bus/platform/devices/3d00000.gpu/power')
GMU = Path('/sys/bus/platform/devices/3d6a000.gmu/power')
FILTER = r'(?i)gmu|hfi|a6xx|adreno|hangcheck|gpu.*(fault|error|recover)|drm.*ERROR|dsi.*(error|timeout)'


def emit(**data):
    print(json.dumps(data), flush=True)


def run(command, timeout=15):
    return subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout).stdout


def interrupted(signum, _frame):
    raise SystemExit(128 + signum)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('policy', choices=['auto', 'on'])
    parser.add_argument('cycles', type=int)
    parser.add_argument('--off-seconds', type=float, nargs='+', default=[2, 5, 15])
    parser.add_argument('--wayland-display', default='wayland-1')
    args = parser.parse_args()
    if os.geteuid() != 0 or args.cycles < 1 or min(args.off_seconds) <= 0:
        parser.error('requires root, positive cycles and off-seconds')
    dpms, = Path('/sys/class/drm').glob('card*-DSI-1/dpms')
    user = ['runuser', '-u', 'oneplus', '--', 'env',
            'XDG_RUNTIME_DIR=/run/user/1000',
            'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus',
            f'WAYLAND_DISPLAY={args.wayland_display}']

    def screen(state):
        start = time.monotonic()
        run(user + ['kscreen-doctor', '--dpms', state.lower()])
        deadline = start + 5
        while dpms.read_text().strip() != state:
            if time.monotonic() > deadline:
                raise RuntimeError(f'panel did not reach {state}')
            time.sleep(.01)
        return time.monotonic() - start

    def counters(device):
        return {name: device.joinpath(name).read_text().strip() for name in
                ['control', 'runtime_status', 'runtime_active_time', 'runtime_suspended_time']}

    original = GPU.joinpath('control').read_text().strip()
    journal = run(['journalctl', '-k', '-n', '0', '--show-cursor', '--no-pager'])
    cursor = re.search(r'-- cursor: (.+)', journal)[1]
    emit(event='start', policy=args.policy, cycles=args.cycles,
         kernel=os.uname().release, original_control=original,
         boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
         autosuspend_ms=GPU.joinpath('autosuspend_delay_ms').read_text().strip(),
         gpu=counters(GPU), gmu=counters(GMU))
    signal.signal(signal.SIGTERM, interrupted)
    try:
        GPU.joinpath('control').write_text(args.policy)
        for cycle in range(1, args.cycles + 1):
            off_seconds = args.off_seconds[(cycle - 1) % len(args.off_seconds)]
            before = counters(GPU)
            screen('Off')
            off_start = time.monotonic()
            time.sleep(off_seconds)
            off_gpu, off_gmu = counters(GPU), counters(GMU)
            settle_start = time.monotonic()
            # KWin/lock-screen work can outlive DPMS off. Allow a bounded idle
            # settling period, recording it rather than counting a busy GPU as suspended.
            while (args.policy == 'auto' and time.monotonic() - settle_start < 3
                   and any(p['runtime_status'] != 'suspended' for p in [off_gpu, off_gmu])
                   and dpms.read_text().strip() == 'Off'):
                time.sleep(.05)
                off_gpu, off_gmu = counters(GPU), counters(GMU)
            off_dpms = dpms.read_text().strip()
            emit(event='off', cycle=cycle, off_seconds=off_seconds,
                 off_elapsed_seconds=time.monotonic() - off_start,
                 extra_idle_wait_seconds=time.monotonic() - settle_start,
                 dpms=off_dpms, gpu=off_gpu, gmu=off_gmu)
            if off_dpms != 'Off':
                raise RuntimeError('DPMS was changed during the off interval; repeat this cycle')
            if args.policy == 'auto':
                if any(p['runtime_status'] != 'suspended' for p in [off_gpu, off_gmu]):
                    raise RuntimeError('GPU/GMU did not suspend while panel was off')
                if int(off_gpu['runtime_suspended_time']) <= int(before['runtime_suspended_time']):
                    raise RuntimeError('GPU suspended-time counter did not advance')
            wake = screen('On')
            start = time.monotonic()
            gl = run(user + ['glmark2-es2-wayland', '--off-screen',
                             '-b', 'build:duration=0.2'], timeout=10)
            gl_time = time.monotonic() - start
            if not re.search(r'GL_RENDERER:\s+FD730\b', gl) or 'glmark2 Score:' not in gl:
                raise RuntimeError(f'GL did not finish on FD730: {gl}')
            emit(event='wake', cycle=cycle, panel_on_seconds=wake,
                 gl_process_seconds=gl_time, gl_score=re.search(r'glmark2 Score:\s+(\d+)', gl)[1],
                 gpu=counters(GPU), gmu=counters(GMU))
            time.sleep(1)
    finally:
        GPU.joinpath('control').write_text(original)
        try:
            screen('On')
        finally:
            emit(event='restored', control=GPU.joinpath('control').read_text().strip())
            result = subprocess.run(['journalctl', '-k', '--no-pager', '-o', 'short-monotonic',
                                     '--after-cursor', cursor, '--grep', FILTER],
                                    capture_output=True, text=True, timeout=30)
            if result.returncode not in (0, 1):
                raise RuntimeError(result.stderr)
            messages = result.stdout.strip()
            emit(event='kernel_messages', messages=messages)
            if messages and messages != '-- No entries --':
                raise RuntimeError('new GPU/display kernel messages; inspect before accepting')
    emit(event='passed', cycles=args.cycles)


if __name__ == '__main__':
    main()
